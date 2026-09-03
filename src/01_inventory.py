"""Step 1 — build the scene panel.

Queries the Microsoft Planetary Computer STAC catalogue for every Sentinel-1
RTC scene intersecting the site cluster, then applies the filters declared in
protocol.md, in order, recording how many scenes each one removes.

No credentials required. Writes results/candidate_pool.csv and
results/attrition.csv.
"""
import json
import pathlib

import pandas as pd
from pystac_client import Client
from shapely.geometry import shape

ROOT = pathlib.Path(__file__).resolve().parents[1]
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-1-rtc"
SEARCH_WINDOW = "2014-01-01/2026-09-04"

# Protocol constants. Declared in protocol.md; changing one invalidates the panel.
KEEP_MODE = "IW"
KEEP_POLS = {"VV", "VH"}
KEEP_PASS = "ascending"
KEEP_ORBITS = (11, 113)
FROZEN_PLATFORM = "S1A"
EXTENSION_PLATFORMS = ("S1C", "S1D")


def normalise_platform(value: str | None) -> str:
    """Platform strings arrive inconsistently cased: SENTINEL-1A vs sentinel-1a."""
    return (value or "").upper().replace("SENTINEL-", "S")


def cluster_hull(registry: dict) -> dict:
    """Axis-aligned bounding box of every AOI in the registry.

    Scene footprints must contain this hull, which guarantees that all AOIs
    are measured on exactly the same set of scenes (acquisition parity).
    """
    xs, ys = [], []
    for feature in registry["features"]:
        for x, y in feature["geometry"]["coordinates"][0]:
            xs.append(x)
            ys.append(y)
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return {
        "type": "Polygon",
        "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
    }


def main() -> None:
    registry = json.loads((ROOT / "aoi" / "registry_v2.geojson").read_text())
    hull = cluster_hull(registry)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "cluster_hull.geojson").write_text(json.dumps(hull, indent=1))

    catalogue = Client.open(STAC)
    items = list(
        catalogue.search(
            collections=[COLLECTION], intersects=hull, datetime=SEARCH_WINDOW
        ).items()
    )
    print(f"candidate scenes intersecting cluster: {len(items)}")

    rows = []
    for item in items:
        props = item.properties
        rows.append(
            {
                "scene_id": item.id,
                "acq_dt": item.datetime.isoformat(),
                "acq_date": item.datetime.date().isoformat(),
                "platform": normalise_platform(props.get("platform")),
                "orbit_pass": props.get("sat:orbit_state"),
                "rel_orbit": props.get("sat:relative_orbit"),
                "abs_orbit": props.get("sat:absolute_orbit"),
                "mode": props.get("sar:instrument_mode"),
                "polarizations": ",".join(sorted(props.get("sar:polarizations") or [])),
            }
        )
    pool = pd.DataFrame(rows).sort_values("acq_dt").reset_index(drop=True)
    pool.to_csv(ROOT / "results" / "candidate_pool.csv", index=False)

    # Sequential attrition, in the order declared in protocol.md.
    hull_geom = shape(hull)
    contains_hull = {
        item.id: shape(item.geometry).contains(hull_geom) for item in items
    }
    pool["contains_hull"] = pool.scene_id.map(contains_hull)

    steps = [
        ("0 candidate scenes over cluster", pd.Series(True, index=pool.index)),
        ("1 instrument mode IW", pool["mode"] == KEEP_MODE),
        (
            "2 polarizations include VV and VH",
            pool.polarizations.apply(lambda s: KEEP_POLS <= set(s.split(","))),
        ),
        ("3 orbit pass ascending", pool.orbit_pass == KEEP_PASS),
        ("4 relative orbit in {11, 113}", pool.rel_orbit.isin(KEEP_ORBITS)),
        ("5 platform Sentinel-1A only", pool.platform == FROZEN_PLATFORM),
        ("6 footprint contains cluster hull", pool.contains_hull),
    ]
    keep = pd.Series(True, index=pool.index)
    attrition = []
    for label, condition in steps:
        before = int(keep.sum())
        keep = keep & condition
        after = int(keep.sum())
        attrition.append(
            {"step": label, "remaining": after, "dropped": before - after}
        )
    frame = pd.DataFrame(attrition)
    frame.to_csv(ROOT / "results" / "attrition.csv", index=False)
    print()
    print(frame.to_string(index=False))

    frozen = pool[keep]
    print()
    print(
        f"frozen panel: {len(frozen)} scenes, "
        f"{frozen.acq_date.min()} to {frozen.acq_date.max()}"
    )
    print(f"  by relative orbit: {frozen.rel_orbit.value_counts().to_dict()}")

    extension = pool[
        (pool["mode"] == KEEP_MODE)
        & (pool.orbit_pass == KEEP_PASS)
        & pool.rel_orbit.isin(KEEP_ORBITS)
        & pool.platform.isin(EXTENSION_PLATFORMS)
        & pool.contains_hull
    ]
    if len(extension):
        print(
            f"extension regime ({'/'.join(EXTENSION_PLATFORMS)}): {len(extension)} scenes, "
            f"{extension.acq_date.min()} to {extension.acq_date.max()} "
            "— tagged separately, never pooled with the frozen panel"
        )


if __name__ == "__main__":
    main()
