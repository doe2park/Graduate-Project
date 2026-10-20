/* twin/overlay-visibility.js — realistic visibility for the scan/BIM Overlay (pure helpers + GLSL; no DOM, no Three.js import).
   Owner feedback 2026-10-20: "things that are too far away should not be visible" while walking in Overlay.

   Two effects, both per fragment so a long pipe fades along its length:
   1. DISTANCE FADE  alpha *= 1 - smoothstep(fadeStart, fadeEnd, |camera -> fragment|)  (metres, BIM frame).
      Range presets: near 3 -> 6 m, room 8 -> 14 m (default; 6 -> 11 m emptied the atrium and auditorium in testing), all = no fade and no occlusion (the pre-2026-10-20 X-ray).
   2. WALL OCCLUSION  a depth-only pre-pass of BIM *walls* (Level 1 interior Walls; doors, mullions, ceilings excluded)
      in the same BIM frame as the services, so no capture registration is involved. A service fragment more than
      OCCLUSION.marginM behind the nearest wall surface is hidden (outside the Lens) or shown at OCCLUSION.lens inside
      the Lens (the Lens is the intentional see-through window). Wall fragments nearer than OCCLUSION.nearIgnoreM to the
      camera are ignored so a station that the provisional alignment puts inside a wall does not blank the view.
      Ceilings are NOT occluders: services above the ceiling (plenum) are what the X-ray is for.
   The parent page's opacity slider (iframe opacity / lens mask) multiplies on top of this.

   Works as a browser global (window.OverlayVisibility) and as CommonJS (tests). Kept free of Three.js so scan-xr.html
   can adopt patchShader() later with its own uniforms (not wired into XR yet). */
