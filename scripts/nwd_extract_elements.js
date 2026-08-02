#!/usr/bin/env node
/**
 * nwd_extract_elements.js — download a translated SVF derivative from APS and
 * write a glTF where EVERY node is named by its dbId (element identity).
 *
 * svf-utils' GLTFWriter names each output node `fragment.dbid` — that is the
 * whole reason this pipeline preserves element identity where the old
 * mep-only export (8 discipline meshes) could not.
 *
 * Usage:
 *   export APS_CLIENT_ID=... APS_CLIENT_SECRET=...
 *   node scripts/nwd_extract_elements.js <URN> <outdir>
 *
 * Requires: npm install svf-utils   (Node 18+, uses global fetch)
 */
const path = require('path');

const BASE = 'https://developer.api.autodesk.com';

function findSvfViewables(derivative, found) {
    if (derivative.type === 'resource' && derivative.role === 'graphics' &&
        derivative.mime === 'application/autodesk-svf') {
        found.push(derivative.guid);
    }
    for (const child of derivative.children || []) findSvfViewables(child, found);
}

async function main() {
    const [urn, outdir] = process.argv.slice(2);
    if (!urn || !outdir) {
        console.error('Usage: node nwd_extract_elements.js <URN> <outdir>');
        process.exit(1);
    }
    const { APS_CLIENT_ID, APS_CLIENT_SECRET } = process.env;
    if (!APS_CLIENT_ID || !APS_CLIENT_SECRET) {
        console.error('Set APS_CLIENT_ID / APS_CLIENT_SECRET env vars.');
        process.exit(1);
    }
    const { SVFReader, GLTFWriter, TwoLeggedAuthenticationProvider } = require('svf-utils');
    const auth = new TwoLeggedAuthenticationProvider(APS_CLIENT_ID, APS_CLIENT_SECRET);

    // 1. Find the SVF viewable GUID(s) in the manifest
    console.log('[svf] fetching manifest ...');
    const token = await auth.getToken(['viewables:read']);
    const mres = await fetch(`${BASE}/modelderivative/v2/designdata/${urn}/manifest`,
        { headers: { Authorization: `Bearer ${token}` } });
    if (!mres.ok) throw new Error(`manifest HTTP ${mres.status}: ${await mres.text()}`);
    const manifest = await mres.json();
    const guids = [];
    for (const d of manifest.derivatives || []) findSvfViewables(d, guids);
    if (!guids.length) throw new Error('No SVF viewable found in manifest (was the model translated with type "svf"?)');
    console.log(`[svf] ${guids.length} SVF viewable(s): ${guids.join(', ')}`);

    // 2. Read each viewable and write glTF (nodes named by dbId)
    for (let i = 0; i < guids.length; i++) {
        const guid = guids[i];
        const dest = path.join(outdir, guids.length > 1 ? `gltf_${i}` : 'gltf');
        console.log(`[svf] reading viewable ${guid} ...`);
        const reader = await SVFReader.FromDerivativeService(urn, guid, auth);
        const svf = await reader.read({ log: (msg) => console.log('  ', msg) });
        const writer = new GLTFWriter({
            deduplicate: true,
            skipUnusedUvs: true,
            center: false,          // keep original coords — calibration depends on them
            log: (msg) => console.log('  ', msg),
        });
        await writer.write(svf, dest);
        console.log(`[svf] ✓ glTF written to ${dest} (nodes named by dbId)`);
    }
}

main().catch((err) => { console.error(err); process.exit(1); });
