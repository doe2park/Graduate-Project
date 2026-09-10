# Registered scan and BIM comparison

`scan-compare.html` is the public comparison entry point. It embeds two `scan-bim.html` panes and applies the accepted rigid transform in `alignment-analysis/accepted-registration.json`. Both panes may drive the camera; position, orientation, field of view and zoom are mapped between frames.

The comparison renders the two original scan GLBs, without Cupix login or its viewer. `scan-assets/provenance.json` records byte counts and SHA-256 hashes. No geometry recompression, node renaming or modification of the machine-written data branch was performed. Only the 217 numeric camera positions are published; raw capture/account inventory is excluded.

Level 1 source interior groups are included for context. Geometry registration is not surveyed accuracy or proof of equipment-to-sensor linkage. Other BIM floors can be displayed, but the scan covers Level 1.

The main BIM viewer offers Show all elements / Hide all elements independently of All floors. It clears the element type restriction, retains the selected floor and loads missing layers sequentially. Hide all during loading stops the queue after the current decode; its late result stays hidden. The comparison toggle includes its interior groups. Its default desktop view loads all layers; touch devices initially load Equipment plus interior and may request all layers explicitly.

The comparison adds approximately 118 MB of static assets; the scan alone is approximately 97 MB. First load depends on network and hardware. Existing BIM assets are reused. Source IDs and JSON bindings remain unchanged.
