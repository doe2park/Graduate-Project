# Campus Energy Dashboard backups

Before: 97c97514e96f28c0e067045e6d3e67ed58d646b3. Current checkpoint: ba3d03c7feb41fc93be2219d9af8cb83b2b13dc1. Both HTML files are byte-identical Git extractions, not edited previews. SHA-256 and byte lengths: energy-dashboard-versions.json (local backup: manifest.json).

The previews use the latest existing public campus_energy.json and campus_energy_history.json; they are NOT frozen at either commit date. The preserved current version also reads existing public daily archives. Pages refresh public data every minute. No external writes or collection jobs are triggered. CSV export downloads locally. Root-level copies preserve existing relative navigation links, which open current companion pages.

Original interpretation limitations: instantaneous kW multiplied by 24 is an estimate, not measured daily energy. Feeder/group sums may overlap; timestamps and coverage may differ. Cost, CO2 and anomaly outputs are model/source estimates, not verified savings or equipment telemetry. Original code is intentionally unmodified.

Restoration: tell the assistant which version and which parts to restore (for example original palette or current filters). Restore only selected sections into campus-energy-dashboard.html, then test and preview before publishing. Do not replace the operating page or data branch automatically. Full rollback is possible by copying the chosen exact HTML onto campus-energy-dashboard.html, but has NOT been performed and requires a separate explicit request. Keep these checkpoint files unchanged.

The local backup folder also preserves the previously downloaded public JSON files under their original names; these are audit-time source files, not necessarily contemporaneous with the original UI. Inspect each JSON generated_at/timestamp to determine its actual date. Neither preview is wired to those local snapshots.
