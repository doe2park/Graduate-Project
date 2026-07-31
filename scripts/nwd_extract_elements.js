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
 * Output: <outdir>/gltf/output.gltf (+ bins). Pack it with:
 *   npx @gltf-transform/cli optimize <outdir>/gltf/output.gltf out.glb \
 *       --compress draco --simplify false --palette false --join false --flatten false
 *
 * Requires: npm install svf-utils   (Node 18+)
 */
const path = require('path');

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

    console.log(`[svf] resolving derivatives for URN ...`);
    const reader = await SVFReader.FromDerivativeService(urn, auth);
    console.log(`[svf] reading geometry ...`);
    const svf = await reader.read({ log: (msg) => console.log('  ', msg) });

    const writer = new GLTFWriter({
        deduplicate: true,
        skipUnusedUvs: true,
        center: false,          // keep original coords — calibration depends on them
        log: (msg) => console.log('  ', msg),
    });
    const dest = path.join(outdir, 'gltf');
    await writer.write(svf, dest);
    console.log(`[svf] ✓ glTF written to ${dest} (nodes named by dbId)`);
}

main().catch((err) => { console.error(err); process.exit(1); });
