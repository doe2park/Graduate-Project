# Grimes Hall Interior Scans

Drop-in folder for 360 camera + LiDAR scan data of Grimes Hall interior.
Files here are loaded by `grimes-xr.html` via the **Interior** toggle in the
topbar, with the manifest at `data/grimes-interior.json` describing what to
load and how to align it.

## What goes here

Scan deliverables, in order of preference:

| Format | Extension | Loader | Notes |
|---|---|---|---|
| glTF binary | `.glb` | three.js GLTFLoader | **Preferred.** Single file, supports textures + Draco compression. |
| glTF JSON | `.gltf` (+ bins) | three.js GLTFLoader | Multi-file, OK if exported by Reality Capture, etc. |
| Stanford polygon | `.ply` | three.js PLYLoader | Point cloud or simple mesh. |
| Point Cloud Data | `.pcd` | three.js PCDLoader | Pure point cloud. |
| Gaussian Splat | `.splat` / `.ply` | luma-style splat viewer | If you go the Polycam / Luma route. |

If a vendor hands you `.e57`, `.las`, or a Matterport `.zip`, convert to one of
the above first. CloudCompare exports `.ply`; Reality Capture exports `.glb`.

## Drop-in workflow

1. Copy your scan file here, e.g. `scans/grimes-interior-floor1.glb`.
2. Open `data/grimes-interior.json` and set:
   ```json
   "model": {
     "path": "./scans/grimes-interior-floor1.glb",
     "format": "glb",
     "scale": 1.0
   }
   ```
3. Reload `grimes-xr.html`, click the **🏛 Interior** button in the topbar.
4. If alignment looks off (sunk into the floor, rotated 90°, scaled wrong),
   open browser console — the viewer logs the bounding box on load. Tweak
   `model.scale` / `rotation_deg` / `position` in the manifest until it sits
   right.
5. To add sensor markers, fill `hotspots[]` in the manifest. Use the 🎯 Pick
   tool in the topbar to click a point in the scan and copy the printed
   coordinates.

## File size guidance

- Under 50 MB → commit normally
- 50–200 MB → use Git LFS (`git lfs track "scans/*.glb"`)
- Over 200 MB → host externally (e.g. lab S3 / Google Drive) and put the URL
  in `model.path` instead of a local path. The viewer accepts http(s) URLs.

Compress aggressively with [gltf-transform](https://gltf-transform.dev):

```
npx gltf-transform optimize scan.glb scan-optimized.glb \
  --texture-compress webp --simplify 0.5 --weld
```

A clean photogrammetry capture of a 5,000 sqft floor compresses to ~5–15 MB
this way.

## Coordinate conventions

The viewer expects:
- **Up axis:** Y-up
- **Units:** meters
- **Origin:** scan centroid (the loader auto-recenters anyway)

If your scan is Z-up (Revit / Reality Capture default) set
`rotation_deg.x = -90` in the manifest. If it's in feet, set `scale = 0.3048`.

## Privacy

If a scan accidentally captures people, faces, or sensitive lab equipment,
redact before committing. Do not commit raw walkthrough video.
