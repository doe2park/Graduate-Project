# Sensor deck (public)

"Building Data and Sensing for the Grimes Twin": a 25-slide HTML deck, served by GitHub Pages at
`https://doe2park.github.io/Graduate-Project/talks/sensor-deck/` and locally at `http://127.0.0.1:8790/talks/sensor-deck/`
(a static server at the repository root). `#12` jumps to slide 12.

- **Keys:** ←/→ or Space change slides, also while a live view has focus; Esc returns focus to the deck. Home/End, F fullscreen, N speaker notes.
- **Test-install (concept) slides 12–16** embed the live twin viewer in a same-origin iframe:
  `../../scan-compare.html?view=overlay&capture=2026-05-06&mode=photo&style=lens&sensors=demo&scene=<leak|air|water|elec|rotating>&at=<pose>`.
  - The URL is relative, so the same file works locally and on Pages.
  - Each slide loads only its own scenario's demo sensors (`scene=`), from `twin/sensors/registry.json`. Nothing is installed; every value is illustrative.
  - A viewer loads on its slide and warms up, hidden, on the slide before (once that slide's own live view is ready); every other viewer is unloaded. The viewer loads the scene's anchor layer first (`scan-bim.html` `ovLayerOrder`).
  - Until its demo sensors are drawn, the slide shows the static screenshot with its markers ("Live 3D view loading…" beside the buttons), then swaps in the live view.
  - Drag to look around. Hovering or clicking a numbered card, a marker (static view) or a pin (interactive view) opens a callout **beside that marker / pin** with a short gold leader line: title, "SIMULATED · not installed", the simulated reading and a small **simulated** chart. Click the same marker, click elsewhere or press Esc to close; the right column keeps its three steps.
  - Placement (`place.js`, pure, unit-tested): the card stays inside the image and clear of every other numbered marker / pin, the selected sensor's own drawing (pipe, cable, ring; the `geo` shapes in `scenarios.py`) and the viewer's badges; other sensors' drawings and tints are avoided when possible. It tries 12 spots around the marker for each card size (largest chart first), then the nearest clear spot within 120 px (260 px for the smallest size), else the least overlap. In the interactive view it reads the pins' positions from the same-origin viewer and follows the pin while the view moves; the viewer's own floating cards stay hidden.
  - Charts (`charts.py`) are drawn from `twin/sensors/registry.json` series or the deterministic demo feed (`tools/sensor_sim.py`); `chart_for()` asserts that the drawn numbers match the card text.
  - **Static view** (or a failed load) shows the screenshot fallback with SVG markers.
  - **Open in viewer ↗** opens the same live view in a new tab.

## Editing
Edit `content.json` (text slides), `scenarios.py` (concept slides) or `gen.py` (layout and the fiber / CE278 / MEMS / WSN / “Ready for real sensors” slides). Sensor data for the live views: `twin/sensors/registry.json` + the simulated feed (`twin/sensors/README.md`). Then run:

```sh
python3 talks/sensor-deck/gen.py      # writes talks/sensor-deck/index.html
```

`deck.js` and `deck.css` are inlined into `index.html` by `gen.py`. `place.js` is inlined too (callout placement). `twin_lib.py` holds the concept-slide machinery and `charts.py` the callout charts.
This folder is the working copy. The old `work/sensor-deck/` (gitignored) is only a local archive, and its `check/` holds review renders. Never put renders, raw downloads or `tools/` output in this folder.

## Sources and licences
- Images: `img/SOURCES.md` lists the Wikimedia Commons photos (CC BY / CC BY-SA, credited on the slide), the presenter's own CE278 DAS figures, the CE170/278 lecture figures (used with the owner's permission, credited on the slide) own screenshots of the public May 6, 2026 capture, and two Oct 18 open-ceiling views (ceiling only, approved for public use).
- Fonts: Carlito, SIL OFL 1.1 (`fonts/OFL.txt`).
- Check: `node --test tests/talks-deck.test.cjs`.
