#!/usr/bin/env python3
"""
NWD → APS translation → (properties JSON + optional glb), stdlib-only.

Run on your Mac (no pip installs needed):

    python3 ~/Graduate-Project/convert_nwd_local.py "/path/to/ALL - UCBBE - COMBINED.nwd"

What it does:
  1. Auth to Autodesk Platform Services (credentials baked in below)
  2. Upload the NWD to an OSS bucket (multipart, ~193MB is fine)
  3. Trigger SVF translation, poll until done (5–30 min for this size)
  4. Download the model metadata + object properties JSON
     → saved to data/bechtel_nwd_metadata.json / data/bechtel_nwd_properties.json
  5. If Node.js is installed, also converts SVF → scans/bechtel-full.glb
     (coordinate-preserving!) via `npx forge-convert-utils`

The URN is printed at the end — save it; re-runs with --urn skip the upload.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

CLIENT_ID = "ATa6W7GHsTaqXwYj5tA2zMzZduxlP8IOn91nQOCUzvAz7JOu"
CLIENT_SECRET = "8XnyIQ1ABvT61bidNUATuIhKk9mDUulA1iCXN9k8QxoH9mGHzBQ51lw1ggRh48k3"

APS = "https://developer.api.autodesk.com"
CHUNK = 50 * 1024 * 1024  # 50MB parts
PROJECT_DIR = Path(__file__).resolve().parent


def http(method, url, headers=None, data=None, json_body=None, timeout=120):
    h = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            ct = r.headers.get("Content-Type", "")
            return r.status, (json.loads(body) if "json" in ct and body else body)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:500]


def token():
    print("[1/5] Auth...")
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": "data:read data:write data:create bucket:create bucket:read",
    }).encode()
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    st, body = http("POST", f"{APS}/authentication/v2/token",
                    {"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"}, data=data)
    if st != 200:
        sys.exit(f"auth failed: {st} {body}")
    print("      ok")
    return body["access_token"]


def ensure_bucket(tok, bucket):
    st, _ = http("GET", f"{APS}/oss/v2/buckets/{bucket}/details",
                 {"Authorization": f"Bearer {tok}"})
    if st == 200:
        return
    st, body = http("POST", f"{APS}/oss/v2/buckets",
                    {"Authorization": f"Bearer {tok}"},
                    json_body={"bucketKey": bucket, "policyKey": "transient"})
    if st not in (200, 409):
        sys.exit(f"bucket failed: {st} {body}")


def upload(tok, bucket, src):
    name = urllib.parse.quote(src.name)
    size = src.stat().st_size
    parts = max(1, (size + CHUNK - 1) // CHUNK)
    print(f"[2/5] Upload {src.name} ({size/1e6:.0f} MB, {parts} parts)...")
    st, sig = http("GET", f"{APS}/oss/v2/buckets/{bucket}/objects/{name}/signeds3upload?parts={parts}",
                   {"Authorization": f"Bearer {tok}"})
    if st != 200:
        sys.exit(f"signed upload failed: {st} {sig}")
    with open(src, "rb") as f:
        for i, url in enumerate(sig["urls"]):
            chunk = f.read(CHUNK)
            print(f"      part {i+1}/{parts} ({len(chunk)/1e6:.0f} MB)")
            for attempt in range(3):
                st2, _ = http("PUT", url, data=chunk, timeout=600)
                if st2 in (200, 201):
                    break
                print(f"        retry {attempt+1} (HTTP {st2})")
            else:
                sys.exit("part upload failed")
    st, fin = http("POST", f"{APS}/oss/v2/buckets/{bucket}/objects/{name}/signeds3upload",
                   {"Authorization": f"Bearer {tok}"}, json_body={"uploadKey": sig["uploadKey"]})
    if st != 200:
        sys.exit(f"finalize failed: {st} {fin}")
    print("      ok")
    return fin["objectId"]


def translate(tok, object_id):
    urn = base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")
    print("[3/5] Translate (SVF)...")
    st, body = http("POST", f"{APS}/modelderivative/v2/designdata/job",
                    {"Authorization": f"Bearer {tok}", "x-ads-force": "true"},
                    json_body={"input": {"urn": urn},
                               "output": {"formats": [{"type": "svf", "views": ["3d"]}]}})
    if st not in (200, 201):
        sys.exit(f"translate failed: {st} {body}")
    print("      queued")
    return urn


def poll(tok, urn):
    print("[4/5] Waiting for translation (can take 5–30 min)...")
    start = time.time()
    while True:
        st, m = http("GET", f"{APS}/modelderivative/v2/designdata/{urn}/manifest",
                     {"Authorization": f"Bearer {tok}"})
        if st == 200 and isinstance(m, dict):
            s, p = m.get("status"), m.get("progress", "")
            print(f"      [{int(time.time()-start):4d}s] {s} {p}")
            if s == "success":
                return
            if s in ("failed", "timeout"):
                print(json.dumps(m, indent=2)[:2000])
                sys.exit("translation failed")
        if time.time() - start > 3600:
            sys.exit("timed out")
        time.sleep(15)


def metadata(tok, urn):
    print("[5/5] Downloading metadata/properties...")
    outdir = PROJECT_DIR / "data"
    outdir.mkdir(exist_ok=True)
    st, meta = http("GET", f"{APS}/modelderivative/v2/designdata/{urn}/metadata",
                    {"Authorization": f"Bearer {tok}"})
    if st == 200:
        (outdir / "bechtel_nwd_metadata.json").write_text(json.dumps(meta, indent=1))
        guids = [v["guid"] for v in meta.get("data", {}).get("metadata", [])]
        print(f"      views: {guids}")
        for guid in guids[:1]:
            for attempt in range(40):
                st2, props = http("GET",
                                  f"{APS}/modelderivative/v2/designdata/{urn}/metadata/{guid}/properties?forceget=true",
                                  {"Authorization": f"Bearer {tok}"}, timeout=300)
                if st2 == 200:
                    raw = props if isinstance(props, (bytes, bytearray)) else json.dumps(props).encode()
                    (outdir / "bechtel_nwd_properties.json").write_bytes(raw)
                    print(f"      properties saved ({len(raw)/1e6:.1f} MB)")
                    break
                if st2 == 202:
                    print("      properties extracting... waiting")
                    time.sleep(15)
                    continue
                print(f"      properties unavailable: {st2} {str(props)[:200]}")
                break
    else:
        print(f"      metadata failed: {st}")


def trigger_obj(tok, urn, model_guid):
    """Submit a separate translate job for OBJ output (different format than SVF)."""
    print("[obj-1/3] Triggering OBJ derivative job...")
    st, body = http("POST", f"{APS}/modelderivative/v2/designdata/job",
                    {"Authorization": f"Bearer {tok}", "x-ads-force": "true"},
                    json_body={
                        "input": {"urn": urn},
                        "output": {"formats": [{
                            "type": "obj",
                            "advanced": {
                                "modelGuid": model_guid,
                                "objectIds": [-1]  # -1 = whole model
                            }
                        }]}
                    })
    if st not in (200, 201):
        sys.exit(f"OBJ translate failed: {st} {body}")
    print(f"      queued (status {st})")


def poll_obj(tok, urn):
    """Poll until the OBJ derivative shows up in the manifest."""
    print("[obj-2/3] Waiting for OBJ derivative (typically 2-10 min)...")
    start = time.time()
    while True:
        st, m = http("GET", f"{APS}/modelderivative/v2/designdata/{urn}/manifest",
                     {"Authorization": f"Bearer {tok}"})
        if st == 200 and isinstance(m, dict):
            # Look for any child derivative of type 'obj' that's status 'success'
            obj_done = False
            obj_children = []
            for d in m.get("derivatives", []):
                if d.get("outputType") == "obj":
                    s = d.get("status")
                    p = d.get("progress", "")
                    print(f"      [{int(time.time()-start):4d}s] obj derivative: {s} {p}")
                    if s == "success":
                        obj_done = True
                        obj_children = d.get("children", [])
                    elif s in ("failed", "timeout"):
                        print(json.dumps(d, indent=2)[:1500])
                        sys.exit("OBJ translation failed")
            if obj_done:
                return obj_children
        if time.time() - start > 1800:
            sys.exit("OBJ translation timed out (30 min)")
        time.sleep(15)


def download_obj(tok, urn, children):
    """Walk the children tree, download every resource file (obj, mtl, textures)."""
    print("[obj-3/3] Downloading OBJ + materials...")
    outdir = PROJECT_DIR / "scans" / "bechtel-obj"
    outdir.mkdir(parents=True, exist_ok=True)

    # Flatten the children tree — APS nests resources under views/output sets.
    def walk(items, paths=None):
        paths = paths or []
        for item in items:
            urn_path = item.get("urn", "")
            if urn_path:
                paths.append(urn_path)
            if item.get("children"):
                walk(item["children"], paths)
        return paths

    all_urns = walk(children)
    print(f"      found {len(all_urns)} resources")
    saved = []
    for i, durn in enumerate(all_urns):
        # APS expects URL-encoded resource URN
        encoded = urllib.parse.quote(durn, safe="")
        fname = durn.rsplit("/", 1)[-1] or f"resource_{i}.bin"
        out_path = outdir / fname
        st, data = http("GET",
                        f"{APS}/modelderivative/v2/designdata/{urn}/manifest/{encoded}",
                        {"Authorization": f"Bearer {tok}"}, timeout=600)
        if st == 200 and isinstance(data, (bytes, bytearray)):
            out_path.write_bytes(data)
            saved.append(out_path)
            print(f"      [{i+1}/{len(all_urns)}] {fname} ({len(data)/1e6:.1f} MB)")
        else:
            print(f"      [{i+1}/{len(all_urns)}] {fname} FAIL: {st}")
    print(f"      ✓ {len(saved)} files saved under {outdir}")
    return outdir, saved


def obj_to_glb(obj_dir):
    """Use modern obj2gltf npm package to convert OBJ → glb. No APS auth needed."""
    if not shutil.which("npx"):
        print("\n  npx not found; install Node.js (brew install node) then run:")
        print(f"  npx -y obj2gltf -i <obj-file> -o {obj_dir}/output.glb -b")
        return
    obj_files = list(obj_dir.glob("*.obj"))
    if not obj_files:
        print(f"\n  No .obj file in {obj_dir} — skip glb conversion")
        return
    input_obj = obj_files[0]
    output_glb = obj_dir / "bechtel-full.glb"
    print(f"\n[glb] Converting {input_obj.name} → {output_glb.name} via obj2gltf...")
    cmd = ["npx", "-y", "obj2gltf", "-i", str(input_obj), "-o", str(output_glb), "-b"]
    print("      $", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode == 0 and output_glb.exists():
        size_mb = output_glb.stat().st_size / 1e6
        print(f"      ✓ glb created: {output_glb} ({size_mb:.1f} MB)")
    else:
        print("      glb conversion failed — try Blender or another OBJ→glTF tool")


def to_glb(urn):
    """Bridge: kept for backward compat, but now triggers the OBJ path."""
    # Read the model guid from saved metadata
    meta_file = PROJECT_DIR / "data" / "bechtel_nwd_metadata.json"
    if not meta_file.exists():
        print("\n  No metadata file found; run the full script first.")
        return
    meta = json.loads(meta_file.read_text())
    views = meta.get("data", {}).get("metadata", [])
    if not views:
        print("\n  No views found in metadata; cannot trigger OBJ.")
        return
    model_guid = views[0]["guid"]
    print(f"\n  Using model GUID: {model_guid}")
    tok = token()
    trigger_obj(tok, urn, model_guid)
    children = poll_obj(tok, urn)
    obj_dir, _ = download_obj(tok, urn, children)
    obj_to_glb(obj_dir)


def main():
    args = sys.argv[1:]
    urn = None
    if "--urn" in args:
        urn = args[args.index("--urn") + 1]
    tok = token()
    if not urn:
        if not args:
            sys.exit('usage: python3 convert_nwd_local.py "/path/to/ALL - UCBBE - COMBINED.nwd"')
        src = Path(args[0]).expanduser()
        if not src.exists():
            sys.exit(f"file not found: {src}")
        bucket = f"grimes-twin-{CLIENT_ID.lower()[:20]}"
        ensure_bucket(tok, bucket)
        object_id = upload(tok, bucket, src)
        urn = translate(tok, object_id)
        poll(tok, urn)
    metadata(tok, urn)
    to_glb(urn)
    print("\n──────────────────────────────────────")
    print("URN (저장해둬 — 재실행 시 --urn 으로 업로드 생략):")
    print(urn)
    print("──────────────────────────────────────")


if __name__ == "__main__":
    main()
