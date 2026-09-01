#!/usr/bin/env node
/**
 * nwd_extract_subset.js — re-export ONLY a chosen set of dbIds from the SVF,
 * one named node per fragment, no instancing dedup. Small output, full identity.
 *
 * Why: the 2026-08-03 master used deduplicate:true + gltf-transform instancing,
 * which stripped names from 284,709 repeated fragments (99% of receptacles,
 * 80% of light fixtures ...). A full --no-dedup re-export of all 741k elements
 * does not fit on the Mac (ENOSPC at the glTF write, 2026-09-01). The writer
 * has a per-fragment filter, so we export just the elements the twin binds.
 *
 * Usage:
 *   export APS_CLIENT_ID=... APS_CLIENT_SECRET=...
 *   node scripts/nwd_extract_subset.js <URN> <outdir> <wanted_dbids.json>
 *
 * wanted_dbids.json = JSON array of integer dbIds (leaf or ancestor — the
 * filter matches fragment dbIds directly; build the list with the externalId
 * prefix walk in scripts/extract_layer.py so every leaf of a wanted element
 * is included). Output: <outdir>/output.gltf + .bin (pack later with
 * gltf-transform: --palette false --join false --flatten false).
 */
const fs = require('fs');
const path = require('path');
const BASE = 'https://developer.api.autodesk.com';

function findSvfViewables(d, found) {
    if (d.type === 'resource' && d.role === 'graphics' && d.mime === 'application/autodesk-svf') found.push(d.guid);
    for (const c of d.children || []) findSvfViewables(c, found);
}

async function main() {
    const [urn, outdir, wantedPath] = process.argv.slice(2);
    if (!urn || !outdir || !wantedPath) {
        console.error('Usage: node nwd_extract_subset.js <URN> <outdir> <wanted_dbids.json>');
        process.exit(1);
    }
    const { APS_CLIENT_ID, APS_CLIENT_SECRET } = process.env;
    if (!APS_CLIENT_ID || !APS_CLIENT_SECRET) { console.error('Set APS_CLIENT_ID / APS_CLIENT_SECRET'); process.exit(1); }
    const wanted = new Set(JSON.parse(fs.readFileSync(wantedPath, 'utf8')).map(Number));
    console.log(`[subset] ${wanted.size} wanted dbIds`);

    const { SVFReader, GLTFWriter, TwoLeggedAuthenticationProvider } = require('svf-utils');
    const auth = new TwoLeggedAuthenticationProvider(APS_CLIENT_ID, APS_CLIENT_SECRET);
    const token = await auth.getToken(['viewables:read']);
    const mres = await fetch(`${BASE}/modelderivative/v2/designdata/${urn}/manifest`, { headers: { Authorization: `Bearer ${token}` } });
    if (!mres.ok) throw new Error(`manifest HTTP ${mres.status}`);
    const guids = [];
    for (const d of (await mres.json()).derivatives || []) findSvfViewables(d, guids);
    if (!guids.length) throw new Error('No SVF viewable in manifest');

    const reader = await SVFReader.FromDerivativeService(urn, guids[0], auth);
    const svf = await reader.read({ log: (m) => { if (!/meshpack/.test(m)) console.log('  ', m); } });
    let kept = 0, total = 0;
    const writer = new GLTFWriter({
        deduplicate: false,       // one node per fragment → every node keeps its dbId name
        skipUnusedUvs: true,
        center: false,            // same frame as the master
        filter: (dbid) => { total++; const k = wanted.has(dbid); if (k) kept++; return k; },
        log: (m) => console.log('  ', m),
    });
    fs.mkdirSync(outdir, { recursive: true });
    await writer.write(svf, outdir);
    console.log(`[subset] ✓ wrote ${outdir} — kept ${kept} of ${total} fragments`);
}
main().catch((e) => { console.error(e); process.exit(1); });
