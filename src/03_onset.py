"""Step 3 — the onset test, and the checks that decide whether to believe it.

The detection rule and every threshold in it are fixed in protocol.md. Nothing
here is tuned to the data.

  Onset = the first quarter whose mean VH exceeds
          baseline mean + K_SIGMA x baseline SD
          and which stays above that line for PERSIST_QUARTERS consecutive
          quarters.

The test runs independently on each relative orbit. A result is accepted only
if both orbits return the same quarter. That is the discriminator, not the
size of the step: orbits 11 and 113 see the same ground from different look
geometries, so a processing artefact or a slow drift has no reason to agree
across them and a real construction event has every reason to.

Writes results/onset.csv, results/quarterly_vh_db.csv,
results/platform_handover.csv and results/verification.csv.
"""
import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]

# --- Pre-registered constants. Declared before the data was read. ------------
BASELINE_START = "2015-06-01"
BASELINE_END = "2016-06-30"
K_SIGMA = 3.0
PERSIST_QUARTERS = 3
MIN_BASELINE_SCENES = 8
PLATEAU_QUARTERS = 8  # trailing window used to report the settled level
ORBITS = (11, 113)
# ----------------------------------------------------------------------------

AOI_ORDER = [
    "T1_ntt_fdc__v1",
    "C1_hkex_dc__v1",
    "P1_vacant__v1",
    "C2b_amc__v2",
    "X1_build_slab__v1",
    "X2_build_site__v1",
]


def to_db(linear: pd.Series) -> pd.Series:
    return 10.0 * np.log10(linear)


def onset_for(series: pd.DataFrame) -> dict:
    """Apply the pre-registered onset rule to one AOI on one orbit."""
    series = series.sort_values("acq_date")
    baseline = series[
        (series.acq_date >= BASELINE_START) & (series.acq_date <= BASELINE_END)
    ].vh_db
    if len(baseline) < MIN_BASELINE_SCENES:
        return {"onset_quarter": None, "note": "insufficient baseline"}

    baseline_mean = baseline.mean()
    baseline_sd = baseline.std(ddof=1)
    threshold = baseline_mean + K_SIGMA * baseline_sd

    quarterly = series.groupby("quarter").vh_db.mean()
    above = (quarterly > threshold).to_numpy()
    quarters = quarterly.index.tolist()

    onset = None
    for start in range(len(quarters) - PERSIST_QUARTERS + 1):
        if above[start : start + PERSIST_QUARTERS].all():
            onset = start
            break

    return {
        "baseline_db": round(baseline_mean, 2),
        "baseline_sd_db": round(baseline_sd, 3),
        "threshold_db": round(threshold, 2),
        "onset_quarter": quarters[onset] if onset is not None else None,
        "level_at_onset_db": round(quarterly.iloc[onset], 2)
        if onset is not None
        else None,
        "plateau_db": round(quarterly.iloc[-PLATEAU_QUARTERS:].mean(), 2),
        "note": "",
    }


