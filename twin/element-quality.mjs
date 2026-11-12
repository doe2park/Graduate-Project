/* twin/element-quality.mjs — applies buildings/grimes/element-quality.json to a layer sidecar at load time.

   The overlay (scripts/build_element_quality.py) names source objects that are not building parts and elements whose
   floor label disagrees with their geometry. Source GLBs and sidecars are never changed; this only decides what a
   viewer draws and which storey it files an element under.
   - hidden ids (annotation copies, layout points and clearance zones, exact double exports) leave `meta` and come back
     in `hidden`, so lists, search and picking never offer something that is not drawn. ?flagged=1 keeps them.
   - a storey correction sets levelKey to the storey that holds the geometry; the source label stays in sourceLevelKey.
   - every touched record gets `quality`: an array of reason keys (see QUALITY_NOTES).
   No DOM, no network: the page fetches the overlay and passes it in. A missing or unknown overlay changes nothing. */

export const ELEMENT_QUALITY_API = 1;
export const ELEMENT_QUALITY_PATH = 'buildings/grimes/element-quality.json';
const SCHEMA = 'twin-element-quality/1';
const HIDDEN_REASONS = ['annotation', 'reference', 'duplicate'];

export const QUALITY_NOTES = {
  annotation: 'Drawing linework that repeats a modelled part (CAD annotation layer)',
  reference: 'Layout point, sleeve point or clearance zone: a construction aid, not a part',
  duplicate: 'Exported twice at the same place; the other copy is shown',
  noGeometry: 'Has an identity but no drawable geometry in the model',
  aggregate: 'One source object that covers most of a floor; its parts cannot be picked one by one',
  storey: 'Level label disagrees with the geometry; filed under the storey that contains it',
};

export function showFlagged(search) {
  try { return new URLSearchParams(search || '').get('flagged') === '1'; } catch { return false; }
}

const list = value => Array.isArray(value) ? value.filter(id => typeof id === 'string' && id !== '') : [];
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
const done = new WeakMap();   // a cached sidecar object is applied once; a second load of the layer gets the same result

/* Returns {applied, hidden: Map(id -> record), counts}. Mutates `meta` as described above. */
export function applyElementQuality(meta, overlay, layer, {keepHidden = false} = {}) {
  const counts = {annotation: 0, reference: 0, duplicate: 0, noGeometry: 0, aggregate: 0, storey: 0};
  const result = {applied: false, hidden: new Map(), counts};
  const entry = overlay && overlay._schema === SCHEMA && overlay.layers && typeof overlay.layers === 'object' ? overlay.layers[layer] : null;
  if (!meta || typeof meta !== 'object' || !entry || typeof entry !== 'object') return result;
  if (done.has(meta)) return done.get(meta);
  done.set(meta, result);
  result.applied = true;
  const flag = (id, reason) => { const info = meta[id]; (info.quality || (info.quality = [])).push(reason); counts[reason]++; return info; };
  for (const reason of ['noGeometry', 'aggregate']) for (const id of list(entry[reason])) if (own(meta, id)) flag(id, reason);
  const storey = entry.storey && typeof entry.storey === 'object' ? entry.storey : {};
  for (const [key, ids] of Object.entries(storey)) for (const id of list(ids)) {
    if (!own(meta, id) || meta[id].levelKey === key) continue;
    const info = flag(id, 'storey');
    info.sourceLevelKey = info.levelKey || 'UNKNOWN'; info.levelKey = key;
  }
  const hiddenLists = entry.hidden && typeof entry.hidden === 'object' ? entry.hidden : {};
  for (const reason of HIDDEN_REASONS) for (const id of list(hiddenLists[reason])) {
    if (!own(meta, id) || result.hidden.has(id)) continue;
    const info = flag(id, reason);
    if (keepHidden) continue;
    info.hidden = reason; result.hidden.set(id, info); delete meta[id];
  }
  return result;
}

/* Remove the drawables owned by hidden ids from a loaded glTF scene, before a render tier is built from it.
   Ownership follows the tiers: the nearest ancestor-or-self whose elementId (or name) is a known id. */
export function dropHiddenObjects(root, hidden, meta) {
  if (!root || !hidden || !hidden.size) return 0;
  const drop = [];
  root.traverse(object => {
    if (!(object.isMesh || object.isLine || object.isPoints)) return;
    for (let p = object; p; p = p.parent) {
      const id = p.userData?.elementId ?? p.name;
      if (!id) continue;
      if (meta && own(meta, id)) return;
      if (hidden.has(id)) { drop.push(object); return; }
    }
  });
  for (const object of drop) object.removeFromParent();
  return drop.length;
}

/* For pruneGlbToLevels: the same sidecar view plus the hidden ids on a level no page asks for, so they are cut
   from the scene graph before Draco decodes them. */
export function metaForPruning(meta, hidden) {
  if (!hidden || !hidden.size) return meta;
  const out = Object.assign({}, meta);
  for (const id of hidden.keys()) out[id] = {levelKey: '(hidden)'};
  return out;
}

/* True for a record a viewer should not draw by default (it kept the record because keepHidden was set). */
export function isNonPart(info) {
  return Array.isArray(info?.quality) && info.quality.some(reason => HIDDEN_REASONS.includes(reason));
}

export function qualityText(info) {
  const reasons = Array.isArray(info?.quality) ? info.quality : [];
  return reasons.map(reason => QUALITY_NOTES[reason]).filter(Boolean).join(' · ');
}

export function hiddenSummary(counts) {
  const n = HIDDEN_REASONS.reduce((sum, reason) => sum + (counts?.[reason] || 0), 0);
  return n ? `${n.toLocaleString('en-US')} non-part source objects not drawn` : '';
}
