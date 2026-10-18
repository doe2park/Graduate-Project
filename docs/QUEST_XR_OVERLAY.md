# Quest WebXR Scan↔BIM overlay (`scan-xr.html`)

Added 2026-10-18. A headset version of the `scan-compare.html` Overlay. You stand inside one captured 360° photo. BIM services are placed with the same registration as the web overlay. A controller acts as an X-ray flashlight. The trigger opens info cards. You jump between recorded capture stations. The page does not change `scan-compare.html`, `scan-photo.html` or `scan-bim.html`, any GLB or Draco bytes, node names, registrations or the `data` branch.

## Open it on a Quest

WebXR requires a secure context (HTTPS). There are two ways to open the page.

1. **Private-LAN HTTPS from the Mac (works before anything is pushed):**
   ```sh
   cd ~/Graduate-Project
   python3 scripts/serve_quest_https.py          # prints  https://<mac-private-ip>:8929/scan-xr.html
   ```
   Connect the Mac and the Quest to the same Wi-Fi. Guest or campus networks with client isolation block this. In Quest Browser, open the printed URL, for example `https://192.168.x.y:8929/scan-xr.html`. The self-signed certificate shows a warning. Choose Advanced → continue, and only for this exact private address. Press **Enter VR** and allow spatial tracking. Ctrl+C on the Mac stops the server.
   - The server binds only the Mac's RFC1918 address. It creates no public tunnel and makes no router, firewall or trust-store changes. It serves GET/HEAD only, gives no directory listings, and allows only site file types. It refuses dot-paths (`.git`, `.env`, `.github-token`), `work/`, `capture-local/`, `node_modules/`, `tools/`, `scripts/`, `tests/`, private exports and symlink escapes.
   - The certificate and key are in `work/quest-https/`, which is gitignored. They are valid for 30 days for that IP and are reused while valid. `--dry-run` prints the URL without serving. `--local` binds 127.0.0.1 for a desktop check. `--port N` changes the port.
   - The headset also needs internet for the pinned CDN modules (three@0.169.0 on jsdelivr, the Draco decoder on gstatic) and for the public meter JSON on the `data` branch.
2. **GitHub Pages (after the owner pushes):** `https://doe2park.github.io/Graduate-Project/scan-xr.html`. Pages is already HTTPS.

URL options: `?capture=2026-09-17` · `&station=<id or index>` · `&style=all` · `&radius=12` (m) · `&layers=all` (include fire piping) or a comma list · `&levels=L1` · `&hires=1|0` · `&xrscale=0.85` · `&foveation=0.7` · `&cell=6` · `&instance=32`.

## Controls

| Quest (Touch controllers) | Action |
|---|---|
| Trigger at a service | World-space info card (canvas texture) + gold highlight; trigger on nothing clears |
| Trigger at the menu | Press a menu button |
| Thumbstick ↑ / ↓ | Jump to the recorded neighbour station in the pointed direction / behind (short fade) |
| Thumbstick ← / → | Snap turn 30° (toggle in menu); there is no smooth locomotion |
| A / X | Lens ↔ All |
| B / Y | Menu: style, opacity ±, cone ±, capture May 6 ↔ Sep 17, photo 2K/4K, snap turn, fire piping, close |
| Grip + stick ↑↓ / ←→ | Opacity / cone angle |

Desktop (testing without a headset): drag = look, wheel = zoom, the mouse aims the flashlight cone, click = trigger, WASD/arrows = walk to a neighbour, `L` = Lens/All, `M` = XR menu panel, Esc = clear card. The toolbar offers capture, station, Lens/All, opacity, cone, 4K photo, Fire piping, Stats and **Enter VR**. Enter VR appears only when `immersive-vr` is supported.

## How it lines up with the web overlay

