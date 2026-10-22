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

## Controls (redesigned 2026-10-22 after the owner's first headset test)

The first test found the controls clumsy: the stick only stepped forward/back to the next route neighbour, the 6×2 menu had too many small buttons, the opacity steps were fiddly, and it was not visible where a controller pointed or where a click would land. The redesign gives each hand one job.

| Quest (Touch controllers) | Action |
|---|---|
| **Left stick ↑, hold** | Aim: a dotted arc runs from the left controller to a target marker (ring on the floor, a pillar up to the photo centre) with a label, *Capture 37 · 9.4 m*. Red means not allowed, and the label gives the reason. |
| **…release** | Go there with a short black fade. **Pull the stick back** instead to cancel. |
| Left stick ↓ | Step back one recorded station along the route. |
| **Left or right stick ← / →** | Snap turn 30° about your head. There is no smooth locomotion. |
| **Right controller** | Flashlight. The X-ray cone follows its ray. |
| **Right trigger** | Info card on the element the ray highlights. Trigger on nothing clears the card. |
| Right stick ↑ / ↓ | Widen / narrow the flashlight cone, 3° per push (4–30°). |
| Either trigger on the menu | Press the **highlighted** button. A click acts only on the button the ray is on, and the panel background does nothing. |
| A / X | Lens ↔ All. |
| B / Y | Open / close the menu. It also closes 1.5 s after every ray has left it. |

**Where the target is (photo mode).** Movement stays discrete, between capture stations (`ScanXRCore.stationTarget`).
1. If the left ray meets the assumed floor (eye height − 1.5 m) within 15 m, the target is the station nearest that floor spot, provided it is within 2.5 m. Pointing at your own feet says *You are here*.
2. Otherwise the target is the station whose photo centre is within a 30° cone of the left ray, up to 15 m. Stations are ranked by angle. A level ray down a corridor therefore picks the far station, and a ray tipped down picks a nearer one. Stations more than 1.5 m above or below (other floors) are ignored. So are stations the route graph does not connect, and stations whose recorded route is much longer than the straight line, which are probably behind a wall (detour penalty).

Gaussian mode: the target is a free teleport point on the floor (≤ 8 m, near the captured positions, inside the zone; unchanged rules). Pointing at the horizon falls back to the station cone. MR mode has no teleport: the BIM is aligned to the real building, and you walk.

**Pointing feedback.** Each tracked controller draws a tapered laser ray and a reticle where it hits:
- on a menu button: the ray and reticle turn gold, the button turns gold and grows, and a short haptic tick plays;
- on a service element: an amber reticle. This uses a throttled raycast for the flashlight hand. The interval adapts to the cost, at 20× the measured cast time and between 120 and 800 ms. `&hover=0` turns it off if it costs frames. On the Mac, one cast measured 0.2 ms (median, seven layers, headless Chrome; `report.hoverRayCostMs`). This is not a Quest number;
- on the assumed floor: a flat white ring.

The haptics use `gamepad.hapticActuators[0].pulse()`, with `vibrationActuator.playEffect()` as a fallback. Whichever exists is used.

**Menu (B/Y).** The panel is 0.64 × 0.40 m, about 0.8 m in front of you, 0.15 m below eye height and turned toward your head. It rides with you through jumps and snap turns.
- Main page, five large buttons: **Capture** (cycles the published captures) · **Lens / All** · **Photo / Gaussian** · **Recenter** (nearest capture) · **More ▸**.
- **More ▸:** Back · **Flashlight: right hand / both hands** (both: the left controller also carries a cone, as a second cone in the same shader) · **Opacity** (fixed at Lens 70 % and All 35 %; the button cycles Lens 50 → 70 → 90 %) · Photo 2K/4K · **Exit VR** · eight layer toggles (a layer that is not loaded loads on demand, and frames can stutter).

A head-locked status line, about 15° below the view centre, shows messages in the headset, because the page's status pill is not visible in VR. The world-locked tag after each jump repeats the alignment caveat and a one-line control hint. `&hands=both` starts with both flashlights.

**Single controller or hand tracking.** A lone controller does both jobs: its stick aims and turns, and its ray lights. With hand tracking (no sticks), pinch is the trigger. The laser, hover and menu work, but there is no point-and-go.

