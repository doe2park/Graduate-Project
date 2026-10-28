# Field capture: Grimes Level 2 + Level 3 (Insta360 ONE X2), 28 Oct 2026

Goal: one recording that the local Cupix-free pipeline can tie to the BIM.
The tie comes from **Level 1 photos that are already registered**. So the walk must **start and end on Level 1** at the atrium stair.

## 1. Before you leave

- [ ] Battery full, plus a power bank. A spare battery if you have one.
- [ ] microSD: at least 20 GB free. Time-lapse is small (Oct 18: 166 MB for 3 min 53 s).
- [ ] Lenses clean (microfibre cloth). No lens guards.
- [ ] **No firmware update today.** The pipeline was checked on the Oct 18 files.
- [ ] Phone note ready (section 6). Tape measure.
- [ ] Stick: the same one as Oct 18.

## 2. Camera mode

- **Use: TimeLapse, 5.7K, interval 0.5 s.** That is what made the Oct 18 file (463 frames over 3 min 53 s, no sound). The pipeline is proven on it.
- Backup only: normal **Video 5.7K 30 fps**. The runner handles it (it sees the sound track) but it is untested on a long walk. Files are much bigger.
- **Do not use:** TimeShift / hyperlapse, HDR video, Photo or Interval photo, Bullet Time. These change the frame timing or the lens calibration.
- Leave exposure on auto. Don't touch the white balance or the colour profile during the walk.
- Test first: record 10 s, stop, then check a new `VID_..._00_NNN.insv` appears in the camera's album.

## 3. Holding the camera

- **Lens about 2.0 m above the floor, kept the same all the time.** The Oct 18 data fits 1.97–2.07 m.
- **Measure it once:** stand normally and tape from the floor to the lens centre. Write it down. It becomes `--camera-height`.
- Keep the stick vertical, with the camera **above your head**. Hold the stick to the side and in front of you. Look ahead, not at the camera. Your face appeared in many Oct 18 frames.
- Turn the camera's screen away from you. Don't touch the camera while walking.
- Keep about 0.5 m away from walls and glass.

## 4. Route: one continuous recording

**Start/end spot (Level 1):** in the atrium, about 3 m in front of the wide grey bottom steps of the white atrium stair (the stair with the wooden bench step).
This is next to Oct 18 Level 1 stations 50–52 and May station 83697689. Those photos are what tie the walk to the BIM. On Oct 18 they matched the stair foot at 52–137 inliers.

1. Press record at the start spot. **Stand still for 5 s.**
2. **Level 1 mini loop (~1 min):** walk a slow loop of about 10 m around the atrium lounge. Come back past the start spot.
3. **Up the atrium stair to Level 2:** one step per second. Pause 3 s on the landing and 3 s at the top.
4. **Level 2 loop:** walk the whole corridor ring, then go back to the top of the stair. Take a short look into open rooms only if they are empty.
5. **Up to Level 3**, as slowly as in step 3.
6. **Level 3 loop.** Include every corridor that has no grey dots on `route-L3.png`. These are the Oct 18 gap; the Oct 18 notes call it the west/north part. Go back to the top of the stair.
7. **Down to Level 2, then down to Level 1.** Walk a short stretch of the Level 2 corridor on the way.
8. **Finish at the start spot.** Stand still for 5 s, then stop recording.

Route sketches: `docs/field-capture/route-L1.png`, `route-L2.png`, `route-L3.png`. They show the BIM plan, the start spot and the Oct 18 coverage. North is up (inferred from the BIM frame).

**Why one recording:** each recording must contain the Level 1 start spot, or it cannot be placed without Cupix. Walking the stairs **both ways** gives a second chance to join the floors if SfM breaks on the stairs, as it did on Oct 18.
If you must stop (battery, people), start the next recording at the Level 1 start spot again.

## 5. Walking

- **Walk slowly, about half your normal speed** (0.5 m/s). One step per second on the stairs.
- **Pause 2–3 s:** in every doorway, at corners, at the top and bottom of every flight, and on both sides of a big change in light.
- Turn slowly. Never spin on the spot.
- Lights on where you can. Avoid walking straight from dark into bright spaces.
- **People:** wait until they have passed. Skip rooms where people are working. Don't film screens or whiteboards up close.

## 6. Phone note (write as you go)

- Camera file number (`_NNN`), start and stop clock times.
- Measured lens height (m).
- Route as walked: floors, wings, skipped areas, closed doors.
- Any stop or restart, and where.
- Anything odd: people in the frame, a dropped stick, a hand on the lens.

## 7. Copy the files

1. On the X2: Settings → USB mode → **U-Disk**. Connect to the Mac.
2. Open `DCIM/Camera01/`. Copy **only `VID_20261028_HHMMSS_00_NNN.insv`**. If a `_10_` file with the same name exists, copy it too. **`LRV_...` files are not needed.**
3. Destination: `/Users/yschung/Desktop/Research stuff/Raw Data/Insta 360 X2 Scan/`
   Use Finder, or `cp -p`. **Keep the file date:** the runner uses it to work out the time-lapse rate.
4. Check the copy (Terminal):
   ```
   shasum -a 256 "/Volumes/<card>/DCIM/Camera01/VID_20261028_*_00_*.insv" "/Users/yschung/Desktop/Research stuff/Raw Data/Insta 360 X2 Scan/VID_20261028_"*_00_*.insv
   ```
   The two hashes of each file must be the same.
5. Keep the files on the card until processing has worked and the files are backed up.

## 8. Process (Mac, repo folder)

```
cd ~/Graduate-Project
python3 scripts/capture_upper_floors.py --date 2026-10-28 --camera-height <measured> \
  "/Users/yschung/Desktop/Research stuff/Raw Data/Insta 360 X2 Scan/VID_20261028_<time>_00_<NNN>.insv"
python3 -m http.server 8893
```

Then open `http://localhost:8893/scan-compare.html?capture=2026-10-28&floors=L2` (or `L3`, `L1`).
This takes about 15–30 min per recording on the M4 (the privacy blur is the slowest part).
The report is in `work/raw360/2026-10-28/run-report.json`.

**If the run stops at "place"**, no part could be tied to the BIM. The usual cause is that the start/end spot is missing or too fast. The files are fine, so the **fallback is a Cupix upload as before**.

Everything is provisional and not surveyed. Panoramas are blurred automatically, but a manual review is needed before anything is shared.
