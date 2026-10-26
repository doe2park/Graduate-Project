# Image sources: talks/sensor-deck/img

Every raster image used by the deck (the fiber principle sketches, row icons and the building WSN diagram are native SVG drawn in `gen.py`), where it comes from, its licence or permission, and what was changed. The slide that shows each image also carries a short credit line. `tests/talks-deck.test.cjs` checks that every file here is listed and used.

| File | Source | Licence / permission | Changes | Slide |
|---|---|---|---|---|
| `ce278-das-waterfall.jpg` | The presenter's own CE278 final project (UC Berkeley, fall 2025): DAS dynamic-strain waterfall, run 115938-160018 (15:59:38–16:00:38), channels 1450–1650 (`Strain_focused.png`). Computed from the course-provided DAS dataset. | Own figure; the owner approved public use. | White margins trimmed, resized to 1200 px wide. The plot's axis labels are kept. | CE278 project |
| `ce278-das-detection.jpg` | Same project and run: event detection, RMS strain in channels 1500–1600 (`Vehicle Detection.png`) | Own figure; the owner approved public use. | White margins trimmed, resized to 1600 px wide. | CE278 project |
| `l24-p3-mems-accelerometer.jpg` | CE170/278 Infrastructure Sensing, UC Berkeley (Prof. K. Soga), Lecture 2-4 ("Digital Sensors and Wireless Sensor Network"), p. 3: MEMS comb accelerometer schematic | Course material. On 2026-10-24 the owner said lecture figures may be used in this deck, including the public version. | Page rendered at 220 dpi (pdftoppm). Only the schematic is cropped; the lecture's slide title, the product photo and the third-party SEM image on the same page are excluded. | MEMS |
| `l24-p19-wireless-node.jpg` | Same course, Lecture 2-4, p. 19: a battery wireless sensor node (course lab hardware, top-left photo of four) | Course material, same permission. | Page rendered at 220 dpi; only that one photo is cropped (no lecture text). | MEMS |
| `b-hvac.jpg`, `b-plumb.jpg`, `b-elec.jpg`, `b-fan.jpg`, `t1-lens-base.jpg` | Own headless screenshots of the public viewer (`scan-compare.html`, Overlay · Lens) on the **public May 6, 2026 capture** (captures 43, 1, 43, 22 and 35) | Own work, from published project data | Cropped so that no viewer UI text remains | Static fallback of concept slides 2–5 and 1 |
| `t2-twin-sensor-mockup.jpg` | `t1-lens-base.jpg` with drawn concept graphics (temperature line, alert ring, two markers); contains no text | Own work | Graphics drawn with Pillow | Fallback if the concept 1 base image fails |

There is no imagery from the Oct 18 capture or from any capture still under privacy review.

Fonts: `../fonts/Carlito-*.ttf` are Carlito by tyPoland Łukasz Dziedzic, licensed under the SIL Open Font License 1.1 (`../fonts/OFL.txt`). They are not modified.


Removed on 2026-10-25 (owner: only building-relevant visuals): the Wikimedia photos of a telecom fiber cable, a wireless accelerometer on a bridge hanger and FBG sensors on a rail; the lecture figures of a vibrating-wire gauge in a rebar cage vs a MEMS strain sensor (Lecture 2-4 p. 5) and of gas-pipeline WSN instrumentation (Lecture 2-4 p. 10).
