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
