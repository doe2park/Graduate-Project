/** Built once per package; no full metadata scan is needed for layer counters. */
export function createRecordIndex(records) {
  const entries = Object.entries(records), byLayer = new Map(), byFloor = new Map();
  const searchable = entries.map(([key, e]) => [key, e, [e.sourceId, e.type, e.category, e.element_tag, e.mark, e.layer, e.level].join(' ').toLowerCase()]);
  for (const [key, e] of entries) {
    if (!byLayer.has(e.layer)) byLayer.set(e.layer, []);
    byLayer.get(e.layer).push(key);
    const floor = e.levelKey || 'UNKNOWN';
    if (!byFloor.has(floor)) byFloor.set(floor, new Map());
    const counts = byFloor.get(floor); counts.set(e.layer, (counts.get(e.layer) || 0) + 1);
  }
  return {
    entries, byLayer, byFloor,
    search(query, limit = 100, selected = null) {
      const q = query.trim().toLowerCase(), shown = []; let count = 0, selectedMatch;
      for (const [key, e, text] of searchable) if (text.includes(q)) { count++; if (shown.length < limit) shown.push([key,e]); else if (key === selected) selectedMatch = [key,e]; }
      if (selectedMatch) shown.push(selectedMatch);
      return {count, shown};
    },
    count({layers, floor = '', hiddenKeys = new Set(), isolatedKey = null}) {
      const enabled = e => e && layers.has(e.layer) && (!floor || (e.levelKey || 'UNKNOWN') === floor);
      if (isolatedKey) return enabled(records[isolatedKey]) && !hiddenKeys.has(isolatedKey) ? 1 : 0;
      let n = 0;
      for (const layer of layers) n += floor ? byFloor.get(floor)?.get(layer) || 0 : byLayer.get(layer)?.length || 0;
      for (const key of hiddenKeys) if (enabled(records[key])) n--;
      return n;
    }
  };
}
