# Protocol `tectonic_dc_v1`

Every constant here was fixed before the analysis was run. Changing any one of
them produces a different protocol version and a different panel, not an
improved result. The point of writing them down is that a third party can check
whether the reported result follows from them.

---

## 1. Measurement definition

| | |
|---|---|
| Sensor | Sentinel-1 C-band synthetic aperture radar |
| Product | RTC — radiometrically terrain-corrected |
| Quantity | gamma-nought, linear power |
| Posting | 10 m |
| Source | Microsoft Planetary Computer, collection `sentinel-1-rtc` |
| Access | anonymous; assets signed without credentials |
| Primary polarisation | VH |
| Secondary polarisation | VV, recorded but not used in the decision rule |
| Unit domain tag | `LINEAR_POWER_GAMMA0` |

**Averaging happens in linear power. Conversion to decibels happens only after
aggregation, never before.** Averaging decibels averages logarithms and
silently biases the mean.

### Deviation on record

An earlier version of this protocol specified `COPERNICUS/S1_GRD_FLOAT` in
Google Earth Engine, which is sigma-nought with no terrain correction. This run
uses terrain-corrected gamma-nought instead. Terrain correction is arguably the
better choice for a site with tall structures, but it is a different instrument
definition: **absolute levels from this run are not comparable to
sigma-nought products.** Steps and contrasts within the run are comparable,
because every area of interest went through one identical pipeline. Re-running
under sigma-nought to confirm the result survives is outstanding work.

---

## 2. Scene selection

Applied in this order, with the count removed at each step recorded in
`results/attrition.csv`:

1. Scene footprint intersects the cluster bounding box.
2. Instrument mode `IW`.
3. Polarisations include both `VV` and `VH`.
4. Orbit pass `ascending`.
5. Relative orbit in {11, 113}.
6. Platform Sentinel-1A only.
7. Scene footprint **contains** the cluster hull.

Step 7 guarantees acquisition parity: every area of interest is measured on
exactly the same set of scenes, so no cross-area comparison can be an artefact
of one area having been observed on different dates than another.

### Orbit stratification

Relative orbits 11 and 113 are kept as **separate strata and never pooled.**
They view the same ground from different incidence and azimuth geometries, so
the same surface returns a different absolute backscatter on each. Pooling them
inflates the apparent pre-event variance and destroys the independence that the
decision rule depends on.

### Platform regimes

The Sentinel-1A panel is a closed historical record. Over this cluster, S1A's
last acquisition is 2026-06-24 and the first S1C/S1D acquisition is 2026-07-01.
Scenes from other platforms are tagged `EXTENSION` and reported separately.
**Regimes are never blended into one series.** Differences across the handover
are reported in `results/platform_handover.csv` so that a reader can judge the
size of the calibration offset against the size of the signal.

---

## 3. Areas of interest

Polygons are frozen in `aoi/registry_v2.geojson`. Each carries:

- `geometry_sha256` — SHA-256 over the geometry, canonical JSON, computed as
  `sha256(json.dumps(geometry, sort_keys=True, separators=(",",":")))`
- `aoi_role` — one of `treatment`, `control`, `placebo`, `positive_control`
- `geometry_frozen` — the polygon may not be edited; a change requires a new
  variant id and a new hash

The registry carries a `registry_sha256` over the set, so a reader can confirm
they hold the same set of polygons the results were computed from.

Every run must include at least one **control** (a comparable structure not
expected to change), one **placebo** (ground where a detection would falsify
the method), and one **positive control** (a site known to have changed). A run
with only treatment areas cannot be assessed.

Roles are assigned from evidence about the site, and a role may be **corrected**
if the evidence turns out to be wrong. Such a correction is recorded in the
registry with the superseded variant id, not silently applied. One occurred in
this run and is documented in `docs/VALIDATION.md`.

---

## 4. Analysis grid

Scenes arrive in mixed UTM zones. All scenes are therefore reprojected onto one
fixed target grid before any pixel is read:

| | |
|---|---|
| CRS | EPSG:32650 (UTM zone 50N) |
| Resolution | 10 m |
| Alignment | snapped to a 10 m multiple |
| Resampling | nearest neighbour |
| Extent | area-of-interest envelope plus a 60 m margin |

Because the grid is fixed, an area of interest is the identical set of pixel
positions in every scene. This makes the pixel-stability check meaningful: if
the pixel count for an area varies across scenes, something is wrong with the
read, and the run is invalid.

RTC nodata arrives as zero and is excluded before averaging.

---

## 5. Decision rule

Computed per area of interest, **independently on each relative orbit**:

| Parameter | Value |
|---|---|
| Baseline window | 2015-06-01 to 2016-06-30 |
| Minimum baseline scenes | 8 |
| Threshold | baseline mean + 3.0 × baseline standard deviation |
| Persistence requirement | 3 consecutive quarters above threshold |
| Onset | the first quarter of the first such run |
| Reported plateau | mean of the trailing 8 quarters |

**Acceptance requires both orbits to return the same onset quarter.** An
apparent event on one orbit only is not reported as a detection, whatever its
magnitude.

This is deliberately a threshold-crossing rule rather than a break-point
estimator. On a multi-year construction ramp, a least-squares single-break scan
lands somewhere mid-ramp and moves by up to a year between orbits, while the
threshold crossing is stable. A break estimator will also fit a step to a slow
drift, which produced a false positive in this run — see `docs/VALIDATION.md`.

There are no free parameters fitted to the data. The four numbers above are the
entire tuning surface, and they are declared here.

---

## 6. Mandatory quality assertions

`src/03_onset.py` refuses to emit a result unless both hold:

- **Pixel-set stability** — each area of interest resolves to exactly one
  distinct pixel count across every scene in the panel.
- **Acquisition parity** — every area of interest is measured on an identical
  number of scenes.

These are assertions, not warnings. A panel that fails either is not a panel.

---

## 7. Claim boundaries

The protocol supports statements of the form: *backscatter over this locked
polygon crossed a pre-declared threshold in this quarter, consistently across
two independent look geometries, and stayed there.*

It does not support statements about:

- **energisation, power draw, grid connection, or utilisation.** C-band responds
  to geometry and moisture. There is no physical path from this measurement to
  electrical state.
- **named construction milestones.** Onset tracks ground disturbance and early
  site works. At the one site in this run with a published start date, the
  measured onset precedes it by about a year.
- **building count, floor area, or capacity.** Not measured.

Evidence tiers are never blended. A measured onset and a date from a press
release are different kinds of claim and are reported as such.