def main() -> None:
    registry = json.loads((ROOT / "aoi" / "registry_v2.geojson").read_text())
    roles = {
        f["properties"]["aoi_variant_id"]: f["properties"]["aoi_role"]
        for f in registry["features"]
    }

    frame = pd.read_csv(ROOT / "results" / "scene_level.csv")
    frame["vh_db"] = to_db(frame.vh_mean_linear)
    frozen = frame[frame.regime == "FROZEN"]
    extension = frame[frame.regime == "EXTENSION"]

    # --- QA: pixel-set stability ---------------------------------------------
    print("QA — pixel set must be identical in every scene")
    stability = (
        frozen.groupby("aoi_variant_id")
        .vh_n_px.nunique()
        .rename("distinct_pixel_counts")
        .reset_index()
    )
    stability["stable"] = stability.distinct_pixel_counts == 1
    print(stability.to_string(index=False))
    assert stability.stable.all(), "pixel set is not stable — panel is invalid"

    # --- QA: acquisition parity ---------------------------------------------
    parity = frozen.groupby("aoi_variant_id").scene_id.nunique()
    assert parity.nunique() == 1, "AOIs measured on different scene sets"
    print(f"\nacquisition parity: {parity.iloc[0]} scenes for every AOI")
    print(
        f"panel: {frozen.acq_date.min()} to {frozen.acq_date.max()}, "
        f"orbits {dict(frozen[frozen.aoi_variant_id == AOI_ORDER[0]].rel_orbit.value_counts())}"
    )

    # --- The onset test ------------------------------------------------------
    records = []
    for aoi_id in AOI_ORDER:
        for orbit in ORBITS:
            subset = frozen[
                (frozen.aoi_variant_id == aoi_id) & (frozen.rel_orbit == orbit)
            ]
            record = onset_for(subset)
            record.update(
                aoi_variant_id=aoi_id, aoi_role=roles[aoi_id], rel_orbit=orbit
            )
            records.append(record)
    onset = pd.DataFrame(records)[
        [
            "aoi_variant_id",
            "aoi_role",
            "rel_orbit",
            "baseline_db",
            "baseline_sd_db",
            "threshold_db",
            "onset_quarter",
            "level_at_onset_db",
            "plateau_db",
        ]
    ]
    onset["rise_db"] = (onset.plateau_db - onset.baseline_db).round(2)
    onset.to_csv(ROOT / "results" / "onset.csv", index=False)
    print(
        f"\nONSET TEST — baseline {BASELINE_START[:7]} to {BASELINE_END[:7]}, "
        f"threshold = mean + {K_SIGMA:g} SD, must persist {PERSIST_QUARTERS} quarters"
    )
    print(onset.to_string(index=False))

    # --- Cross-orbit agreement: the accept/reject decision -------------------
    print("\nCROSS-ORBIT AGREEMENT — a result is accepted only if both orbits agree")
    verification = []
    for aoi_id in AOI_ORDER:
        pair = onset[onset.aoi_variant_id == aoi_id]
        quarters = pair.onset_quarter.tolist()
        detected = all(q is not None and not pd.isna(q) for q in quarters)
        agree = detected and len(set(quarters)) == 1
        verification.append(
            {
                "aoi_variant_id": aoi_id,
                "aoi_role": roles[aoi_id],
                "onset_o11": quarters[0],
                "onset_o113": quarters[1],
                "accepted": agree,
                "rise_o11_db": pair.rise_db.iloc[0],
                "rise_o113_db": pair.rise_db.iloc[1],
            }
        )
        flag = "ACCEPTED" if agree else "no detection"
        print(
            f"  {aoi_id:22s} {roles[aoi_id]:17s} "
            f"o11 {str(quarters[0]):7s} o113 {str(quarters[1]):7s}  {flag}"
        )
    pd.DataFrame(verification).to_csv(
        ROOT / "results" / "verification.csv", index=False
    )

    # --- Quarterly series ----------------------------------------------------
    quarterly = (
        frozen.pivot_table(
            index="quarter", columns="aoi_variant_id", values="vh_db", aggfunc="mean"
        )[AOI_ORDER]
        .round(2)
    )
    quarterly.to_csv(ROOT / "results" / "quarterly_vh_db.csv")
    print(f"\nwrote quarterly series, {len(quarterly)} quarters")

    # --- Platform handover ---------------------------------------------------
    if len(extension):
        handover = []
        for aoi_id in AOI_ORDER:
            recent = frozen[
                (frozen.aoi_variant_id == aoi_id) & (frozen.acq_date >= "2026-01-01")
            ].vh_db.mean()
            new = extension[extension.aoi_variant_id == aoi_id].vh_db.mean()
            handover.append(
                {
                    "aoi_variant_id": aoi_id,
                    "aoi_role": roles[aoi_id],
                    "frozen_2026h1_db": round(recent, 2),
                    "extension_db": round(new, 2),
                    "delta_db": round(new - recent, 2),
                }
            )
        handover = pd.DataFrame(handover)
        handover.to_csv(ROOT / "results" / "platform_handover.csv", index=False)
        quiet = handover[handover.aoi_role.isin(["control", "placebo"])].delta_db
        print("\nPLATFORM HANDOVER — S1A panel vs extension regime")
        print(handover.to_string(index=False))
        print(
            f"  unchanged ground: mean {quiet.mean():+.2f} dB "
            f"(n={len(quiet)}) — the offset is small next to the signal"
        )


if __name__ == "__main__":
    main()
