# Campus energy dashboard observation audit

The existing public dashboard remains a self-contained HTML page using Chart.js 4.4.1 and the same public snapshot/history JSON endpoints. No collector, data-branch, access, or sharing changes.

## Initial redesign (superseded where noted below)

- Parse full BMO observation timestamps as America/Los_Angeles; ambiguous/nonexistent DST times are excluded rather than guessed. Do not order by collector HH:MM.
- Last 24 hours, last 7 days, and all retained observations are actual elapsed-time windows ending now. Up to 96 retained samples can span weeks.
- Preserve numerical zero, distinguish unavailable/stale/time-unknown readings, show responding meter IDs and original timestamps. Recent means at most 60 minutes old, not proof of complete meter coverage.
- Building selection, comparison, campus search/drilldown, original reading table and CSV export. The chart does not bridge gaps over one hour or sum asynchronous building histories.
- Current kW multiplied by 24 is explicitly a constant-demand scenario, not measured daily energy. Source forecasts and anomalies remain labelled heuristic.
- Building/feeder context is distinct from Brick relationships or modelled device allocation. No per-equipment telemetry is invented.
- Light analytical canvas with Berkeley navy/gold, meaningful group colors, six summary cells, responsive charts and reduced-motion support.

## Initial verification

- Node test runner: 56 tests passed, including six new regression cases. New cases failed before implementation/fix.
- Python unittest discovery: 13 passed. MEP recovery: 7 passed. Initial missing Three.js/NumPy/Pillow and sparse-checkout fixtures were resolved in an isolated verification environment; final suites passed.
- Mac Chrome: desktop and 390×844 viewport (375 CSS content pixels with scrollbar), no document overflow, no captured console warnings/errors. Physical mobile devices not tested.
- Checked building selection, comparison, all period buttons, zero-demand Etcheverry, no-reading Cory, comparison-only chart, search, inventory drilldown, source table expansion and manual refresh.
- Browser CSV download: 96 Grimes records exactly matched published observation timestamps and kW values.
- Separate code review found an empty-chart epoch-date issue. Fixed with an explicit no-observations state and regression test; populated comparisons remain visible.

The original source snapshot inspected was generated 2026-10-13 01:53:27 UTC and contained 25 available readings among 37 buildings. Live data may change; these are audit-time counts, not constants in the UI.

## Readability and interpretation refinement

- Lead with a building-specific reading brief: prominent observed kW, original Pacific timestamp, meter IDs, elapsed reading age, and comparison with the preceding actual observation including both times and the precise interval.
- Replace the arbitrary 60-minute recent/stale classification with neutral elapsed age. No collection SLA or completeness percentage is inferred.
- Show observed maximum and its timestamp, minimum, sample median and valid count/date count. These are not billing peak, baseload, time-weighted demand or efficiency metrics.
- Render individual observations without connecting lines. Replace campus category totals/shares with daily observation counts and median/maximum sampling gaps; unknown feeder overlap prevents defensible campus aggregation.
- Explain kW versus kWh prominently. Daily kWh, load factor, EUI, savings and fault diagnoses are not calculated from sparse snapshots. Model assumptions remain collapsed.
- Increase type size, weight and contrast; retain responsive two-column mobile statistics and visible building context. References: EnergyCAP interval-data guidance, EPA EUI definition, Figma hierarchy and CLEVER°FRANKE dashboard design, linked in-page.

### Refinement validation

- Node: 60 tests passed, including 10 dashboard regression cases for timestamps, missing/zero values, CSV, periods, empty charts, reading interpretation, sampling gaps and exact comparison intervals.
- Python: 13 tests passed; MEP recovery: 7 passed.
- Independent review: no critical or important findings.
- Mac Chrome desktop and 390×844 mobile: no horizontal document overflow, large primary number visible in the first mobile screen; no captured console warnings/errors. Verified period/building/comparison controls, zero reading, missing reading and comparison-only chart. Existing CSV export remains covered by regression tests and earlier exact-source download verification.
