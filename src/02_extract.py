"""Step 2 — read every scene onto one fixed grid and reduce to AOI means.

Every scene is reprojected onto a single fixed target grid (EPSG:32650, 10 m,
snapped) before any pixel is touched. This matters: scenes arrive in mixed UTM
zones, so without a fixed grid the "same" AOI would be a slightly different set
of pixels in different scenes and the pixel-stability check would be
meaningless.

Averaging happens in linear power. Conversion to dB happens only after
aggregation, never before.

No credentials required — Planetary Computer RTC assets are signed anonymously.
Writes results/scene_level.csv and results/qa_pixel_counts.csv.
"""
import json
import os
import pathlib
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import planetary_computer
import rasterio
from pystac_client import Client
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from shapely.geometry import shape

warnings.filterwarnings("ignore")

# Let GDAL skip directory listings on remote reads. Do NOT set
# CPL_VSIL_CURL_ALLOWED_EXTENSIONS: the RTC assets are named ".rtc.tiff" and an
# extension allowlist of ".tif" silently blocks every read.
os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"

ROOT = pathlib.Path(__file__).resolve().parents[1]
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-1-rtc"
SEARCH_WINDOW = "2014-01-01/2026-09-04"

TARGET_CRS = CRS.from_epsg(32650)  # UTM 50N, covers Hong Kong
RESOLUTION = 10.0  # metres, the native RTC posting
PAD_M = 60.0  # grid margin around the AOI set
MAX_WORKERS = 12

KEEP_MODE = "IW"
KEEP_POLS = {"VV", "VH"}
KEEP_PASS = "ascending"
KEEP_ORBITS = (11, 113)
FROZEN_PLATFORM = "S1A"
EXTENSION_PLATFORMS = ("S1C", "S1D")


def normalise_platform(value: str | None) -> str:
    return (value or "").upper().replace("SENTINEL-", "S")


def build_grid(aois):
    """One fixed, snapped grid covering every AOI. Identical for all scenes."""
    projected = [transform_geom("EPSG:4326", TARGET_CRS, geom) for _, _, geom in aois]
    xs = [c[0] for g in projected for c in g["coordinates"][0]]
    ys = [c[1] for g in projected for c in g["coordinates"][0]]
    x0 = np.floor((min(xs) - PAD_M) / RESOLUTION) * RESOLUTION
    y1 = np.ceil((max(ys) + PAD_M) / RESOLUTION) * RESOLUTION
    width = int(np.ceil((max(xs) + PAD_M - x0) / RESOLUTION))
    height = int(np.ceil((y1 - (min(ys) - PAD_M)) / RESOLUTION))
    transform = from_origin(x0, y1, RESOLUTION, RESOLUTION)
    masks = {
        aoi_id: geometry_mask(
            [geom], out_shape=(height, width), transform=transform, invert=True
        )
        for (aoi_id, _, _), geom in zip(aois, projected)
    }
    return transform, width, height, masks


