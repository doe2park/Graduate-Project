/* ════════════════════════════════════════════════════════════════════════
   Twin Resolver — building-agnostic. Given a Twin Package (manifest + Brick
   model + binding + sources), it turns a clicked glb node into live data.
   Pure logic, no Three.js, no DOM. Runs in the browser AND in Node (tests).

   The ONE interaction every building shares:
     nodeName --binding--> Brick entity --hasPoint/isFedBy--> points
              --externalReference--> sources --adapter--> live values
   Add a building = add a package folder. No code changes here. Ever.
   ════════════════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  // Load the 4 package files. `fetchJson(url)` must return a parsed object.
  async function loadPackage(manifestUrl, fetchJson) {
    const manifest = await fetchJson(manifestUrl);
    const [brick, binding, sources] = await Promise.all([
      fetchJson(manifest.data.brick),
      fetchJson(manifest.data.binding),
      fetchJson(manifest.data.sources),
    ]);
    return { manifest, brick, binding, sources };
  }

  // Resolve a clicked glb node name to its Brick entity + the points that
  // describe its live data (its own points, plus those of meters that feed it).
  // glb exporters routinely sanitize node names ("HVAC Duct" -> "HVAC_Duct"),
  // so binding lookups are normalized: case, spaces, underscores, and other
  // punctuation are ignored. Exact match still wins when present.
  function normKey(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, ''); }

  function resolveNode(pkg, nodeName) {
    let uri = pkg.binding.nodes[nodeName];
    if (!uri) {
      if (!pkg._normNodes) {
        pkg._normNodes = {};
        for (const k in pkg.binding.nodes) pkg._normNodes[normKey(k)] = pkg.binding.nodes[k];
      }
      uri = pkg._normNodes[normKey(nodeName)];
    }
    if (!uri) return { nodeName, bound: false, reason: 'no binding for node "' + nodeName + '"' };
    const ent = pkg.brick.entities[uri];
    if (!ent) return { nodeName, uri, bound: false, reason: 'binding points to unknown entity ' + uri };

    const pointUris = [];
    (ent.hasPoint || []).forEach(p => pointUris.push(p));
    // Equipment usually has no sensor of its own at system tier — pull the points
    // of whatever meters feed it (brick:isFedBy), which is where the kW lives.
    (ent.isFedBy || []).forEach(feederUri => {
      const feeder = pkg.brick.entities[feederUri];
      if (feeder && feeder.hasPoint) feeder.hasPoint.forEach(p => pointUris.push(p));
    });

    const points = pointUris.map(pu => {
      const pe = pkg.brick.entities[pu] || {};
      return { uri: pu, type: pe.type, unit: pe.hasUnit, ref: pe.externalReference };
    }).filter(p => p.ref);

    return {
      nodeName, uri, bound: true,
      label: ent.label || uri,
      type: ent.type,
      feeders: (ent.isFedBy || []).map(f => (pkg.brick.entities[f] || {}).label || f),
      points,
    };
  }

  // Given resolved points, fetch their live values through the configured adapters.
  // `fetchJson(url)` loads a data file (cached by the caller if desired).
  async function fetchValues(pkg, points, fetchJson) {
    const out = {};
    const dataCache = {};
    const get = async url => (dataCache[url] = dataCache[url] || fetchJson(url));
    for (const p of points) {
      const ps = pkg.sources.points[p.ref];
      if (!ps) { out[p.ref] = { error: 'no source for ' + p.ref }; continue; }
      const ad = pkg.sources.adapters[ps.adapter];
      if (!ad) { out[p.ref] = { error: 'no adapter ' + ps.adapter }; continue; }
      out[p.ref] = await runAdapter(ad, ps, await get(ad.url));
    }
    return out;
  }

  function _dig(obj, path) { return path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj); }

  function runAdapter(adapter, pointSrc, data) {
    if (adapter.type === 'bmo-json') {
      const meters = _dig(data, adapter.metersAt) || {};
      const m = meters[pointSrc.meter];
      if (!m) return { error: 'meter ' + pointSrc.meter + ' missing' };
      return {
        value: _dig(m, adapter.valueAt),
        unit: pointSrc.unit || 'kW',
        series: (_dig(m, adapter.seriesAt) || []).map(s => ({ t: s.t, v: s.v })),
        name: m.name,
        ts: (m.latest && m.latest.timestamp) || null,
      };
    }
    return { error: 'unknown adapter type ' + adapter.type };
  }

  const API = { loadPackage, resolveNode, fetchValues };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else global.TwinResolver = API;
})(typeof window !== 'undefined' ? window : globalThis);
