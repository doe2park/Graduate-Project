# Original dark design with validated observation handling

The user selected the original 97c9751 visual design after comparing saved versions. This update uses its actual CSS/token system and compact header, 1200px content width, four small metric cards, full-width trend, and paired donut/ranking cards. It removes decorative emoji and the bright redesign's oversized intro/hero; supplementary research context is collapsed. The SVG data flow is retained in dark colors.

The lead metrics now describe the selected building and actual observations, replacing unsupported campus sums, instantaneous-demand daily energy and headline tariff scenarios. Existing cost/carbon scenarios remain explicitly labelled inside collapsed details. The donut partitions selected observations by kW band, not campus energy or feeder share. The trend retains gold line styling and crosshair; real timestamps and gaps above one hour prevent invented continuous measurements. Long windows retain observed range/median summaries. Blue dashed comparison remains distinct. Sparse observations can legitimately appear as isolated points.

The energy-model and snapshot/archive loader logic remains unchanged. Existing time-zone handling, ambiguity rejection, zero/missing handling, archive scope exclusion, deterministic archive precedence and CSV provenance are preserved. Soda's two device-250 channels remain separate, with value, unit, original timestamp and direct source link; its top summary now counts numeric channels rather than the obsolete legacy device set. Collector and data files are unchanged.

Validation:
- Node suites: 74 passed; Python tests: 18 passed; MEP recovery: 7 passed. Dashboard suite 24/24 rerun after Soda summary fix. Tests protect original checkpoint hashes, compact shell, observed-demand metrics, gold trend and actual gap handling.
- Independent code review: no important findings; no duplicate/missing referenced DOM IDs. Data model and loaders match the previous release.
- Mac Chrome: original and candidate captured at the same 1440×900 viewport; original header/width/card arrangement, palette and typography visually compared. Desktop/month comparison loaded 31/31 files. Mobile 390×844 has 375px client/content width without document overflow. Verified 24-hour filter, comparison, Soda source links, stacked SVG flow and tooltip interaction. Only unrelated Zotero extension connection errors were captured.
- Existing original/current HTML checkpoints, comparison page, manifests and local ZIP are unchanged; their meaning remains original 97c9751 versus saved bright ba3d03c7. Footer retains the saved-versions link.

No publication settings, credentials, other research apps or collection workflows changed.

## Follow-up: readable 24-hour lines and inventory

The user requested a clearer 24-hour line chart and white All Buildings text. The 2026-10-13 audit found four retained Grimes observations in that window: 36.1, 107.6, 113.6 and 116.8 kW, at Oct 12 03:37:33, 13:00:01, 18:45:01 and 20:15:01 Pacific. Their gaps are 9h22m28s, 5h45m and 1h30m. A fixed one-hour cutoff made every point isolated despite the longer observed collection cadence.

For 24 hours only, each building now uses 1.5 times the median positive gap in its retained, non-future observations, bounded between one and six hours, as a visual connection limit. Grimes' retained median gap is 4h45m, resulting in a six-hour limit. The three later observations connect; the 9h22m gap remains open. This is a presentation heuristic, not a claim of continuous measurement or expected collector uptime. No intermediate samples are generated; the caption explicitly explains this. Seven-day and longer summaries retain their previous behavior. All Buildings names and primary table values are white; secondary provenance and status colors remain distinct.

Demand Distribution is unchanged: it counts observations in fixed kW bands, divided by total observed samples. It does not represent energy, elapsed-time, building-category or cost share; variable collection intervals bias that frequency summary.

Validation: Node 75/75, Python 18/18 and MEP 7/7 passed. A new regression covers sparse cadence, the six-hour cap, large-gap breaks, zero readings and the one-hour fallback. Independent review found no important issue. Mac Chrome confirmed the visible line/gap pattern, Davis comparison, seven-day switching, white inventory text, and no mobile document overflow at 390×844. No console warnings or errors were captured for this run. Immutable checkpoints and data/collection files remain untouched.
