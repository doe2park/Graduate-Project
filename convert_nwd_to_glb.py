#!/usr/bin/env python3
"""
Convert a .nwd (or .nwc / .rvt / .ifc) into .glb for the Grimes XR viewer.

Pipeline:
  1. Auth with Autodesk Platform Services (APS) using client credentials
  2. Create / reuse an OSS bucket
  3. Upload the source file (multipart for files > 5 MB)
  4. Trigger SVF derivative translation (server-side, ~1–10 min depending on size)
  5. Poll until translation completes
  6. Invoke the open-source `aps-modelderivative-svf-utils` Node tool to
     pull SVF derivatives down and convert them into a single .glb
  7. Save to scans/<output>.glb so the existing Interior loader can pick it up

ONE-TIME SETUP:
  a) Sign up at https://aps.autodesk.com (free)
  b) "Create Application" → pick any name → callback URL can be http://localhost
  c) Copy the Client ID + Client Secret
  d) Install dependencies:
        pip install requests
        npm install -g aps-modelderivative-svf-utils   # or: forge-convert-utils
  e) Set env vars (or pass --client-id / --client-secret):
        export APS_CLIENT_ID="..."
        export APS_CLIENT_SECRET="..."

USAGE:
    python convert_nwd_to_glb.py path/to/grimes.nwd
    # optional flags:
    python convert_nwd_to_glb.py grimes.nwd --output scans/grimes-full.glb --bucket my-bucket

The translation runs once on Autodesk's cloud; the URN is reusable so re-running
this script with the same file skips re-upload + re-translation.
"""

import argparse
import base64
import os
import sys
import time
import json
import subprocess
import shutil
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing requests. Run: pip install requests")

APS_BASE     = "https://developer.api.autodesk.com"
TOKEN_URL    = f"{APS_BASE}/authentication/v2/token"
OSS_BASE     = f"{APS_BASE}/oss/v2"
MD_BASE      = f"{APS_BASE}/modelderivative/v2"
CHUNK_SIZE   = 5 * 1024 * 1024            # 5 MB — APS multipart minimum
POLL_SECS    = 8                          # poll cadence
POLL_TIMEOUT = 60 * 30                    # 30 min ceiling


# ─── auth ──────────────────────────────────────────────────────────────────
def get_token(client_id: str, client_secret: str) -> str:
    print("[1/6] Auth: requesting access token...")
    r = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials",
              "scope": "data:read data:write data:create bucket:create bucket:read"},
        timeout=30,
    )
    r.raise_for_status()
    tok = r.json()["access_token"]
    print(f"      ✓ token acquired (truncated: {tok[:14]}...)")
    return tok


# ─── bucket ────────────────────────────────────────────────────────────────
def ensure_bucket(token: str, bucket_key: str):
    print(f"[2/6] Bucket: ensuring '{bucket_key}' exists...")
    r = requests.get(f"{OSS_BASE}/buckets/{bucket_key}/details",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code == 200:
        print(f"      ✓ existing bucket reused")
        return
    if r.status_code == 404:
        cr = requests.post(
            f"{OSS_BASE}/buckets",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"bucketKey": bucket_key, "policyKey": "transient"},  # 24hr lifetime — file gets cleaned
            timeout=30,
        )
        cr.raise_for_status()
        print(f"      ✓ bucket created (24hr transient policy)")
        return
    r.raise_for_status()


