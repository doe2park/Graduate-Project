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
   - The server binds only the Mac's RFC1918 address. It creates no public tunnel and makes no router, firewall or trust-store changes. It serves GET/HEAD only, gives no directory listings, and allows only site file types. It refuses dot-paths (`.git`, `.env`, `.github-token`), `work/`, `capture-local/`, `node_modules/`, `tools/`, `scripts/`, `tests/`, private exports and symlink escapes. The one opt-in exception is `--gaussian-package <dir>` (see *Gaussian scene mode*): it serves only the `.json`/`.ksplat`/`.ply` files directly inside that one `work/gaussian/.../package` directory.
   - The certificate and key are in `work/quest-https/`, which is gitignored. They are valid for 30 days for that IP and are reused while valid. `--dry-run` prints the URL without serving. `--local` binds 127.0.0.1 for a desktop check. `--port N` changes the port.
   - The headset also needs internet for the pinned CDN modules (three@0.169.0 on jsdelivr, the Draco decoder on gstatic) and for the public meter JSON on the `data` branch.
2. **GitHub Pages (after the owner pushes):** `https://doe2park.github.io/Graduate-Project/scan-xr.html`. Pages is already HTTPS.

URL options: `?capture=2026-09-17` or `?capture=2026-10-18` · `&station=<id or index>` · `&style=all` · `&radius=12` (m) · `&layers=all` (include fire piping) or a comma list · `&levels=L1` · `&hires=1|0` · `&xrscale=0.85` · `&foveation=0.7` · `&cell=6` · `&instance=32` · `&scene=gaussian` · `&splat=mobile|full` · `&eye=1.5` (assumed capture-camera height for the teleport floor, m) · `&gaussian=<manifest path>` (local/private dev hosts only).

## Controls

| Quest (Touch controllers) | Action |
|---|---|
| Trigger at a service | World-space info card (canvas texture) + gold highlight; trigger on nothing clears |
| Trigger at the menu | Press a menu button |
| Thumbstick ↑ / ↓ | Jump to the recorded neighbour station in the pointed direction / behind (short fade) |
| Gaussian: point at the floor, hold stick ↑, release | Teleport to the gold ring (red ring = not allowed, reason shown); pointing at the horizon instead keeps the neighbour-station jump |
| Thumbstick ← / → | Snap turn 30° (toggle in menu); there is no smooth locomotion |
| A / X | Lens ↔ All |
| B / Y | Menu: style, opacity ±, cone ±, capture May 6 → Sep 17 → Oct 18 (cycles), photo 2K/4K, snap turn, fire piping, **Scene Photo ↔ Gaussian**, nearest station, close |
| Grip + stick ↑↓ / ←→ | Opacity / cone angle |

Desktop (testing without a headset): drag = look, wheel = zoom, the mouse aims the flashlight cone, click = trigger, WASD/arrows = walk to a neighbour, `L` = Lens/All, `M` = XR menu panel, Esc = clear card, `G` = Photo ↔ Gaussian, Shift+click = teleport (Gaussian). The toolbar offers capture, station, Lens/All, opacity, cone, 4K photo, Fire piping, **Gaussian**, Stats and **Enter VR**. Enter VR appears only when `immersive-vr` is supported.

## How it lines up with the web overlay

- The eye, photo sphere and stations stay in the capture's scan frame. The sphere orientation is exactly `scan-photo.html` `stationOrientation`, with no heading offset (the web default). The head is placed on the station (`'local'` reference space; `rigForStation`).
- Element layers use the same GLBs and sidecars as `scan-bim.html` `OVERLAY_LAYER_KEYS`, with the same placement into the BIM world (rotY(π) + `EQUIP_OFFSET`). They sit under one group with the **inverse** of the capture registration. `scan-compare.html` instead converts the photo camera into the BIM frame with `convert()`. The relative eye/photo/BIM geometry is identical, and `tests/scan-xr-core.test.cjs` checks this against `registration-core.js` and the extracted `convert()`.
- Labels: May 6 = *registered (internal residual ≈0.13 m, not surveyed)*. Sep 17 and Oct 18 = *PROVISIONAL alignment (not surveyed)*. The label appears in the toolbar pill, the XR menu, a small world-locked tag after every jump, and every info card. Long captions shrink to fit and are never cut. Cards say *Design (BIM) position*, because as-built adjustments are not applied in XR.
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
  - the menu Capture button cycling to Oct 18, its provisional label, own registration and photo, then back to May 6;
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
- Mesh mode and Align tools from `scan-compare.html` are not part of the XR page. Gaussian mode is described below. (The Ghost overlay style was removed on 2026-10-19.)

## Gaussian scene mode (added 2026-10-19, local only)

