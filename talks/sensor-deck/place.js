/* Callout placement for the test-install slides (12-16). PURE (no DOM): unit-tested in tests/talks-deck.test.cjs and
   inlined into index.html by gen.py. Rects are [x0, y0, x1, y1] in one pixel space (stage px for the deck).

   Rule (place):
     hard = other markers' badges, the selected marker's own badge + halo, the selected sensor's drawn geometry (pipe,
            cable, ring), viewer badges; leaving the image counts as hard too.
     soft = the other sensors' geometry and tints (avoided when possible, never at the cost of a hard overlap).
     0. A previously used spot (opts.prefer) is kept while it stays clear, so the card does not jump while the live view moves.
     For each card size, largest (biggest chart) first:
       1. Adjacent: 12 spots beside the marker (right, left, below, above, the four diagonals, then right / left slid up and
          down). The first with no hard and no soft overlap wins.
       2. Near: a grid of positions inside the image, nearest to the marker first, within opts.near[size] px of it (default
          120 px for the two larger sizes, 260 px for the smallest), same test. The leader line bridges the gap.
     3. Otherwise the spot (any size, any of the above) with no hard overlap and the least soft overlap; else the least
        hard overlap. Overlaps smaller than opts.tol px on a side are ignored. */
(function (g) {
  'use strict';
  const area = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  const shrink = (r, t) => [r[0] + t, r[1] + t, r[2] - t, r[3] - t];

  /* shapes -> small rects: ['seg', x1, y1, x2, y2, halfWidth] | ['ring', cx, cy, r, halfWidth] | ['box', x0, y0, x1, y1] |
     ['dot', cx, cy, r]. Long segments are cut into pieces (<= step px) so a diagonal pipe does not block its whole bbox. */
  function shapeRects(shapes, scale = 1, step = 24) {
    const out = [], s = scale;
    const seg = (x1, y1, x2, y2, hw) => {
      const n = Math.max(1, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / step));
      for (let i = 0; i < n; i++) {
        const ax = x1 + (x2 - x1) * i / n, ay = y1 + (y2 - y1) * i / n, bx = x1 + (x2 - x1) * (i + 1) / n, by = y1 + (y2 - y1) * (i + 1) / n;
        out.push([Math.min(ax, bx) - hw, Math.min(ay, by) - hw, Math.max(ax, bx) + hw, Math.max(ay, by) + hw]);
      }
    };
    for (const sh of shapes || []) {
      const [k, ...v] = sh, q = v.map(x => x * s);
      if (k === 'seg') seg(q[0], q[1], q[2], q[3], q[4]);
      else if (k === 'ring') { const N = 24; for (let i = 0; i < N; i++) { const a = 2 * Math.PI * i / N, b = 2 * Math.PI * (i + 1) / N; seg(q[0] + q[2] * Math.cos(a), q[1] + q[2] * Math.sin(a), q[0] + q[2] * Math.cos(b), q[1] + q[2] * Math.sin(b), q[3]); } }
      else if (k === 'box') out.push([q[0], q[1], q[2], q[3]]);
      else if (k === 'dot') out.push([q[0] - q[2], q[1] - q[2], q[0] + q[2], q[1] + q[2]]);
    }
    return out;
  }

  function score(r, bounds, hard, soft, tol) {
    const inside = area(r, bounds), full = (r[2] - r[0]) * (r[3] - r[1]);
    let h = full - inside, s = 0;
    for (const o of hard) h += area(r, shrink(o, tol));
    for (const o of soft) s += area(r, shrink(o, tol));
    return [h, s];
  }
  const distTo = (r, x, y) => Math.hypot(Math.max(r[0] - x, 0, x - r[2]), Math.max(r[1] - y, 0, y - r[3]));

  /* adjacent spots, in preference order: [dx, dy] of the card's top-left relative to the anchor */
  function adjacent(w, h, gap) {
    const d = gap * 0.72;
    return [[gap, -h / 2], [-gap - w, -h / 2], [-w / 2, gap], [-w / 2, -gap - h],
            [d, d], [d, -d - h], [-d - w, d], [-d - w, -d - h],
            [gap, -h * 0.15], [gap, -h * 0.85], [-gap - w, -h * 0.15], [-gap - w, -h * 0.85]];
  }

  function place(o) {
    const {x: ax, y: ay} = o.anchor, B = o.bounds, hard = o.hard || [], soft = o.soft || [], tol = o.tol == null ? 2 : o.tol;
    const gap = o.gap == null ? 40 : o.gap, step = o.step || 12, sizes = o.sizes;
    const near = ti => Array.isArray(o.near) ? o.near[Math.min(ti, o.near.length - 1)] : o.near != null ? o.near : ti === sizes.length - 1 ? 260 : 120;
    const cand = (ti, dx, dy, stage) => {
      const {w, h} = sizes[ti], r = [ax + dx, ay + dy, ax + dx + w, ay + dy + h], [hs, ss] = score(r, B, hard, soft, tol);
      return {x: r[0], y: r[1], w, h, tier: ti, dx, dy, hard: hs, soft: ss, stage, dist: distTo(r, ax, ay)};
    };
    const all = [];
    if (o.prefer && sizes[o.prefer.tier]) { const c = cand(o.prefer.tier, o.prefer.dx, o.prefer.dy, 0); if (!c.hard && !c.soft) return c; all.push(c); }
    for (let ti = 0; ti < sizes.length; ti++) {
      for (const [dx, dy] of adjacent(sizes[ti].w, sizes[ti].h, gap)) { const c = cand(ti, dx, dy, 1); if (!c.hard && !c.soft) return c; all.push(c); }
      const {w, h} = sizes[ti], grid = [], lim = near(ti);
      for (let y = B[1]; y <= B[3] - h + 0.01; y += step) for (let x = B[0]; x <= B[2] - w + 0.01; x += step) {
        const r = [x, y, x + w, y + h], d = distTo(r, ax, ay);
        if (d <= lim) grid.push([d, x, y]);
      }
      grid.sort((a, b) => a[0] - b[0]);
      for (const [, x, y] of grid) { const c = cand(ti, x - ax, y - ay, 2); if (!c.hard && !c.soft) return c; all.push(c); }
    }
    all.sort((a, b) => (a.hard - b.hard) || (a.soft - b.soft) || (a.dist - b.dist));
    return Object.assign(all[0], {stage: 3});
  }

  /* leader line: from the anchor (offset r0 px out, past the halo) to the nearest point of the card */
  function leader(c, x, y, r0 = 0) {
    const px = Math.max(c.x, Math.min(c.x + c.w, x)), py = Math.max(c.y, Math.min(c.y + c.h, y)), L = Math.hypot(px - x, py - y);
    if (L <= r0 + 2) return null;
    return [x + (px - x) * r0 / L, y + (py - y) * r0 / L, px, py];
  }

  const TwPlace = {place, shapeRects, leader, area, score};
  if (typeof module !== 'undefined' && module.exports) module.exports = TwPlace; else g.TwPlace = TwPlace;
})(this);