# ─── upload ────────────────────────────────────────────────────────────────
def upload(token: str, bucket: str, src: Path) -> str:
    """Upload to OSS using S3-signed URL flow. Returns the objectId (urn:adsk... unencoded)."""
    name = src.name
    size = src.stat().st_size
    print(f"[3/6] Upload: {name} ({size/1024/1024:.1f} MB) → OSS")

    n_parts = max(1, (size + CHUNK_SIZE - 1) // CHUNK_SIZE)
    headers = {"Authorization": f"Bearer {token}"}

    # Signed URLs expire in ~2 minutes (X-Amz-Expires=119), so batch-fetching
    # all part URLs upfront 403s partway through a big upload. Request each
    # part's URL right before uploading it, and refresh once on 403.
    upload_key = None

    def signed_url_for(part_no: int) -> str:
        nonlocal upload_key
        params = {"parts": 1, "firstPart": part_no}
        if upload_key:
            params["uploadKey"] = upload_key
        r = requests.get(
            f"{OSS_BASE}/buckets/{bucket}/objects/{name}/signeds3upload",
            headers=headers, params=params, timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        upload_key = d["uploadKey"]
        return d["urls"][0]

    with open(src, "rb") as f:
        for i in range(n_parts):
            chunk = f.read(CHUNK_SIZE)
            print(f"      uploading part {i+1}/{n_parts} ({len(chunk)/1024/1024:.1f} MB)...")
            up = requests.put(signed_url_for(i + 1), data=chunk, timeout=300)
            if up.status_code == 403:   # URL expired mid-flight — refresh once
                up = requests.put(signed_url_for(i + 1), data=chunk, timeout=300)
            up.raise_for_status()

    fin = requests.post(
        f"{OSS_BASE}/buckets/{bucket}/objects/{name}/signeds3upload",
        headers={**headers, "Content-Type": "application/json"},
        json={"uploadKey": upload_key},
        timeout=60,
    )
    fin.raise_for_status()
    object_id = fin.json()["objectId"]   # e.g. urn:adsk.objects:os.object:bucket/name
    print(f"      ✓ upload complete")
    return object_id


# ─── translate ─────────────────────────────────────────────────────────────
def trigger_translation(token: str, object_id: str) -> str:
    urn_b64 = base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")
    print(f"[4/6] Translate: triggering SVF translation (urn={urn_b64[:24]}...)")

    # Correct Model Derivative endpoint is designdata/job.
    # IMPORTANT: request "svf" (not svf2) — svf-utils' SVFReader consumes the
    # classic SVF derivative; SVF2/OTG is a different internal format.
    attempts = [
        {
            "url":  f"{MD_BASE}/designdata/job",
            "body": {"input": {"urn": urn_b64},
                     "output": {"destination": {"region": "us"},
                                "formats": [{"type": "svf", "views": ["3d"]}]}},
            "label": "designdata/job + destination us + svf",
        },
        {
            "url":  f"{MD_BASE}/designdata/job",
            "body": {"input": {"urn": urn_b64},
                     "output": {"formats": [{"type": "svf", "views": ["3d"]}]}},
            "label": "designdata/job (no destination)",
        },
    ]

    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json",
               # no x-ads-force: if the derivative already exists, the job
               # returns immediately instead of re-translating for ~10 min
               }

    for i, a in enumerate(attempts, 1):
        print(f"      try {i}/{len(attempts)}: {a['label']}")
        r = requests.post(a["url"], headers=headers, json=a["body"], timeout=60)
        if r.ok:
            print(f"      ✓ HTTP {r.status_code} — translation queued via «{a['label']}»")
            return urn_b64
        # Show why it failed (truncated)
        try:
            err = r.json()
            msg = err.get("developerMessage") or err.get("diagnostic") or str(err)[:120]
        except Exception:
            msg = r.text[:120]
        print(f"        ✗ HTTP {r.status_code}: {msg}")

    print("\n      All variations failed. Last response headers:", dict(r.headers))
    print("      Last response body:", r.text[:1500])
    sys.exit("translation request failed across all known endpoint shapes")


def poll_translation(token: str, urn: str):
    print(f"[5/6] Poll: waiting for translation to finish (timeout {POLL_TIMEOUT//60} min)...")
    start = time.time()
    while True:
        r = requests.get(
            f"{MD_BASE}/designdata/{urn}/manifest",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if r.status_code == 200:
            m = r.json()
            status = m.get("status", "?")
            progress = m.get("progress", "")
            elapsed = int(time.time() - start)
            print(f"      [{elapsed:4d}s] status={status} progress={progress}")
            if status == "success":
                print("      ✓ translation complete")
                return
            if status in ("failed", "timeout"):
                print(json.dumps(m, indent=2))
                sys.exit(f"translation {status}")
        elif r.status_code != 404:
            r.raise_for_status()
        if time.time() - start > POLL_TIMEOUT:
            sys.exit("translation polling timed out")
        time.sleep(POLL_SECS)


# ─── SVF → glb (element identity) ──────────────────────────────────────────
def svf_to_glb(urn: str, token: str, out_path: Path):
    """svf-utils' GLTFWriter names every output node by its dbId — that gives
    the element-tier identity the twin needs (the old mep-only export had only
    8 discipline meshes). Extract glTF, then pack to glb WITHOUT
    join/flatten/palette so node names survive."""
    print(f"[6/7] Convert SVF → glb (element identity): {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    here = Path(__file__).resolve().parent
    extractor = here / "scripts" / "nwd_extract_elements.js"
    workdir = out_path.parent / "_svf_work"
    workdir.mkdir(parents=True, exist_ok=True)

    if subprocess.run(["node", "-e", "require('svf-utils')"], cwd=str(here),
                      capture_output=True).returncode != 0:
        print("      installing svf-utils (local npm) ...")
        subprocess.run(["npm", "install", "--no-save", "svf-utils"],
                       cwd=str(here), check=True)

    r = subprocess.run(["node", str(extractor), urn, str(workdir)],
                       cwd=str(here), env=os.environ)
    if r.returncode != 0:
        sys.exit("SVF → glTF extraction failed (check output above)")

    gltfs = sorted(workdir.rglob("*.gltf"))
    if not gltfs:
        sys.exit(f"No .gltf produced under {workdir}")

    print("      packing to glb (Draco, node names preserved) ...")
    r = subprocess.run(["npx", "-y", "@gltf-transform/cli", "optimize",
                        str(gltfs[0]), str(out_path),
                        "--compress", "draco", "--simplify", "false",
                        "--palette", "false", "--join", "false", "--flatten", "false"])
    if r.returncode != 0:
        sys.exit("glb packing failed")

    sz = out_path.stat().st_size / 1024 / 1024
    print(f"      ✓ wrote {out_path} ({sz:.1f} MB)")


# ─── properties sidecar ────────────────────────────────────────────────────
def fetch_properties(urn: str, token: str, out_path: Path):
    """dbId → {name, externalId, type/category/level} sidecar for the
    element-tier binding.json work. Matches GLB node names (dbIds)."""
    print(f"[7/7] Properties sidecar: {out_path}.meta.json")
    H = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{MD_BASE}/designdata/{urn}/metadata", headers=H, timeout=60)
    r.raise_for_status()
    guid = r.json()["data"]["metadata"][0]["guid"]

    props = None
    for _ in range(60):   # big models: server-side extraction can 202 for a while
        r = requests.get(f"{MD_BASE}/designdata/{urn}/metadata/{guid}/properties",
                         params={"forceget": "true"}, headers=H, timeout=600)
        if r.status_code == 202:
            time.sleep(POLL_SECS); continue
        r.raise_for_status()
        props = r.json()["data"]["collection"]
        break
    if props is None:
        sys.exit("properties extraction timed out")

    slim = {}
    for p in props:
        entry = {"name": p.get("name", ""), "externalId": p.get("externalId", "")}
        po = p.get("properties", {}) or {}
        for group in ("Item", "Element"):
            g = po.get(group)
            if isinstance(g, dict):
                for k in ("Type", "Category", "Layer", "Level", "Source File"):
                    if k in g:
                        entry[k.lower().replace(" ", "_")] = g[k]
        slim[str(p["objectid"])] = entry

    meta_path = Path(str(out_path) + ".meta.json")
    with open(meta_path, "w") as f:
        json.dump({"_schema": "twin-elements/1", "_source": urn, "elements": slim}, f)
    print(f"      ✓ {len(slim)} elements → {meta_path}")


# ─── main ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="Path to .nwd / .nwc / .rvt / .ifc")
    ap.add_argument("--output", default="scans/grimes-full.glb",
                    help="Output .glb path (default: scans/grimes-full.glb)")
    ap.add_argument("--bucket", default=None,
                    help="OSS bucket key (must be globally unique). Default: derived from client id.")
    ap.add_argument("--client-id",     default=os.environ.get("APS_CLIENT_ID"),
                    help="APS Client ID (or set APS_CLIENT_ID env)")
    ap.add_argument("--client-secret", default=os.environ.get("APS_CLIENT_SECRET"),
                    help="APS Client Secret (or set APS_CLIENT_SECRET env)")
    ap.add_argument("--skip-upload", action="store_true",
                    help="Skip upload+translate (re-use existing URN, useful when re-extracting glb)")
    ap.add_argument("--urn", default=None,
                    help="If --skip-upload, supply the URN here")
    args = ap.parse_args()

    if not args.client_id or not args.client_secret:
        sys.exit("Missing APS credentials — see top of this script for one-time setup.")

    src = Path(args.source).expanduser().resolve()
    if not args.skip_upload and not src.exists():
        sys.exit(f"Source file not found: {src}")

    bucket = args.bucket or f"grimes-twin-{args.client_id.lower()[:24]}".replace("_", "-")
    token = get_token(args.client_id, args.client_secret)

    if args.skip_upload:
        if not args.urn:
            sys.exit("--skip-upload requires --urn")
        urn = args.urn
        print(f"[skip] Reusing URN {urn[:24]}... — will (re)trigger translation")
        # Decode URN back to object_id so we can re-trigger translation
        pad = '=' * (-len(urn) % 4)
        object_id = base64.urlsafe_b64decode(urn + pad).decode()
        urn = trigger_translation(token, object_id)
        poll_translation(token, urn)
    else:
        ensure_bucket(token, bucket)
        object_id = upload(token, bucket, src)
        urn = trigger_translation(token, object_id)
        poll_translation(token, urn)

    svf_to_glb(urn, token, Path(args.output))
    fetch_properties(urn, token, Path(args.output))

    print("\n────────────────────────────────────────────────────")
    print(f"  Done. Now wire it into the Interior loader:")
    print(f"  Edit data/grimes-interior.json:")
    print(f'      "model": {{ "path": "./{args.output}", "format": "glb" }}')
    print("  Reload grimes-xr.html and click 🏛 Interior.")
    print("────────────────────────────────────────────────────")
    print(f"  URN (save for re-runs):")
    print(f"  {urn}")
    print("────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