**Desktop (testing without a headset).**
- Looking and moving: drag = look, wheel = zoom, WASD/arrows = walk to a neighbour, `Q`/`E` = turn 30°.
- Pointer: the mouse aims the flashlight cone. Hovering the menu highlights buttons like a controller ray, and click = trigger.
- **Shift + move** previews point-and-go (arc, marker, label). **Shift + click** goes.
- Keys: `L` = Lens/All, `M` = menu, `G` = Photo ↔ Gaussian, Esc = clear card.
- The toolbar keeps capture, station, Lens/All, opacity and cone sliders, 4K photo, Fire piping, **Gaussian**, Stats and **Enter VR**. Enter VR appears only when `immersive-vr` is supported.

MR mode keeps its alignment controls (below), and gains the same laser, reticle, panel hover highlight and haptics.

### 5-minute headset checklist (LAN test, before anything is pushed)

| min | Check | Pass if |
|---|---|---|
| 0–1 | Mac: `python3 scripts/serve_quest_https.py` → Quest Browser opens the printed `https://<mac-ip>:8929/scan-xr.html` → wait for *Services ready* → **Enter VR** | Both lasers are visible; the reticle sits on the floor or on services |
| 1–2 | **Move far:** point the left controller down the corridor at a distant spot, hold stick ↑ | The arc and marker land on a station 6–15 m away, with the label *Capture N · x m*; releasing jumps there with a fade |
| 2–3 | Point at the floor next to a nearby station, hold ↑, release; then pull ↑ and back to cancel | The floor ring snaps to that station; the cancel does nothing |
| 3   | **Snap turn:** left stick ←/→, then right stick ←/→ | 30° per push; you stay on the photo centre |
| 3–4 | **Flashlight:** sweep the right controller across the ceiling; right stick ↑/↓; **info card:** right trigger on a duct or light | Services appear only inside the cone and the cone width changes; the card opens on the element the amber reticle was on |
| 4–5 | **Menu:** B/Y → hover each button (gold, haptic tick) → Lens/All → More ▸ → Flashlight: both hands (both cones light) → Back → point away | Every click acts on the highlighted button; the panel closes about 1.5 s after the rays leave it |

Record any lag while sweeping the flashlight. If services stutter, retry with `&hover=0` and note the difference.

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
- `node --test tests/scan-xr-core.test.cjs` (10 tests at the time; 19 since the 2026-10-22 controls) covers:
  - registration placement against `registration-core.js` and the extracted `scan-compare.html` `convert()`;
  - photo orientation against the scan-photo Three.js formula;
  - neighbour choice identical to `scan-photo.html` `chooseWalkNeighbor` on all 200 real stations × 16 directions;
  - stick hysteresis, snap turn that keeps the head fixed, and head-on-station rig placement;
  - the cone and opacity maths, and menu hit-testing;
  - since 2026-10-22, the menu layout model (≤ 5 main buttons, at least 0.18 × 0.09 m each, ids, every centre hits its own button, gaps and header miss); controller roles (left moves, right lights, both hands, a lone controller); stick intents; hold/release/cancel aiming; 12 snap turns returning to the start; and `stationTarget` (floor spot, 30°/15 m cone, a level ray picking the far station, other floors, an unconnected station, the route-detour penalty, refusals, Gaussian zone indices, arc and labels). It also checks that, on the real May 6 manifest, pointing at each reachable station 1–15 m from the default station selects it, at least 60 % of the time and for at least one station more than 6 m away;
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
  - the XR menu panel and its buttons. Since 2026-10-22 the test checks 5 main buttons about 0.81 m from the eye; hover highlight under the ray; a click acting on the highlighted button; a header click doing nothing; the More page (both-hands flashlight, opacity cycle 90/50/70 %, a layer off and on, Back, Exit);
  - point-and-go (2026-10-22): a level centre ray at a non-neighbour station 6–14 m away selects it with *Capture N · x m*. The jump lands the eye on it; in the run on 2026-10-22, 88 → 93 covered 13.4 m in one jump. A floor spot picks the station beside it, pointing up is refused, and a snap turn keeps the eye fixed. In Gaussian mode, the floor gives *Teleport · x m*, and a level ray falls back to a station;
  - no idle redraws;
  - no overflow at 390 px, with the alignment caveat unclipped;
  - no page errors.

  Run it with:
  `PLAYWRIGHT_MODULE=<playwright or playwright-core> node tests/scan-xr-smoke.cjs`. `XR_SMOKE_LAYERS=equipment,lighting` gives a lighter run. It launches Chrome with `--use-angle=metal --ignore-gpu-blocklist`, because headless WebGL was otherwise disabled on this Mac.