def main() -> None:
    registry = json.loads((ROOT / "aoi" / "registry_v2.geojson").read_text())
    aois = [
        (f["properties"]["aoi_variant_id"], f["properties"]["aoi_role"], f["geometry"])
        for f in registry["features"]
    ]
    hull = json.loads((ROOT / "results" / "cluster_hull.geojson").read_text())
    hull_geom = shape(hull)

    transform, width, height, masks = build_grid(aois)
    print(f"target grid {width} x {height} px, EPSG:32650 @ {RESOLUTION:.0f} m")
    index = {k: np.flatnonzero(m.ravel()) for k, m in masks.items()}
    for aoi_id, _, _ in aois:
        print(f"  {aoi_id:22s} {len(index[aoi_id]):4d} px")
    pd.DataFrame(
        [
            {"aoi_variant_id": a, "measured_px_10m": len(index[a])}
            for a, _, _ in aois
        ]
    ).to_csv(ROOT / "results" / "qa_pixel_counts.csv", index=False)

    catalogue = Client.open(STAC)
    items = list(
        catalogue.search(
            collections=[COLLECTION], intersects=hull, datetime=SEARCH_WINDOW
        ).items()
    )

    def passes_base_filters(item) -> bool:
        props = item.properties
        return (
            props.get("sar:instrument_mode") == KEEP_MODE
            and KEEP_POLS <= set(props.get("sar:polarizations") or [])
            and props.get("sat:orbit_state") == KEEP_PASS
            and props.get("sat:relative_orbit") in KEEP_ORBITS
            and shape(item.geometry).contains(hull_geom)
        )

    selected = []
    for item in items:
        if not passes_base_filters(item):
            continue
        platform = normalise_platform(item.properties["platform"])
        if platform == FROZEN_PLATFORM:
            selected.append(("FROZEN", item))
        elif platform in EXTENSION_PLATFORMS:
            selected.append(("EXTENSION", item))
    selected.sort(key=lambda pair: pair[1].datetime)
    frozen_n = sum(1 for r, _ in selected if r == "FROZEN")
    print(f"\nfrozen {frozen_n} scenes, extension {len(selected) - frozen_n} scenes")

    def read_scene(position: int):
        _, item = selected[position]
        signed = planetary_computer.sign(item)
        bands = {}
        with rasterio.Env(GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2"):
            for band in ("vv", "vh"):
                with rasterio.open(signed.assets[band].href) as src, WarpedVRT(
                    src,
                    crs=TARGET_CRS,
                    transform=transform,
                    width=width,
                    height=height,
                    resampling=Resampling.nearest,
                ) as vrt:
                    bands[band] = vrt.read(1).astype("float32")
        return position, bands

    total = len(selected)
    stack = {
        "vv": np.full((total, height * width), np.nan, dtype="float32"),
        "vh": np.full((total, height * width), np.nan, dtype="float32"),
    }
    failures = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(read_scene, k): k for k in range(total)}
        completed = 0
        for future in as_completed(futures):
            try:
                position, bands = future.result()
                stack["vv"][position] = bands["vv"].ravel()
                stack["vh"][position] = bands["vh"].ravel()
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                failures.append((futures[future], type(exc).__name__, str(exc)[:160]))
            completed += 1
            if completed % 100 == 0:
                print(
                    f"  {completed}/{total} scenes  {time.time() - started:.0f}s  "
                    f"failures={len(failures)}",
                    flush=True,
                )
    print(f"read {total - len(failures)}/{total} scenes, {len(failures)} failures")
    for failure in failures[:5]:
        print("  ", failure)

    # RTC nodata arrives as 0; exclude it rather than letting it drag the mean.
    for band in ("vv", "vh"):
        stack[band][stack[band] <= 0] = np.nan

    rows = []
    for position, (regime, item) in enumerate(selected):
        props = item.properties
        base = {
            "regime": regime,
            "scene_id": item.id,
            "acq_dt": item.datetime.isoformat(),
            "acq_date": item.datetime.date().isoformat(),
            "quarter": str(pd.Period(item.datetime.date(), freq="Q")),
            "platform": normalise_platform(props["platform"]),
            "rel_orbit": props["sat:relative_orbit"],
            "orbit_pass": props["sat:orbit_state"],
        }
        for aoi_id, role, _ in aois:
            selection = index[aoi_id]
            vv = stack["vv"][position, selection]
            vh = stack["vh"][position, selection]
            rows.append(
                {
                    **base,
                    "aoi_variant_id": aoi_id,
                    "aoi_role": role,
                    "unit_domain": "LINEAR_POWER_GAMMA0",
                    "vv_mean_linear": float(np.nanmean(vv))
                    if np.isfinite(vv).any()
                    else None,
                    "vv_n_px": int(np.isfinite(vv).sum()),
                    "vh_mean_linear": float(np.nanmean(vh))
                    if np.isfinite(vh).any()
                    else None,
                    "vh_n_px": int(np.isfinite(vh).sum()),
                }
            )
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "results" / "scene_level.csv", index=False)
    print(f"wrote results/scene_level.csv, {len(frame)} rows")


if __name__ == "__main__":
    main()
