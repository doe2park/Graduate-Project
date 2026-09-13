# Gaussian reconstruction implementation plan

User authorized autonomous implementation and later presentation preparation on 2026-09-13.

Goal: optimize an actual 3D Gaussian scene from recovered Grimes images, test continuous navigation beside BIM, and preserve reproducible methods/evidence for future floors.

Architecture: keep the canonical GLBs, registration and element data unchanged. Convert recovered spherical photos and E57 poses into perspective training images in scan Y-up metres. Train a bounded pilot locally with Brush on Apple GPU. Render the resulting Gaussian PLY in a separate experimental scan mode using the existing camera transform. Store private training inputs and outputs locally. Results must distinguish visual evaluation, numerical registration and physical accuracy.

- [ ] Confirm training runtime, license/version, dataset conventions and memory limits.
- [ ] Build and test spherical-to-perspective image/pose exporter with explicit source stations and held-out captures.
- [ ] Run pilot optimization; record commands, checkpoints, losses and image comparisons; expand only if supported by results.
- [ ] Add real Gaussian renderer with continuous desktop/mobile movement and parent camera protocol.
- [ ] Connect experimental mode without changing baseline GLBs, photo mode or sensor bindings; validate transforms and rendering.
- [ ] Record technology-to-reference matrix, current limitations, next-floor onboarding and future slide outline in repository/local research notes.
- [ ] Review, verify and commit locally; do not publish sensitive capture assets without specific publication authorization.

Validation: analytic camera-axis/projection tests, source image hashes and split IDs; actual training checkpoint export; visual comparisons at captured and held-out positions; browser camera synchronization and mode switching; mobile-emulated load/control check with explicit physical-device limitation.
