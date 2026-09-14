# Gaussian reconstruction implementation plan

User authorized autonomous implementation and later presentation preparation on 2026-09-13.

Goal: optimize an actual 3D Gaussian scene from recovered Grimes images, test continuous navigation beside BIM, and preserve reproducible methods/evidence for future floors.

Architecture: keep the canonical GLBs, registration and element data unchanged. Convert recovered spherical photos and E57 poses into perspective training images in scan Y-up metres. Train a bounded pilot locally with Brush on Apple GPU. Render the resulting Gaussian PLY in a separate experimental scan mode using the existing camera transform. Store private training inputs and outputs locally. Results must distinguish visual evaluation, numerical registration and physical accuracy.

- [x] Confirm training runtime, license/version, dataset conventions and memory limits.
- [x] Build and test spherical-to-perspective image/pose exporter with explicit source stations and held-out captures.
- [x] Run pilot optimization; record commands, checkpoints, losses and image comparisons; expand only if supported by results.
- [x] Add real Gaussian renderer with continuous desktop/mobile movement and parent camera protocol.
- [x] Connect experimental mode without changing baseline GLBs, photo mode or sensor bindings; validate transforms and rendering.
- [x] Record technology-to-reference matrix, current limitations, next-floor onboarding and future slide outline in repository/local research notes.
- [x] Review, verify and commit locally; do not publish sensitive capture assets without specific publication authorization.

Validation: analytic camera-axis/projection tests, source image hashes and split IDs; actual training checkpoint export; visual comparisons at captured and held-out positions; browser camera synchronization and mode switching; mobile-emulated load/control check with explicit physical-device limitation.

## Verified result

Completed the 6k-step pilot, 50k-step 1M whole-archive baseline and 30k-step additional 2M warm start. The selected local experimental model is the compressed 1M baseline; the larger final model did not materially reduce reviewed blur. Final training logs and hashes are archived. This delivers actual novel-view Gaussian navigation, not a promise of photograph-quality reconstruction.

Final browser checks passed for synthetic Gaussian rendering/idle scheduling, the actual selected KSplat desktop model, the reduced mobile model, and movement/orientation/FOV mapping from either pane. Mobile validation is emulation on the Mac. Python camera/package tests and actual codec round-trip/hash checks passed; independent code review reported no remaining actionable issues. Original photo/mesh behavior was regression-tested earlier in this turn. Source scan GLB hashes remain unchanged.

Methods, measured results, limits and reusable commands are in `docs/GAUSSIAN_RECONSTRUCTION_METHODS.md`; future slide content is in the local presentation backlog and the Obsidian Gaussian Reconstruction Pilot note. No PowerPoint changed. Local commits only; private Gaussian assets remain ignored and were not publicly deployed.