- The eye, photo sphere and stations stay in the capture's scan frame. The sphere orientation is exactly `scan-photo.html` `stationOrientation`, with no heading offset (the web default). The head is placed on the station (`'local'` reference space; `rigForStation`).
- Element layers use the same GLBs and sidecars as `scan-bim.html` `OVERLAY_LAYER_KEYS`, with the same placement into the BIM world (rotY(π) + `EQUIP_OFFSET`). They sit under one group with the **inverse** of the capture registration. `scan-compare.html` instead converts the photo camera into the BIM frame with `convert()`. The relative eye/photo/BIM geometry is identical, and `tests/scan-xr-core.test.cjs` checks this against `registration-core.js` and the extracted `convert()`.
- Labels: May 6 = *registered (internal residual ≈0.13 m, not surveyed)*. Sep 17 = *PROVISIONAL alignment (not surveyed)*. The label appears in the toolbar pill, the XR menu, a small world-locked tag after every jump, and every info card. Long captions shrink to fit and are never cut. Cards say *Design (BIM) position*, because as-built adjustments are not applied in XR.
- Card tiers come from `ElementCards.elementFeedTier`, the same ladder as the web overlay: explicit feed LIVE/LATEST → MODELLED share → CONTEXT (building meter total, *not this element's own reading*) → NO FEED. A missing meter shows "No reading in this window", never 0.

## Performance choices (Quest)

- Only Level 1 is kept. Fragments whose sidecar `levelKey` is not `L1` are dropped after decode. Fire piping loads only its two L1 chunks (~42 MB) and is opt-in (off by default), like the phone overlay that skips fire.
- `twin/xr-spatial-tier.mjs` builds a runtime-only spatial tier. Batches are bucketed by 6 m XZ cell, not by material/type. Material colour is baked into vertex or instance colour, so one shared shader serves every layer. Geometry that repeats at least 32 times inside one cell stays instanced; the rest merges. Identity is preserved with range → element maps (same semantics as scan-bim), and source bytes and node names are never touched.
- Station radius visibility: only batches whose bounding sphere comes within 12 m of the station (BIM frame) are drawn. This is recomputed on every jump, and frustum culling handles the rest.
- X-ray flashlight: one fragment-shader cone test (`coneOrigin/coneDir/coneCos` uniforms) on the controller ray. Fragments outside the cone are discarded. Lens at 100% opacity switches to opaque rendering with a hard edge, with no blending or transparent sort. Other opacities blend with depth writes on to limit overdraw. All mode is one uniform opacity (default 35%). The photo is never dimmed.
- Unlit shading (no lights, no shadows, no tone mapping). The photo sphere is drawn first without depth test.
- XR uses `setFramebufferScaleFactor(0.85)` and fixed foveation 0.7 (`renderer.xr.setFoveation`, if the runtime supports it). The desktop pixel ratio is capped at 1.5.
- Draco decodes in Web Workers (three's `DRACOLoader` WorkerPool, 2 workers). Layers load sequentially, smallest first, and parser caches are released after batching.
- XR uses the 2048×1024 mobile panorama derivatives by default. The 4K original is a toggle; desktop without XR defaults to 4K. The next three route neighbours are prefetched into the HTTP cache.
- Outside XR, the page renders only after a change (render count measured at 0 per second while idle). In XR it renders every frame, as the compositor requires.

## Desktop measurements (2026-10-18)

These come from headless Chrome on the owner's Mac (Metal ANGLE, GPU, local `http.server`), May 6, default station 83697765, default layers (seven, fire off), 1280×800. Frame rates were not measured, and **these are not Quest numbers**.

| Measure | Value |
|---|---|
| First photo shown | 42 ms after script start (4K, local disk) |
| All seven Level-1 layers ready | 3.6 s |
| Level-1 elements kept | 15,731 (others dropped: 113,188 fragments) |
| Batches built / within 12 m | 611 / 145 |
| Triangles built / within 12 m | 2.75 M / 0.93 M |
| Draw calls in one desktop frame (view-dependent, after frustum culling) | 67 calls, 515 k triangles, 3.6 k line segments |
| JS heap (`performance.memory.usedJSHeapSize`) | ≈ 290 MB |
| Idle renders outside XR | 0 per second |

Per layer (batches / within 12 m / L1 elements / triangles / load ms): lifesafety 65/11/161/38.6 k/234 · equipment 83/17/369/149 k/88 · lighting 123/26/618/117 k/129 · conduit 76/20/1,726/322 k/399 · hydronic 58/12/3,371/1.09 M/789 · plumbing 66/28/1,742/579 k/749 · duct 140/31/7,744/453 k/1,131.

Parameter sweep, same view, desktop draw calls / triangles: 8-instance threshold 183 / 557 k · 32-instance threshold 81 / 557 k · 10 m cells 53 / 696 k · 10 m radius 53 / 476 k. The defaults (6 m cells, threshold 32, 12 m radius) balance draw calls against triangles. On a headset each eye adds its own draw calls unless the runtime uses multiview, and this page does not enable multiview.

## Verified vs unverified

Verified on desktop:
- `node --test tests/scan-xr-core.test.cjs` (10 tests) covers:
  - registration placement against `registration-core.js` and the extracted `scan-compare.html` `convert()`;
  - photo orientation against the scan-photo Three.js formula;
  - neighbour choice identical to `scan-photo.html` `chooseWalkNeighbor` on all 200 real stations × 16 directions;
  - stick hysteresis, snap turn that keeps the head fixed, and head-on-station rig placement;
  - the cone and opacity maths, and menu hit-testing;
  - card honesty for CONTEXT, NO FEED, missing meters and provisional labels;
  - page wiring (pinned three, the same layer set and placement as scan-bim).
- `node --test tests/xr-spatial-tier.test.mjs` (4 tests) covers:
  - the Level filter and spatial cells;
  - baked colours and normals;
  - ray-pick identity for merged, instanced and line batches, including mirrored meshes;
  - exact highlight restore, radius visibility and source-name binding.
- `python3 -m unittest tests/test_serve_quest_https.py` (5 tests) covers:
  - the allowlist and refusals (`.git`, `.env`, `work/` keys, traversal, encoded dot-paths, symlink escape);
  - the private-address guard;
  - a read-only handler (404 / 405, no listing, Permissions-Policy header);
  - a certificate location that is ignored by git.

  A `--dry-run` produced a certificate under `work/quest-https/`.
- `tests/scan-xr-smoke.cjs` runs one headless Chrome pass against the real assets with a meter fixture. It checks:
  - registration, default station, eye on the station, the 4K desktop photo, and no Enter VR without XR;
  - seven layers with zero unidentified fragments and active radius culling;
  - a centre-ray pick that opens a card with an honest tier and caveats;
  - Lens and All rendering differently;
  - a neighbour jump that stays on the recorded route and clears the card;
  - the Sep 17 provisional label and its own registration;
  - the XR menu panel and its buttons;
  - no idle redraws;
  - no overflow at 390 px, with the alignment caveat unclipped;
  - no page errors.

  Run it with:
  `PLAYWRIGHT_MODULE=<playwright or playwright-core> node tests/scan-xr-smoke.cjs`. `XR_SMOKE_LAYERS=equipment,lighting` gives a lighter run. It launches Chrome with `--use-angle=metal --ignore-gpu-blocklist`, because headless WebGL was otherwise disabled on this Mac.

Unverified (no headset session was run):
- Entering `immersive-vr` on Quest Browser: controller events, thumbstick/button mapping, snap turn, the fade, menu and card legibility, and the fixed-foveation effect.
- Quest frame rate, GPU time and memory headroom with seven layers. Load time over Wi-Fi, which is about 78 MB of GLBs plus about 23 MB of sidecar JSON for the default layers.
- Comfort and stereo depth. The photo is monoscopic and drawn at "infinity" (50 m sphere), while BIM is at true depth, so services read as floating in front of the photo surfaces. Only the head position at the station is correct, and leaning away from it shows parallax error. This is inherent to a single 360° photo.
- The Quest network path (client isolation, Mac firewall) and the certificate prompt.

## Limits

- Level 1 only, within 12 m of the station. Each layer still downloads and decodes its whole-building GLB before the other levels are dropped (fire uses its L1 chunks). Loading while inside VR can stall frames, so wait for "Services ready" before pressing Enter VR.
- Positions come from design BIM. As-built adjustments (`twin/as-built.js`) and `?registration=` preview candidates are not applied in XR, and per-station heading offsets stay at zero, as in the web default.
- Cards are trigger-only (no gaze dwell). The meter data refreshes at most once per minute.
- Gaussian and mesh modes, Ghost edges and Align tools from `scan-compare.html` are not part of the XR page.