### Black VR view on 2026-10-22 and the immersive smoke

After the MR prototype (81afd8fb) and the controls redesign (296f0951) were deployed, Enter VR on a Quest 2 showed only black. Both commits were reverted on `main`. With matching files, both revisions render the photo in an emulated immersive session. The black view is reproduced when the new page runs with the previous `twin/xr-core.js`. In that case `X.controllerRoles is not a function` is thrown in the first XR frame (`xrInput` → `roles`). three.js requests the next XR frame only after the animation callback returns, so one exception stops rendering for the whole session. GitHub Pages serves every file with `Cache-Control: max-age=600` and the helper scripts were not versioned. A browser that had loaded the previous version within 10 minutes could therefore pair the new page with the cached older core. This is the most likely cause. It has not been confirmed on the headset, because no headset log exists.

Fix (branch `fix/vr-black-screen`):
- The helpers are loaded as `twin/xr-core.js?v=2` (also `overlay-visibility.js`, `mr-align.js`).
- `ScanXRCore.API` must equal the page's `XR_CORE_API`. On a mismatch the page hides Enter VR/MR and asks for a reload. Bump both, and the `?v=`, whenever the xr-core exports change.
- The per-frame XR work (input, placement, MR tracking) runs in `xrFrameSafe()`. An exception there is counted (`xrInspection().xr.frameErrors`), logged once and shown in the headset, and rendering continues.

`tests/scan-xr-immersive-smoke.cjs` presses Enter VR under Meta's Immersive Web Emulation Runtime (`iwer@2.5.0`, emulated Quest 2, two Touch controllers). It reads the XR framebuffer inside an XR frame and asserts the following: the view is not black, the photo sphere is visible, the page loop keeps rendering, and there are no page errors or caught frame errors. It runs these checks after entering, during an aim preview, with the menu open and with hand tracking. `XR_SMOKE_CORE_REV=<rev>` serves an older `twin/xr-core.js`, which models the stale cache. `XR_SMOKE_GIT_REV=<rev>` tests an older page. Without `IWER_BUILD` the test is skipped; set `XR_IMMERSIVE_REQUIRED=1` to make it fail instead.

```sh
npm install --prefix /tmp/iwer-tools --ignore-scripts --save-exact iwer@2.5.0
PLAYWRIGHT_MODULE=<playwright-core> IWER_BUILD=/tmp/iwer-tools/node_modules/iwer/build/iwer.min.js node tests/scan-xr-immersive-smoke.cjs
```
Emulation renders into the page canvas. It has no Quest compositor, no opaque XR framebuffer and no foveation, so a passing run is not a headset test.

Unverified for the 2026-10-22 controls (desktop emulation only, no headset run):
- How the left and right roles map to `handedness` on real Touch controllers, and the stick hold/release feel. The 0.3 release threshold may need tuning against stick drift.
- Haptic pulses on Quest Browser.
- The legibility of the laser (a tapered 2–4.5 mm cylinder), the reticle and the 0.64 m menu at 0.8 m.
- The menu auto-close after 1.5 s.
- The frame cost of the throttled element-hover raycast on the Quest CPU (`xrInspection().controls.hoverCastMs`).
- Whether the floor-spot snap (2.5 m) and the 30° cone pick the intended station in real use.

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

- Since 2026-10-22, the left stick uses the same point-and-go as Photo mode (see *Controls*). The menu button is *Recenter* (nearest station). In Gaussian mode no photo is downloaded.
- Point-and-teleport works in Gaussian mode only, because a 360° photo has one optical centre:
  - Hold the left stick ↑ to aim: the controller ray meets an invisible horizontal floor plane `eye` (default 1.5 m) below the current eye height. A gold dotted arc and ring mark the target, with *Teleport · x m*.
  - Release to teleport with a short black fade. The eye height is kept, and no smooth locomotion is added.
  - A red ring means the target is not allowed, and the page shows the reason. Targets must be ≤ 8 m away, ≤ 6 m from a recorded station (a proxy for trained coverage) and, for a zoned scene, inside the zone bounds + 1.5 m.
  - Pointing at or above the horizon falls back to the station cone (`stationTarget`, zone stations only).
  - BIM radius culling re-centres on the landing point. The station picker shows the nearest station.
