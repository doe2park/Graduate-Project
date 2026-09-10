# Registered scan and BIM comparison

`scan-compare.html` is the public comparison entry point. It embeds two `scan-bim.html` panes and applies the accepted rigid transform in `alignment-analysis/accepted-registration.json`. Both panes may drive the camera; position, orientation, field of view and zoom are mapped between frames.

The comparison renders the two original scan GLBs, without Cupix login or its viewer. `scan-assets/provenance.json` records byte counts and SHA-256 hashes. No geometry recompression, node renaming or modification of the machine-written data branch was performed. Only the 217 numeric camera positions are published; raw capture/account inventory is excluded.

Level 1 source interior groups are included for context. Geometry registration is not surveyed accuracy or proof of equipment-to-sensor linkage. Other BIM floors can be displayed, but the scan covers Level 1.

The main BIM viewer offers Show all elements / Hide all elements independently of All floors. It clears the element type restriction, retains the selected floor and loads missing layers sequentially. Hide all during loading stops the queue after the current decode; its late result stays hidden. The comparison toggle includes its interior groups. Its default desktop view loads all layers; touch devices initially load Equipment plus interior and may request all layers explicitly.

The comparison adds approximately 118 MB of static assets; the scan alone is approximately 97 MB. First load depends on network and hardware. Existing BIM assets are reused. Source IDs and JSON bindings remain unchanged.

## Mobile texture budget (2026-09-10)

Touch/narrow devices use scan-assets/mobile texture derivatives (maximum edge 512 px), DPR capped at 1, no MSAA, and one Draco decoder worker. Original texture GPU allocation including mipmaps was approximately 776 MB; derivatives need 81 MB. Downloads fall from 97 MB to 20 MB. Geometry, node identities, UVs and accepted registration are unchanged; the mobile derivative preserves all non-image bufferViews byte-for-byte. Sources remain untouched. Rebuild with scripts/build_mobile_scan.py scan-assets (Pillow), verify with python3 tests/mobile-scan-assets.py. Mobile textures are less detailed. Browser emulation does not establish stability on every physical phone.

WebGL context loss shows a reload action instead of silently leaving a blank canvas. Existing all-element controls remain opt-in on mobile and can increase memory use substantially.
