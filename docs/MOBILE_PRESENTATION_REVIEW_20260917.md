# Presentation mobile review — 2026-09-17

## Scope and evidence
Chrome browser viewport emulation, not physical iOS/Android device testing. All five presentation destinations were opened at 390 × 844: campus map, campus energy dashboard, Grimes BIM, design-vs-actual, and Scan ↔ BIM. Additional 360 × 800 checks covered the map, dashboard, performance charts and scan comparison; scan comparison was also inspected at 844 × 390.

- Map: markers and readings loaded, building sidebar opened, timeline replay worked. Removed redundant mobile Explore/hint overlays and resized timeline so controls no longer overlap. Visible Grimes naming replaces the old alias.
- Dashboard: measured initial horizontal layout overflow (594 px at a 390 px viewport); bounded the building table scrolling and grid minimum widths. Retest at 390 and 360 showed no document overflow and complete chart cards.
- Performance: summary values and LEED scorecard loaded; charts remain horizontally scrollable inside their cards at 360 px without widening the page.
- BIM: Objects search selected electrical equipment 12135; actual meter graph rendered, meter 77 selection updated values, and timestamped observations were available. Panel has a sticky close control and bounded scrolling.
- Scan ↔ BIM: captured photo and BIM loaded in vertically stacked panes on portrait and side-by-side in landscape. Layers menu opened, Objects selected diffuser 15365, More details showed 96 received observations, Look around and the mobile Exit control worked. Advanced interior controls are collapsed under View settings. Duplicated header/alignment/exit controls are suppressed.

Mobile cannot be certified on all devices by viewport emulation. This review does not establish real-device GPU memory limits, Safari pointer behavior, or every experimental scan renderer. The default photo comparison was exercised; full heavy geometry remains an explicit user action.

## Object information contract
The new SVG chart uses received `timeseries_kw` records from meters 3, 76 and 77. Invalid readings are omitted, real zero preserved, timestamps sorted/deduplicated, and gaps over 30 minutes break the plotted line. Records are shown newest-first in More details, using Pacific time. Voltage/current and other channels are latest-only because the exported JSON does not retain their history. No per-device telemetry or synthetic history was created.

The card explicitly says the measurements are building meter context, not the selected object. Existing design attributes, provisional feeder associations, MODELLED allocations and identity remain available. Meter 76 is never apportioned. Stale readings are labelled STALE; a recent collection attempt alone is not proof of a recent measurement.

## Where Building Manager Online data comes from
1. Physical utility meters report to Berkeley's Building Manager Online service; this repository starts at the BMO export boundary and does not establish the upstream sensor protocol.
2. `bmo_fetch.py` authenticates using GitHub Actions secrets and requests tab-separated CSV exports for Grimes power meters 3, 76, 77 and water/steam meter 250.
3. `.github/workflows/bmo-fetch.yml` schedules collection at minute 7, 22, 37 and 52 of each hour, requesting the preceding 24 hours. Scheduling and source updates can be delayed.
4. Parsed latest readings, daily statistics and up to 96 kW samples are written by automation to `data/building_data.json` on the machine-managed `data` branch.
5. Static Pages viewers fetch that JSON. Their request cache is 60 seconds; selecting an object loads its meter context. This is periodic collection, not a direct BAS/BACnet connection or a WebSocket stream.

The collector's `status: online` means a nonempty CSV parsed successfully, not a hardware heartbeat or proof of freshness. The legacy `summary.meters_online` also counts only nonzero latest kW, so it should not be used as a definitive device availability measure. The viewer uses reading timestamps for its freshness badge (45-minute threshold).

## Validation
`node --test tests/viewer.test.cjs tests/meter-history.test.cjs` and `VIEWER=scan-bim.html node --test tests/viewer.test.cjs`; HTML inline JavaScript syntax checks and `git diff --check`. No GLB, identity sidecar or data-branch edits.

## Compact card revision

Owner requested that Scan/BIM inspection preserve the visible model. Replaced the full-pane card with a 320 px desktop card and a 276 px phone card, capped at 340 px / 248 px respectively. Desktop collapsed card measured 320 × 287 px; phone details retain the capped area and scroll internally. Kept a single measured-meter chart, compact selector, sample timestamp and freshness status. Moved duplicate headlines, long context and legacy plots to More details. The chart uses a thin unsmoothed line, subtle area shading, a last-sample marker and a pointer readout; retained timestamp gaps and missing-value semantics. Phone summary statistics are omitted from the compact face to keep the detail control visible.