- Snap turn: either stick ←/→. Desktop: Shift+move previews, Shift+click goes.
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

## MR passthrough mode (`?mode=ar`, added 2026-10-21, local prototype)

Walk in the real building wearing the Quest and see the BIM services (ducts, sprinkler piping, plumbing …) *through* the real ceiling and walls. There is no 360° photo and no capture registration in this mode. The page asks for an `immersive-ar` session. The background is transparent, so Quest Browser shows the passthrough camera image. Only service layers are drawn, and they are placed by a **manual alignment** that you make on site by touching 2–5 known landmarks. Every label says **manual alignment, not surveyed**. Positions are design (BIM) positions.

URL options: `?mode=ar` · `&area=l1-auditorium-foyer|l1-east-entrance` · `&range=near|room|all` · `&layers=<comma list>|all` · `&tip=<cm>` (tip-ball offset, default 3) · `&xrscale=` / `&foveation=` as in VR.

Files: `scan-xr.html` (MR block, `MODE_AR`), `twin/mr-align.js` (pure maths, `window.MRAlign`), `buildings/grimes/mr-landmarks.json` (curated landmarks, generated by `scripts/derive_mr_landmarks.mjs --write`), `tests/mr-align.test.cjs`, MR pass in `tests/scan-xr-smoke.cjs`.

### What you see

- Default layers (to fit the Quest 2 budget): **fire piping, ductwork, plumbing**. The other five layers can be toggled from the panel (*Layers ▸*). Loading a layer while inside MR can stutter for a few seconds.
- Distance fade per fragment, with the presets from `twin/overlay-visibility.js`: **Room** (default; full to 8 m, gone by 14 m), **Near** (3 → 6 m), **All** (no fade). Batches wholly beyond the fade are not drawn. The cull set is recomputed when you have walked more than 0.5 m. Ceilings are never occluders, because there is no BIM ceiling or wall geometry in this mode: the real ceiling is the passthrough. Wall occlusion is **not** implemented in MR (see Limits).
- **Lens** (default) is the X-ray window: inside the controller cone, services are at full opacity; outside, they are faint (12 % of the opacity). **All** draws every service in range at a uniform opacity. A/X toggles between them. Grip + stick changes opacity / cone (MR only; VR now has a fixed opacity and the right stick for the cone).
- Trigger on a service (once aligned) opens the same honest info card as VR. Its caption is *MR · <area> · manual alignment, not surveyed · RMS x cm*.

### Alignment UX