(function (root, factory) {
  const api = factory();
  if (root) root.OverlayVisibility = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const RANGE_PRESETS = Object.freeze({
  near: Object.freeze({ key: 'near', label: 'Near', fadeStart: 3, fadeEnd: 6, occlude: true, title: 'Services within about 3 m, gone by 6 m; walls hide what is behind them' }),
  room: Object.freeze({ key: 'room', label: 'Room', fadeStart: 8, fadeEnd: 14, occlude: true, title: 'Services within about 8 m, gone by 14 m; walls hide what is behind them' }),
  all:  Object.freeze({ key: 'all',  label: 'All',  fadeStart: Infinity, fadeEnd: Infinity, occlude: false, title: 'Every service on the floor, through walls (X-ray)' }),
});
const RANGE_KEYS = Object.freeze(['near', 'room', 'all']);
const DEFAULT_RANGE = 'room';
/* marginM: a service may sit this far behind the facing wall surface (in-wall conduit, wall thickness, ~0.3 m alignment).
   hidden: occluded outside the Lens. lens: occluded inside the Lens (relaxed, but dimmer than unoccluded = ordinal depth cue). */
const OCCLUSION = Object.freeze({ marginM: 0.35, nearIgnoreM: 0.6, hidden: 0, lens: 0.45 });
/* Lens weight matches the parent CSS mask: full inside 72% of the radius, linear to 0 at the rim. */
const LENS_CORE = 0.72;
/* picking ignores anything drawn fainter than this (fade x occlusion) */
const PICK_MIN = 0.25;
/* shader stand-in for "no fade" (GLSL has no portable Infinity) */
const FAR_NONE = 1e7;

function parseRange(search) {
  let v = null;
  try { v = new URLSearchParams(search || '').get('range'); } catch (e) { v = null; }
  return RANGE_KEYS.includes(v) ? v : DEFAULT_RANGE;
}
function preset(key) { return RANGE_PRESETS[RANGE_KEYS.includes(key) ? key : DEFAULT_RANGE]; }
function smoothstep(e0, e1, x) { const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t); }
/* 1 = full strength, 0 = gone. Same curve as the GLSL below. */
function rangeFade(distance, p) {
  p = typeof p === 'string' ? preset(p) : p;
  if (!p || !Number.isFinite(p.fadeEnd)) return 1;
  if (!Number.isFinite(distance)) return 0;
  if (distance <= p.fadeStart) return 1;
  return 1 - smoothstep(p.fadeStart, p.fadeEnd, distance);
}
/* dx, dy: offset from the lens centre; r: lens radius (same units). Returns 0..1. */
function lensWeight(dx, dy, r) {
  if (!(r > 0) || !Number.isFinite(dx) || !Number.isFinite(dy)) return 0;
  const d = Math.hypot(dx, dy);
  return Math.min(1, Math.max(0, (r - d) / ((1 - LENS_CORE) * r)));
}
function occlusionFactor(occluded, lensW, p) {
  p = typeof p === 'string' ? preset(p) : p;
  if (!p || !p.occlude || !occluded) return 1;
  const w = Math.min(1, Math.max(0, Number(lensW) || 0));
  return OCCLUSION.hidden + (OCCLUSION.lens - OCCLUSION.hidden) * w;
}
/* occluded = fragment lies more than marginM behind the nearest counted wall surface along the same ray */
function isOccluded(distance, wallDistance) {
  return Number.isFinite(wallDistance) && wallDistance >= OCCLUSION.nearIgnoreM && distance > wallDistance + OCCLUSION.marginM;
}
function visibility({ distance, wallDistance = Infinity, lensW = 0 }, p) {
  return rangeFade(distance, p) * occlusionFactor(isOccluded(distance, wallDistance), lensW, p);
}
function isPickable(args, p) { return visibility(args, p) >= PICK_MIN; }
/* uniform values for a preset: [fadeStart, fadeEnd] and the occlusion switch */
function uniformValues(p) {
  p = typeof p === 'string' ? preset(p) : p;
  const finite = Number.isFinite(p.fadeEnd);
  return { fade: finite ? [p.fadeStart, p.fadeEnd] : [FAR_NONE, FAR_NONE * 2], occlude: p.occlude ? 1 : 0 };
}
/* lens state from the parent (CSS px of the shared rect, y down) -> gl_FragCoord space (device px, y up) */
function lensToFragCoord(lens, cssHeight, pixelRatio) {
  if (!lens || !lens.on || ![lens.x, lens.y, lens.r, cssHeight, pixelRatio].every(Number.isFinite) || !(lens.r > 0)) return [0, 0, 0, 0];
  return [lens.x * pixelRatio, (cssHeight - lens.y) * pixelRatio, lens.r * pixelRatio, 1];
}

/* ── GLSL (Three.js onBeforeCompile). Uniform objects are shared, so one write updates every patched material. ── */
const VERTEX_DECL = 'varying vec3 ovView;\n';
const VERTEX_MAIN = '\n\tovView = mvPosition.xyz;';
const FRAGMENT_DECL = [
  'uniform float ovOn;',          // 1 while the Overlay is on
  'uniform vec2 ovFade;',         // fadeStart, fadeEnd (m)
  'uniform float ovOcc;',         // 1 when the wall depth texture is valid
  'uniform sampler2D ovDepth;',   // wall depth (perspective depth 0..1)
  'uniform vec2 ovRes;',          // drawing-buffer size (px)
  'uniform vec2 ovClip;',         // camera near, far
  'uniform vec3 ovOccK;',         // marginM, hidden, lens
  'uniform vec4 ovLens;',         // lens centre x, y, radius (device px, y up), on
  'varying vec3 ovView;', ''].join('\n');
const FRAGMENT_MAIN = `
	if (ovOn > 0.5) {
		float ovD = length(ovView);
		float ovF = 1.0 - smoothstep(ovFade.x, ovFade.y, ovD);
		if (ovOcc > 0.5) {
			float ovZ = texture2D(ovDepth, gl_FragCoord.xy / ovRes).x;
			if (ovZ < 1.0) {
				float ovWall = (ovClip.x * ovClip.y) / ((ovClip.y - ovClip.x) * ovZ - ovClip.y);
				if (-ovView.z > -ovWall + ovOccK.x) {
					float ovLw = ovLens.w > 0.5 ? clamp((ovLens.z - distance(gl_FragCoord.xy, ovLens.xy)) / (${(1 - LENS_CORE).toFixed(2)} * ovLens.z), 0.0, 1.0) : 0.0;
					ovF *= mix(ovOccK.y, ovOccK.z, ovLw);
				}
			}
		}
		if (ovF < 0.004) discard;
#ifdef OV_PREMULTIPLY
		gl_FragColor *= ovF;
#else
		gl_FragColor.a *= ovF;
#endif
	}
`;
/* Opaque materials draw without blending into a premultiplied-alpha canvas, so rgb and alpha scale together;
   blended materials scale alpha only. */
function patchShader(shader, uniforms, { premultiply = true } = {}) {
  if (!shader || !uniforms || shader.vertexShader.includes('ovView')) return shader;
  if (!shader.vertexShader.includes('#include <project_vertex>')) return shader;
  Object.assign(shader.uniforms, uniforms);
  shader.vertexShader = VERTEX_DECL + shader.vertexShader.replace('#include <project_vertex>', '#include <project_vertex>' + VERTEX_MAIN);
  const at = shader.fragmentShader.lastIndexOf('}');
  shader.fragmentShader = (premultiply ? '#define OV_PREMULTIPLY\n' : '') + FRAGMENT_DECL + shader.fragmentShader.slice(0, at) + FRAGMENT_MAIN + shader.fragmentShader.slice(at);
  return shader;
}
/* depth-only wall pass: drop wall fragments right at the camera (station inside a wall after provisional alignment) */
const OCCLUDER_FRAGMENT_MAIN = `
	if (length(ovView) < ${OCCLUSION.nearIgnoreM.toFixed(2)}) discard;
`;
function patchOccluderShader(shader) {
  if (!shader || shader.vertexShader.includes('ovView') || !shader.vertexShader.includes('#include <project_vertex>')) return shader;
  shader.vertexShader = VERTEX_DECL + shader.vertexShader.replace('#include <project_vertex>', '#include <project_vertex>' + VERTEX_MAIN);
  const at = shader.fragmentShader.lastIndexOf('}');
  shader.fragmentShader = 'varying vec3 ovView;\n' + shader.fragmentShader.slice(0, at) + OCCLUDER_FRAGMENT_MAIN + shader.fragmentShader.slice(at);
  return shader;
}
/* Interior element -> wall occluder? Walls only (doors may be open, mullions frame glass, ceilings hide the plenum). */
function isWallOccluder(info) { return !!info && info.category === 'Walls'; }

return { RANGE_PRESETS, RANGE_KEYS, DEFAULT_RANGE, OCCLUSION, LENS_CORE, PICK_MIN, FAR_NONE,
  parseRange, preset, smoothstep, rangeFade, lensWeight, occlusionFactor, isOccluded, visibility, isPickable, uniformValues, lensToFragCoord,
  VERTEX_DECL, VERTEX_MAIN, FRAGMENT_DECL, FRAGMENT_MAIN, patchShader, patchOccluderShader, isWallOccluder };
});