A scene toggle **Photo ↔ Gaussian** (toolbar button, menu button *Scene*, desktop `G`, URL `?scene=gaussian`). Gaussian mode hides the photo sphere and shows the trained splat scene. GaussianSplats3D 0.4.7 `DropInViewer` is added to the same three.js scene, so it renders inside the WebXR session (verified in the pinned build: `class DropInViewer extends THREE.Group`, `viewer.update()` from a callback mesh's `onBeforeRender` with the per-eye camera). The splat manifest frame is `scan-y-up-metres`, the capture's scan frame, the same frame as the photo stations, as in `scan-compare.html?mode=splat`. The splats therefore sit at the scene root, untransformed. BIM services, the flashlight cone, cards and the radius culling keep the same inverse-registration group as Photo mode. At the default May station, desktop screenshots of Photo and Gaussian mode show the same doors, windows and ceiling lines under identical BIM.

**Honest labels:** *Gaussian · <capture date> · <zone or whole capture> · experimental appearance, not surveyed*. Oct 18 adds *provisional alignment* and *local preview, unpublished*. The label shows in the toolbar caption, the XR menu, the world-locked tag and the button title. The capture's alignment caption (registered or PROVISIONAL) is unchanged next to it.

**Scenes.**
- Default is the published May 6 scene, `scan-assets/gaussian/2026-05-06/viewer.json`.
- No Gaussian exists for Sep 17. The toggle says so (*No Gaussian scene for Sep 17, 2026 · staying in Photo*) and stays in Photo. Oct 18 also stays in Photo unless a local override is loaded.
- `?gaussian=<manifest path>` is honoured only on dev hosts: `localhost`, `127.0.0.1`, `[::1]`, `*.localhost` and private RFC1918 IPv4 (10/8, 172.16/12, 192.168/16). It is never honoured on `doe2park.github.io`. The path must be relative, `[A-Za-z0-9_./-]` ending in `.json`, with no `..`, no leading `/`, no `//` and no dot-segments (`ScanXRCore.gaussianOverride`). The manifest must also be same-origin, `experimental-trained`, `scan-y-up-metres`, for this building, and its `capture` must equal the capture shown. Asset files must be sibling `.ply`/`.ksplat` files. With `?scene=gaussian`, an override and no `?capture`, the page opens the override's capture.
- When a zoned manifest (`zone.stations`) loads, the start position is its `initialStation`. Stations outside the zone show *outside the trained zone, appearance missing*.

### Open on the Quest

On the Mac (same Wi-Fi as the headset):

```sh
cd ~/Graduate-Project
python3 scripts/serve_quest_https.py --gaussian-package work/gaussian/2026-10-18/l1-a/20261019T074640Z/package
# prints  https://<mac-private-ip>:8929/scan-xr.html
#         https://<mac-private-ip>:8929/scan-xr.html?scene=gaussian&gaussian=work/gaussian/2026-10-18/l1-a/20261019T074640Z/package/viewer.json
```

- **May 6 Gaussian (published):** `https://192.168.x.y:8929/scan-xr.html?scene=gaussian`. After a push it is also at `https://doe2park.github.io/Graduate-Project/scan-xr.html?scene=gaussian`.
- **Oct 18 zone l1-a, auditorium (local, unpublished):** `https://192.168.x.y:8929/scan-xr.html?scene=gaussian&gaussian=work/gaussian/2026-10-18/l1-a/20261019T074640Z/package/viewer.json`. This needs the `--gaussian-package` flag above. Without it the server refuses `work/`, and the page falls back to Photo with a note. The flag accepts only a directory under `work/gaussian/` that contains `viewer.json`. It serves only the `.json`/`.ksplat`/`.ply` files directly inside that directory. The certificate, key and other runs stay unreachable. The dry run prints the exact URL.
- Wait for the splat count in the caption and *Services ready* before **Enter VR**.

### Locomotion

- Station jumps are unchanged (stick ↑/↓ toward a recorded neighbour; the *Nearest station* menu button). In Gaussian mode no photo is downloaded.
- Point-and-teleport works in Gaussian mode only, because a 360° photo has one optical centre:
  - Hold stick ↑ to aim: the controller ray meets an invisible horizontal floor plane `eye` (default 1.5 m) below the current eye height. A gold ring marks the target.
  - Release to teleport with a short black fade. The eye height is kept, and no smooth locomotion is added.
  - A red ring means the target is not allowed, and the page shows the reason. Targets must be ≤ 8 m away, ≤ 6 m from a recorded station (a proxy for trained coverage) and, for a zoned scene, inside the zone bounds + 1.5 m.
  - Pointing at or above the horizon falls back to the neighbour-station jump.
  - BIM radius culling re-centres on the landing point. The station picker shows the nearest station.
- Snap turn is unchanged. Desktop: Shift+click on the floor.
- The floor height is an **assumption** (capture-camera height), not a measured floor. On sloped floors (the auditorium rake) the ring can sit above or below the visible floor.

### Performance choices

- XR uses the manifest `mobileFile` by default: 350k Gaussians, SH0, 19.6 MB. The device decision uses `immersive-vr` support, as for the 2K photo. Desktop uses `file` (1M, 48 MB KSplat, SH2). `&splat=mobile|full` forces a file. XR caps any scene at 1M splats, and entering a session switches the active SH degree to 0.
- `sharedMemoryForWorkers:false`, so the sort runs in the library's Web Worker with transferable buffers and needs no SharedArrayBuffer/COOP/COEP (GitHub Pages sends neither). The sort is CPU-based (`gpuAcceleratedSort:false`), with `halfPrecisionCovariancesOnGPU`, `freeIntermediateSplatData` and a static scene.
- The library starts a sort from the camera's *local* pose. Station jumps, teleports and snap turns move the rig instead, so the page forces one sort after each rig move.
- The photo texture is disposed in Gaussian mode. One splat scene stays resident (hidden, not sorted and not drawn in Photo mode) and is disposed on a capture change.
- Splats draw as one transparent pass without depth test (renderOrder −10), before the services. The opaque 100% Lens shortcut is therefore disabled in Gaussian mode, and services stay blended with depth writes.
- Framebuffer scale 0.85 and fixed foveation 0.7 are unchanged. Outside XR, rendering stays on demand: the page draws while a worker sort is in flight, then stops.

### Desktop measurements (2026-10-19, headless Chrome, Metal ANGLE, local `http.server`, 1280×800, `&splat=mobile&layers=equipment,lighting`; not Quest numbers)

| Measure | May 6 (published) | Oct 18 l1-a (local) |
|---|---|---|
| Gaussian file / splats kept | mobile.ply / 350,000 | mobile.ply / 350,000 |
| Splat load (fetch + parse + build) | 0.75–1.17 s | 0.91 s |
| Scene ready after navigation (wall) | 1.2–1.8 s | 1.4 s |
| Draw calls / triangles in one frame (splats are 1 instanced call) | 19 / 750 k | 8 / 701 k |
| JS heap with two service layers | ≈ 400–411 MB | ≈ 400 MB |
| Idle renders outside XR after the sort lands | 0 per second | 0 per second |
| Photo → Gaussian re-toggle (scene resident) | 3–4 ms | 3 ms |

For comparison, the Photo page with seven layers measured ≈ 300 MB heap. The full 48 MB desktop KSplat and the Quest itself were not measured.

### Verified vs unverified (Gaussian)

Verified on desktop:
- `node --test tests/scan-xr-core.test.cjs` (16 tests) adds:
  - manifest/file choice (mobile in XR, SH0, budgets, sibling assets only);
  - override validation (loopback and RFC1918 only; public host rejected; traversal, absolute, scheme, `//` and dot-segment paths rejected);
  - Photo/Gaussian resolution (May published, Sep none with a reason, Oct only through an override);
  - labels;
  - teleport floor hits and limits, including all eight headings at the real May default station;
  - page wiring, plus the pinned package's `DropInViewer` API in `tools/node_modules`.
- `tests/test_serve_quest_https.py` (6 tests) adds the opt-in package allowlist.
- `tests/scan-xr-smoke.cjs` runs a short Gaussian pass. It checks:
  - the May mobile scene: 350k splats, SH0, photo hidden, no photo download, `crossOriginIsolated` false;
  - a bogus `?gaussian=../secret.json` being ignored;
  - BIM placement identical to Photo mode;
  - splats covering the view;
  - no idle redraws;
  - a 2.15 m teleport that keeps eye height, with the BIM radius following;
  - the aim-above-horizon refusal;
  - station jumps;
  - menu toggles Photo ↔ Gaussian;
  - Sep 17 staying in Photo with the reason, and the old scene disposed.

  `XR_SMOKE_OCT=1` also loads the local Oct 18 zone through the override (zone, provisional and local-preview labels, start inside the zone). `XR_SMOKE_GAUSSIAN=0` skips the Gaussian pass.

Unverified (no headset run):
- `DropInViewer` stereo rendering on Quest Browser. The library computes the splat focal length from the page canvas size, not the per-eye viewport. The projection stays consistent, but the 0.3 px kernel and the screen-space size cap are in canvas pixels.
- Quest frame rate and memory with 350k splats plus services. Sort latency on the Quest CPU worker, which may show a brief wrong-order shimmer after a teleport or turn.
- Teleport comfort and the floor-height assumption. Thumbstick aim and release on real controllers.
- Wi-Fi load time of 19.6 MB.