1. **Area.** Choose the area on the 2D page before entering (select *Area*), or with the panel button *Area*. The two curated areas are both Level 1. A landmark file area also sets the BIM level that is loaded.
2. **Touch the landmarks.** The world-locked panel (B/Y toggles it) shows the current point, its description and a small BIM plan with the points (A, B, C …) and the checks (S1, G1 …). The plan is in BIM orientation, *not* your heading. A small **gold ball 3 cm in front of the controller's ray origin** is the touch tip (`&tip=<cm>` changes the offset). Put the ball on the real point and pull the trigger.
   - `xz` points (column faces, wall corners, door-frame edges) are vertical edges. Touch them **at any height**; only their plan position is used.
   - The `y` point (*Floor*) fixes the height. Touch the floor. Without it, the Quest's own floor estimate is assumed to be the BIM Level 1 datum (5.25 m), and the panel says so.
   - **Skip point** if a landmark is hidden or not exposed. **Redo last** goes back one point. **Solve now** fits with what you have (at least 2 plan points).
   - **Grip + trigger** uses the hit-test point on a real surface (Quest's planes/mesh) instead of the tip, if the session granted `hit-test`. A cyan ring shows it while grip is held. This is meant for points you cannot reach, such as a ceiling device for a check, or the floor.
3. **Solve.** Yaw about the vertical axis + translation. There is no tilt (both frames are gravity-aligned) and no scale. Plan points are fitted by closed-form least squares (the same estimator as `registration-core.js fitYawTranslation`). Height comes from the mean floor / 3D offset. After the second plan point a **live preview** shows the services, and it updates with each extra point.
4. **Review.** The panel shows *RMS x cm · worst <id> y cm · n points · height source* plus warnings (only 2 points; span < 3 m; height assumed). With 3+ plan points a leave-one-out error per point is computed (`fit.leaveOneOut`, in `xrInspection().mr`); a point much worse than the others was probably touched at the wrong place. Use **Redo last** or **Re-align**.
5. **Accept + save.** The alignment is stored in `localStorage` (`grimes-mr-alignment/1`, written only through `MRAlign.saveRecord`). If the session granted `anchors`, an XR anchor is created at the touched points' centroid, the alignment is stored *relative to the anchor*, and the page asks for a persistent handle. Each frame the BIM follows the anchor's pose, which absorbs tracking corrections.
6. **Fine-tune.** Panel *Nudge: on* → thumbstick moves the BIM 1 cm per push in your heading (forward/back/left/right). Grip + stick ←/→ turns it 0.25° about your head; grip + stick ↑/↓ raises or lowers it 1 cm. *Step* switches to 5 cm / 1°. Every nudge is saved and marked *nudged* in labels and the record.
7. **Re-entering.** If a saved record has a persistent anchor, the page calls `restorePersistentAnchor`, and the BIM reappears where it was once the anchor is found. **Without an anchor** the saved alignment is in the old session's `local-floor` frame. It is applied with a warning: it is valid only if MR was started from the same spot and heading, so check one landmark or **Re-align**. A tracking-origin reset (holding the Meta button to recentre) invalidates an un-anchored alignment, and the panel says so.
8. **Checks.** Panel *Check points* cycles through the area's checks (sprinkler heads, a 24×24 diffuser). A gold ring marks the BIM position on the ceiling, and that element's layer is loaded if needed. Hold the tip **directly below** the real device (plumb) and trigger, or use grip + trigger to hit the ceiling at its centre. The panel reports *real is N cm from BIM (BIM x, z)*. Each check is appended to `localStorage` `grimes-mr-checks/1`; *Check log* on the 2D page downloads it as JSON.

### Landmarks (`buildings/grimes/mr-landmarks.json`)

These are BIM-derived candidates, **not verified on site**. `scripts/derive_mr_landmarks.mjs` reads GLB node names and decodes the Draco geometry **in memory** (nothing is re-encoded or written back). It takes each point from one element's bounding box in the BIM viewer world (rotY(π) + `EQUIP_OFFSET`). The test `tests/mr-align.test.cjs` regenerates the file and requires it to be identical.

- **`l1-auditorium-foyer` (default): Level 1 foyer outside the auditorium doors (open ceiling).** This is inferred as the likely Oct 18 open-ceiling check area. Evidence: a row of exposed **upright** VK300 heads at BIM z ≈ −5.96 (the concealed pendent heads elsewhere sit below ceilings), between two round concrete columns, directly north of the raked auditorium floor (Floor 128625, z −22.1 … −7.15). Points:
  - A: east round column 130415, face toward the other column;
  - B: west round column 130413, face toward A (8.3 m apart);
  - C: outside corner of west wall 14933;
  - D: outside corner of east wall 14925;
  - F: floor.

  Checks: upright heads S1 278545 (centre of the row), S2 278541 and S3 278537; and the 24×24 supply diffuser G1 15365 (mark 672). In BIM, G1 is ~2.2 m north of the foyer's north wall, so it may be in the next room.
- **`l1-east-entrance`: east double glass door 140** ("EXTERIOR, CR, PANIC"). Points:
  - A, B: inside faces of the two door-frame mullions (1.83 m apart);
  - C: outside corner of the small closet;
  - D: the next doorway jamb;
  - E: the corridor's north-wall end, ~9.7 m in (the far point that fixes the heading);
  - F: floor.

  Checks: concealed pendent head 279994 (0.75 m inside the door) and 24×24 supply diffusers 15169 (mark 55) and 15165 (mark 33).

Which real corner a bounding box represents (finish face vs structure layer) is uncertain by a few cm. The round-column points depend on judging the "facing" point. Skip any landmark that is not exposed. To add or change an area, edit `AREAS` in the script, run `node scripts/derive_mr_landmarks.mjs --write`, and run the tests. `--list` prints candidate elements near the east door.

### Open it on the Quest (owner steps)

1. On the Mac (same Wi-Fi as the headset, no client isolation):
   ```sh
   cd ~/Graduate-Project
   python3 scripts/serve_quest_https.py
   # prints  https://<mac-private-ip>:8929/scan-xr.html
   #         https://<mac-private-ip>:8929/scan-xr.html?mode=ar      <- MR
   ```
2. On the Quest: Settings → Physical space → **Space Setup**. Do it at least once in the area. On Quest 3 this also gives the room mesh and planes for hit-test. On Quest 2 the planes are the ones drawn manually. A small boundary is fine. Whether the boundary interrupts a 10–15 m walk in passthrough was not tested. If it does, use a larger boundary.
3. Quest Browser → open `https://<mac-private-ip>:8929/scan-xr.html?mode=ar`. Certificate warning → *Advanced → Proceed* (this exact private address only).
4. Wait for *Services ready · Ductwork, Plumbing, Fire piping* (≈ 63 MB over Wi-Fi), then press **Enter MR**.
5. **Permission prompts.** Quest Browser asks before an immersive session to allow the site to use your physical surroundings / spatial tracking. Choose **Allow**. A separate **spatial data** permission may be asked for plane / mesh / anchor features. If you deny it, MR still runs, but hit-test, anchors or persistence will be missing (the panel's events list `session features`). To undo a choice: Quest Browser → Settings → Site permissions. The exact prompt wording was not observed (no headset run).
6. If **Enter MR** is missing, the browser does not offer `immersive-ar`. The note line says *this browser offers no immersive-ar (passthrough) session*. Update Quest Browser, or check that the page is HTTPS on the private IP. The normal photo page (`scan-xr.html` without `?mode=ar`) shows an *Enter MR* shortcut wherever `immersive-ar` exists.
7. Ctrl+C on the Mac stops the server. Exiting MR ends the session: the alignment then belongs to that session unless it was anchored.

### 10-minute test protocol (Level 1 foyer outside the auditorium doors)

Record everything in a table: date, headset (Quest 2/3), area, points used, RMS, worst point, leave-one-out of the worst, height source, each check offset (cm, BIM x/z), nudges.

| min | Step |
|---|---|
| 0–2 | Stand in the foyer between the two round columns. Confirm on site that A–D exist and are exposed; note any that are not (skip them in step 2). Open `?mode=ar`, area *foyer*, wait for *Services ready*, **Enter MR**, allow the prompts. |
| 2–5 | Panel shows *Point A*. Touch A, B, C, D with the gold ball (any height; hold still, trigger), then the floor (F). Read *RMS / worst / warnings*. **Target: RMS ≤ 3 cm, worst ≤ 5 cm.** If one point is far worse, *Redo last* or *Re-align*. Optionally redo with only 3 points (A, B, F) to see the effect. *Accept + save*. |
| 5–8 | *Check points* → **S1** (upright head, centre of the exposed row): stand under the real head, hold the ball plumb below its deflector, trigger. Note *real is N cm (BIM x, z)*. Repeat for **S2**, **S3**. Then **G1** (24×24 diffuser, mark 672): plumb under its centre, or grip + trigger on the ceiling at its centre. Note whether G1 is actually in the foyer. Look up with **Lens**: do the BIM branch lines run to the real heads? |
| 8–9 | Walk ~10 m to the far column and back; re-check S1. A growth of the offset = tracking drift or heading error. Try **Nudge** (1 cm / 0.25°) to null S1, and note the nudge needed. |
| 9–10 | Exit MR, re-enter: anchored → the BIM should come back in place (re-check S1). Not anchored → expect the warning. On the 2D page press *Check log* (Quest Browser saves the JSON to the headset's Downloads) and keep it with the notes; the log lives only in that browser's storage. |

How to read the result: the landmark RMS says how consistently the touches agree with the design positions; it is not survey accuracy. A check offset mixes alignment error, tracking drift and the **design-vs-installed** difference of that device. At Grimes, lights and diffusers already differ from BIM by 0.1–0.2 m in places (`docs/REGISTRATION_WORKBENCH.md`). Report them as such, never as surveyed deviations.

### Quest 2 vs Quest 3

| | Quest 2 | Quest 3 |
|---|---|---|
| Passthrough | grayscale, low resolution: corners and device edges are harder to see, so touch error is larger | colour, higher resolution, better depth of the passthrough reprojection |
| Hit-test (grip + trigger) | planes from manual Space Setup only (walls/floor/ceiling you drew), no mesh | Space Setup room mesh + planes: hitting a ceiling device or the floor is practical |
| GPU budget | weak: keep 3 layers and **Room/Near**; fixed foveation 0.7, framebuffer scale 0.85, target 72 Hz (`updateTargetFrameRate(72)` when offered) | more headroom; more layers or All are plausible (unmeasured) |
| Anchors / persistence | depends on Quest Browser / OS support; untested | same; untested |

### Verified vs unverified (MR)

Verified on desktop:
- `node --test tests/mr-align.test.cjs` (15 tests) covers:
  - the yaw convention against `registration-core.js` and Three.js;
  - exact recovery at four headings;
  - equality with `fitYawTranslation`;
  - **noise**: 200 seeded trials at 1 cm and 3 cm on the real foyer landmarks. The p95 true error at landmarks and sprinkler/diffuser checks stays below 3 cm and 8 cm; the p95 yaw error stays below 0.4° and 1.2°;
  - a 30 cm mis-touch flagged as the worst point and by leave-one-out;
  - the 2-point case, degenerate inputs and the short-span warning;
  - nudges about the head;
  - anchor-relative storage across a changed session frame;
  - record and check-log persistence with throwing storage;
  - check offsets in BIM axes;
  - the session state machine;
  - the landmark file (schema, points on their element boxes, reproducible from the GLBs);
  - the shader mirror against `overlay-visibility.js` `rangeFade`;
  - panel hit-testing;
  - page wiring.
- `tests/scan-xr-smoke.cjs` MR pass (headless Chrome, `?mode=ar&layers=duct,plumbing`) checks:
  - no capture, no photo and no Enter MR without `immersive-ar`, with the desktop note shown;
  - layers with zero unidentified fragments;
  - services hidden until aligned;
  - **Simulate alignment** (5 synthetic touches, 1 cm noise) → RMS 1.4 cm, truth error 0.7 cm, yaw error 0.04°;
  - the BIM group equal to the fit;
  - the record in `localStorage`;
  - honest labels;
  - services on screen;
  - Room culls (64 of 206 batches visible), Near ⊂ Room, All = no culling;
  - a card pick with the MR caption;
  - a check that reports a 5 cm offset exactly;
  - a 1 cm nudge saved;
  - panel buttons;
  - the reload notice;
  - no overflow at 390 px;
  - no page errors.

  `XR_SMOKE_MR=0` skips it. Screenshots: `scan-xr-mr-*.png`.

**Unverified: everything on a headset.** No `immersive-ar` session has been run on a Quest 2 or Quest 3. This covers:
- the passthrough compositing (transparent clear, `alpha-blend`);
- the permission prompts;
- `local-floor` height, controller target-ray / tip ball position, and touch accuracy;
- `hit-test`, `anchors`, `requestPersistentHandle` / `restorePersistentAnchor`, plane/mesh features, and `dom-overlay` (not expected on a headset);
- frame rate, foveation and the 72 Hz request;
- tracking drift over a walk;
- whether the curated landmarks are exposed and correctly identified on site.

### Limits

- **Tracking drift.** Inside-out tracking drifts over distance and time. Expect the alignment to degrade away from where it was made (centimetres over a room; more over a corridor). The anchor helps only near itself. Re-align per area.
- **Heading error grows with distance.** A 0.5° yaw error is 9 cm at 10 m. Spread the points (the far point E at the east entrance exists for this).
- **Re-alignment.** It is needed per session unless a persistent anchor was granted and found. It is also needed after recentring and per floor/area. There are only two Level 1 areas; other floors need new landmarks.
- **Quest 2.** Grayscale, low-resolution passthrough makes corners and devices hard to pick out. There is no mesh hit-test, and less GPU headroom.
- **No occlusion.** MR draws services over everything, including people and real objects in front of them. Neither BIM-wall occlusion (`overlay-visibility.js`) nor Quest 3 depth sensing is wired in. Ordinal depth comes only from the distance fade and the Lens.
- Design (BIM) positions only: as-built adjustments are not applied. Landmark boxes carry a few cm of ambiguity (finish vs structure layer). The tip ball is a virtual point seen over a reprojected camera image, so expect a few cm of parallax when touching.
