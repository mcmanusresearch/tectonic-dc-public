# Validation

Six tests were declared before this run, each with a stated failure condition
that would invalidate the result. This file records how every one adjudicated,
including the ones that did not pass and the ones still outstanding.

Declaring a failure condition in advance is what separates a measurement from a
demonstration. A method that has never been given the chance to fail has not
been validated by finding a result it likes.

Summary: **four passed, one failed and was resolved against the study design,
two remain outstanding.**

---

## Test 1 — Positive controls must respond

**Declared failure:** if areas of interest known to have been under
construction show no step, the method cannot detect construction and nothing
else in the run means anything.

**Outcome: passed.** Both works-lot areas cross threshold at 2017Q1 on both
orbits independently, with rises of +4.7 to +7.8 dB against baseline standard
deviations of 1.2 to 1.4 dB. Both respond again in 2026, coinciding with a
build visible in current imagery.

---

## Test 2 — Controls and placebos must stay quiet

**Declared failure:** if areas expected to be static also step, the detection is
an artefact of the pipeline rather than a measurement of the ground.

**Outcome: failed as originally specified, then resolved.** One of the two
designated controls — the Advanced Manufacturing Centre — stepped, hard, by more
than 10 dB on both orbits.

The resolution is not favourable to the study design. The Advanced Manufacturing
Centre was **not a valid control**: it was under construction from 2018 and
completed in April 2022
([HKSTP](https://www.hkstp.org/en/park-life/news-and-events/news/hkstp-unveils-its-advanced-manufacturing-centre-amc-to-accelerate-researchtoindustry-propel-in)),
squarely inside the observation window. It was selected as a control on the
mistaken assumption that an operating industrial building had been static
throughout. That was an analyst error in site selection, not a measurement
artefact.

It is reclassified as a positive control in `aoi/registry_v2.geojson`, with the
superseded variant id recorded in the feature properties rather than the change
being applied silently.

Two things follow, and only one of them is comfortable:

- The measurement caught a design error that its author did not. That is the
  behaviour a control structure exists to produce.
- The originally specified test still failed. Anyone assessing this run should
  treat "controls stayed quiet" as holding for the two areas that were genuinely
  static — the operating HKEX data centre and the vacant lot, neither of which
  crosses threshold on either orbit across eleven years — and not for the
  control set as originally drawn.

---

## Test 3 — Pixel sets must be stable

**Declared failure:** if the pixel count for an area of interest varies across
scenes, the "same" area is not the same measurement over time and any trend
could be a change in what was sampled.

**Outcome: passed.** Each of the six areas resolves to exactly one distinct
pixel count across all 608 scenes. This is enforced as an assertion in
`src/03_onset.py`, which will not emit a result if it fails. Because all scenes
are reprojected onto one fixed grid, stability holds by construction rather than
by luck — but it is still checked, because a construction that guarantees a
property is not evidence that the code implements the construction.

---

## Test 4 — Acquisition parity must hold

**Declared failure:** if different areas of interest are measured on different
scene sets, comparisons between them are confounded with observation dates.

**Outcome: passed.** 608 scenes for every area, guaranteed by requiring each
scene footprint to contain the cluster hull rather than merely intersect it.
Zero scenes were lost to partial coverage. Also enforced as an assertion.

---

## Test 5 — Detections must not coincide with processing-regime boundaries

**Declared failure:** if a detected onset lands on the date a processing
baseline changed, the step is a calibration artefact rather than a physical
change.

**Outcome: not adjudicated.** The Planetary Computer RTC collection does not
expose the processor version fields needed to test this. It is executable
against Google Earth Engine's Sentinel-1 collection, which carries the
processing metadata, and that re-run is outstanding.

This is a real gap, not a formality. It is the single strongest remaining
alternative explanation for the accepted detections, and it is not addressed by
anything else in this run. The cross-orbit agreement requirement provides
partial cover — a processing change would have to shift both orbits' calibration
in the same direction in the same quarter — but partial cover is not a test.

---

## Test 6 — Results must survive an inward buffer

**Declared failure:** if a detection disappears when the polygon is shrunk to
exclude its boundary pixels, the step came from edge effects or from
mis-registration against neighbouring ground rather than from the site itself.

**Outcome: not yet run.** The smallest area in the set is 67 pixels at 10 m, so
an inward buffer removes a large fraction of the sample and the test needs to be
specified carefully before it is meaningful. It is not reported as passing.

---

## A false positive worth publishing

This did not correspond to a declared test, and it is the most useful thing the
run produced.

An earlier version of the analysis used a least-squares single-break scan: fit a
single step at every candidate date, take the date with the best fit, report the
step size divided by the residual standard deviation as a signal-to-noise ratio.

On the NTT FDC campus — an operating data centre where nothing was built during
the window — that scan reported:

| Orbit | Break date | Step | Signal-to-noise |
|---|---|---|---|
| 11 | 2022-08-13 | −2.89 dB | −4.10 |
| 113 | 2022-11-24 | +1.32 dB | +1.58 |

A signal-to-noise ratio of −4.10 sits well past any plausible detection floor,
and the largest value on either genuinely static area in the same run was 1.74.
Judged on effect size, this is a detection. There is no event. The campus drifts
slowly downward across eleven years, and a least-squares break estimator will
fit a step to a drift because a step is the only shape it is permitted to fit.

The two orbits disagree in **sign**. They observe the same ground; they cannot
both be right, and a physical change would not reverse direction with look
geometry.

Two conclusions were adopted into `protocol.md` as a result:

1. **Effect size is not a decision rule.** Cross-orbit agreement in both sign
   and date is the accept/reject criterion. Magnitude is reported, not trusted.
2. **Report threshold-crossing onset, not the least-squares break point.** On the
   Advanced Manufacturing Centre's four-year ramp, the least-squares break lands
   mid-ramp and moves a full year between orbits (2018-07 against 2019-08) while
   the threshold-crossing onset is 2018Q2 on both. The threshold rule is stable
   where the break estimator is not.

Both are protocol amendments arising from a failure, which is the only way a
measurement protocol ever improves.

---

## What would falsify the accepted result

For completeness, the specific findings that would overturn the detections
reported in `README.md`:

- A primary document showing the Advanced Manufacturing Centre site was
  undisturbed through 2018 and 2019.
- A Sentinel-1 processing baseline change over Hong Kong in 2018Q2 or 2017Q1
  affecting both relative orbits.
- Reproduction under sigma-nought showing no onset at either date.
- An inward-buffered polygon showing the rise confined to boundary pixels.

None of these has been ruled out by anything in this repository except the
first, and only partially.
