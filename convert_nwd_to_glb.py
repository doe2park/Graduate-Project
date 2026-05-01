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

    sig = requests.get(
        f"{OSS_BASE}/buckets/{bucket}/objects/{name}/signeds3upload",
        headers=headers, params={"parts": n_parts}, timeout=60,
    )
    sig.raise_for_status()
    sig_data = sig.json()
    upload_key = sig_data["uploadKey"]

    with open(src, "rb") as f:
        for i, url in enumerate(sig_data["urls"]):
            chunk = f.read(CHUNK_SIZE)
            print(f"      uploading part {i+1}/{n_parts} ({len(chunk)/1024/1024:.1f} MB)...")
            up = requests.put(url, data=chunk, timeout=300)
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
    r = requests.post(
        f"{MD_BASE}/designs",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "input":  {"urn": urn_b64},
            "output": {"formats": [{"type": "svf", "views": ["3d"]}]},
        },
        timeout=60,
    )
    r.raise_for_status()
    print(f"      ✓ translation queued")
    return urn_b64


def poll_translation(token: str, urn: str):
    print(f"[5/6] Poll: waiting for translation to finish (timeout {POLL_TIMEOUT//60} min)...")
    start = time.time()
    while True:
        r = requests.get(
            f"{MD_BASE}/designs/{urn}/manifest",
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


# ─── SVF → glb ─────────────────────────────────────────────────────────────
def svf_to_glb(urn: str, token: str, out_path: Path):
    print(f"[6/6] Convert SVF → glb: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # We delegate to a community Node tool. Two known-good options:
    #   a) aps-modelderivative-svf-utils  (newer name)
    #   b) forge-convert-utils            (legacy but still works)
    candidates = ["aps-modelderivative-svf-utils", "forge-convert-utils"]
    tool = None
    for cand in candidates:
        if shutil.which(cand) or shutil.which(f"{cand}-svf2gltf"):
            tool = cand
            break

    if not tool:
        print("\n  ⚠ Node tool not found on PATH.")
        print("    Install one of:")
        for c in candidates:
            print(f"      npm install -g {c}")
        print(f"\n    Then run:")
        print(f"      forge-svf2gltf -t glb -o {out_path} {urn}")
        print(f"      (uses APS_CLIENT_ID / APS_CLIENT_SECRET env vars)")
        sys.exit(0)

    cmd = [f"{tool}-svf2gltf" if shutil.which(f"{tool}-svf2gltf") else tool,
           "-t", "glb", "-o", str(out_path), urn]
    print(f"      $ {' '.join(cmd)}")
    env = os.environ.copy()
    env.setdefault("APS_CLIENT_ID", env.get("FORGE_CLIENT_ID", ""))
    env.setdefault("APS_CLIENT_SECRET", env.get("FORGE_CLIENT_SECRET", ""))
    r = subprocess.run(cmd, env=env)
    if r.returncode != 0:
        sys.exit("SVF → glb conversion failed (check Node tool output above)")

    sz = out_path.stat().st_size / 1024 / 1024
    print(f"      ✓ wrote {out_path} ({sz:.1f} MB)")


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
        print(f"[skip] Reusing URN {urn[:24]}...")
    else:
        ensure_bucket(token, bucket)
        object_id = upload(token, bucket, src)
        urn = trigger_translation(token, object_id)
        poll_translation(token, urn)

    svf_to_glb(urn, token, Path(args.output))

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
