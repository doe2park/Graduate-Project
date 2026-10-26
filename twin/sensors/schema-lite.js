/* Tiny JSON Schema subset validator (no dependency; the repo has no build step). Supports exactly what the sensor
   schemas use: type (incl. arrays like ["string","null"]), enum, pattern, minLength, minimum, maximum, required,
   properties, additionalProperties:false, items, minItems, maxItems and $ref to a sibling schema passed in `refs`.
   validate(schema, value, refs) -> list of error strings (empty = valid). Used by tests and by adapters. */
(function (root, factory) {
  const api = factory();
  if (root) root.SchemaLite = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';
const typeOf = v => v === null ? 'null' : Array.isArray(v) ? 'array' : Number.isInteger(v) ? 'integer' : typeof v;
const isType = (v, t) => t === 'number' ? typeof v === 'number' && Number.isFinite(v) : t === 'integer' ? Number.isInteger(v) : typeOf(v) === t;
function validate(schema, value, refs, path, out) {
  path = path || '$'; out = out || [];
  if (schema.$ref) { const r = refs && refs[schema.$ref]; if (!r) { out.push(path + ': unresolved $ref ' + schema.$ref); return out; } return validate(r, value, refs, path, out); }
  if (schema.type) { const ts = [].concat(schema.type); if (!ts.some(t => isType(value, t))) { out.push(path + ': expected ' + ts.join('|') + ', got ' + typeOf(value)); return out; } }
  if (schema.enum && !schema.enum.includes(value)) out.push(path + ': not one of ' + schema.enum.join('|'));
  if (typeof value === 'string') {
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) out.push(path + ': does not match ' + schema.pattern);
    if (schema.minLength !== undefined && value.length < schema.minLength) out.push(path + ': shorter than ' + schema.minLength);
  }
  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) out.push(path + ': below ' + schema.minimum);
    if (schema.maximum !== undefined && value > schema.maximum) out.push(path + ': above ' + schema.maximum);
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) out.push(path + ': fewer than ' + schema.minItems + ' items');
    if (schema.maxItems !== undefined && value.length > schema.maxItems) out.push(path + ': more than ' + schema.maxItems + ' items');
    if (schema.items) value.forEach((v, i) => validate(schema.items, v, refs, path + '[' + i + ']', out));
  }
  if (typeOf(value) === 'object') {
    for (const k of schema.required || []) if (!(k in value)) out.push(path + ': missing ' + k);
    for (const [k, s] of Object.entries(schema.properties || {})) if (k in value) validate(s, value[k], refs, path + '.' + k, out);
    if (schema.additionalProperties === false) for (const k of Object.keys(value)) if (!(k in (schema.properties || {}))) out.push(path + ': unexpected ' + k);
  }
  return out;
}
return {validate};
});
