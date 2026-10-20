#!/usr/bin/env python3
"""Write work/local-test.html: one page of clickable local test links (work/ is gitignored).

    python3 scripts/local_test_hub.py            # regenerate the page
    python3 scripts/local_test_hub.py --serve    # also start `http.server 8790` if nothing listens, then open the page

Detects which Gaussian manifests / zone indexes exist under scan-assets/gaussian/ and local Quest packages under
work/gaussian/. Captures and per-capture Gaussian sources mirror CAPTURE_DATES / CAPTURE_GAUSSIAN in scan-compare.html.
Never publishes anything; reads only local files.
"""
import argparse, glob, html, json, os, socket, subprocess, sys, webbrowser
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8790
BASE = f"http://127.0.0.1:{PORT}"
OUT = os.path.join(ROOT, "work", "local-test.html")
# Short fallback list; refreshed from scan-compare.html when its CAPTURE_DATES line can be read.
CAPTURES = ["2026-05-06", "2026-09-17", "2026-10-18"]
GAUSSIAN = {  # capture -> (kind, path), as in scan-compare.html CAPTURE_GAUSSIAN
    "2026-05-06": ("manifest", "scan-assets/gaussian/2026-05-06/viewer.json"),
    "2026-10-18": ("zones", "scan-assets/gaussian/2026-10-18/zones/index.json"),
}


def read_capture_list():
    """Best effort: take CAPTURE_DATES / CAPTURE_GAUSSIAN from scan-compare.html so the hub follows new captures."""
    import re
    try:
        src = open(os.path.join(ROOT, "scan-compare.html"), encoding="utf-8").read()
        m = re.search(r"CAPTURE_DATES=\[([^\]]*)\]", src)
        dates = re.findall(r"'(\d{4}-\d\d-\d\d)'", m.group(1)) if m else []
        g = re.search(r"CAPTURE_GAUSSIAN=\{(.*?)\};", src, re.S)
        gauss = {}
        if g:
            for d, kind, path in re.findall(r"'(\d{4}-\d\d-\d\d)':\{kind:'(\w+)',path:'([^']+)'\}", g.group(1)):
                gauss[d] = (kind, path)
        if dates:
            return sorted(dates), gauss or GAUSSIAN
    except OSError:
        pass
    return CAPTURES, GAUSSIAN


def exists(rel):
    return os.path.isfile(os.path.join(ROOT, rel))


def zone_ids(rel):
    try:
        d = json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))
        return [z.get("id", "?") for z in d.get("zones", [])]
    except (OSError, ValueError):
        return []


def a(href, text, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{html.escape(href)}" target="_blank" rel="noopener">{html.escape(text)}</a>'


def splat_url(kind, path, date=None):
    if kind == "zones":
        return f"{BASE}/scan-splat.html?zones={quote(path, safe='')}" + (f"&capture={date}" if date else "")
    return f"{BASE}/scan-splat.html?manifest={quote(path, safe='')}"


def section_web(dates, gauss):
    rows = []
    for d in dates:
        for mode in ("photo", "splat"):
            cells = []
            have = d in gauss and exists(gauss[d][1]) if mode == "splat" else True
            for label, extra in (("compare", ""), ("overlay lens", "&view=overlay&style=lens"), ("overlay plain", "&view=overlay&style=plain")):
                url = f"{BASE}/scan-compare.html?capture={d}&mode={mode}{extra}"
                if mode == "splat" and d not in gauss:
                    cells.append(f"<td>{a(url, label)}<br><small>no Gaussian (expected note)</small></td>")
                elif mode == "splat" and not have:
                    cells.append(f"<td>{a(url, label)}<br><small>Gaussian not available yet</small></td>")
                else:
                    cells.append(f"<td>{a(url, label)}</td>")
            name = "360° photos" if mode == "photo" else "Gaussian"
            rows.append(f"<tr><th>{d}</th><th>{name}</th>{''.join(cells)}</tr>")
    return ("<table><tr><th>Capture</th><th>Mode</th><th>Compare</th><th>Overlay · Lens</th><th>Overlay · Plain</th></tr>"
            + "".join(rows) + "</table><p class='n'>Old <code>?style=ghost</code> links load Plain (Ghost removed 2026-10-19).</p>")


def section_gaussian(gauss):
    items = []
    may = gauss.get("2026-05-06", ("manifest", "scan-assets/gaussian/2026-05-06/viewer.json"))
    items.append(("May 6 · single scene", may[0], may[1], None, "2026-05-06"))
    oct_ = gauss.get("2026-10-18", ("zones", "scan-assets/gaussian/2026-10-18/zones/index.json"))
    items.append(("Oct 18 · Level 1 zone index", oct_[0], oct_[1], None, "2026-10-18"))
    out = ["<ul>"]
    for label, kind, path, _, date in items:
        if exists(path):
            ids = zone_ids(path) if kind == "zones" else []
            z = f" · zones: {', '.join(ids)}" if ids else ""
            out.append(f"<li>{html.escape(label)}: {a(splat_url(kind, path, date if kind == 'zones' else None), path)}{html.escape(z)}</li>")
        else:
            out.append(f"<li>{html.escape(label)}: <span class='na'>not available yet</span> <code>{html.escape(path)}</code></li>")
    out.append("</ul>")
    return "".join(out)


def section_other():
    pairs = [
        (f"{BASE}/campus-energy-dashboard.html", "campus-energy-dashboard.html (live data)"),
        (f"{BASE}/scan-photo.html?manifest={quote('scan-assets/captures/2026-10-18/panoramas/manifest.json', safe='')}", "scan-photo.html · Oct 18 panoramas"),
        (f"{BASE}/scan-photo.html?manifest={quote('scan-assets/panoramas/manifest.json', safe='')}", "scan-photo.html · May 6 panoramas"),
        (f"{BASE}/scan-bim.html?pane=scan&capture=2026-10-18", "scan-bim.html · scan mesh pane (Oct 18)"),
        (f"{BASE}/scan-bim.html?pane=bim", "scan-bim.html · BIM pane"),
        (f"{BASE}/scan-bim.html?pane=bim&overlay=1", "scan-bim.html · BIM pane, overlay mode"),
    ]
    if exists("capture-local/preview/building_data.json"):
        pairs.insert(1, (f"{BASE}/campus-energy-dashboard.html?buildingData=capture-local/preview/building_data.json",
                         "campus-energy-dashboard.html · localhost override ?buildingData=capture-local/preview/building_data.json"))
    else:
        pairs.insert(1, ("", "campus-energy-dashboard.html ?buildingData override: capture-local/preview/building_data.json not available yet"))
    return "<ul>" + "".join(f"<li>{a(h, t)}</li>" if h else f"<li><span class='na'>{html.escape(t)}</span></li>" for h, t in pairs) + "</ul>"


def section_quest():
    pk = sorted(glob.glob(os.path.join(ROOT, "work", "gaussian", "*", "*", "*", "package", "viewer.json")))
    pk = [os.path.relpath(p, ROOT) for p in pk]
    lines = ["<p>Quest server (separate from 8790; HTTPS, private LAN, port 8929). Replace <code>&lt;LAN-IP&gt;</code> with the Mac's address: "
             "<code>ipconfig getifaddr en0</code> (Wi-Fi; try <code>en1</code>), or run <code>python3 scripts/serve_quest_https.py --dry-run</code>, which prints it. "
             "Open the URL in Quest Browser and accept the self-signed certificate warning.</p><ul>",
             "<li><code>https://&lt;LAN-IP&gt;:8929/scan-xr.html</code> (photo scene)</li>",
             "<li><code>https://&lt;LAN-IP&gt;:8929/scan-xr.html?scene=gaussian</code> (published May 6 Gaussian)</li>",
             "<li><code>https://&lt;LAN-IP&gt;:8929/scan-xr.html?capture=2026-10-18</code></li>"]
    for p in pk:
        lines.append(f"<li>Local package <code>{html.escape(p)}</code>: start the server with <code>--gaussian-package {html.escape(os.path.dirname(p))}</code>, then "
                     f"<code>https://&lt;LAN-IP&gt;:8929/scan-xr.html?scene=gaussian&amp;gaussian={html.escape(p)}</code></li>")
    if not pk:
        lines.append("<li class='na'>No local Gaussian package under work/gaussian/*/*/*/package/ yet.</li>")
    lines.append("</ul>")
    return "".join(lines)


HOWTO = """<pre>
# from the repo root
python3 -m http.server 8790                      # site at http://127.0.0.1:8790/
python3 scripts/local_test_hub.py --serve        # regenerate this page, start 8790 if needed, open it

# Quest (WebXR needs HTTPS), serves on private LAN port 8929; optional local Gaussian package
python3 scripts/serve_quest_https.py
python3 scripts/serve_quest_https.py --gaussian-package work/gaussian/2026-10-18/l1-a/&lt;run&gt;/package

# unit tests (light)
for f in tests/*.test.cjs; do node "$f" || echo FAIL "$f"; done
python3 -m unittest discover -s tests -p 'test_*.py'

# matrix smoke (launches headless Chrome: heavy, avoid while a GPU job runs)
PLAYWRIGHT_MODULE=/Users/yschung/Graduate-Project-media/tools/node_modules/playwright-core node tests/scan-compare-matrix-smoke.cjs
</pre>"""

CSS = ("body{font:15px/1.5 -apple-system,Arial,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#1b2733;background:#fff}"
       "h1{font-size:24px}h2{font-size:17px;margin-top:28px;border-bottom:1px solid #d0d7de;padding-bottom:4px}"
       "table{border-collapse:collapse;width:100%}th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}"
       "small,.n{color:#57606a}.na{color:#9a6700}pre{background:#f6f8fa;padding:12px;overflow:auto;border-radius:6px}code{background:#f6f8fa;padding:1px 4px}a{color:#0969da}")


def build():
    dates, gauss = read_capture_list()
    from datetime import datetime
    body = [
        "<h1>Grimes local test hub</h1>",
        f"<p class='n'>Generated {datetime.now():%Y-%m-%d %H:%M} by scripts/local_test_hub.py. Links need <code>python3 -m http.server {PORT}</code> from the repo root.</p>",
        "<h2>a) Web Scan↔BIM</h2>", section_web(dates, gauss),
        "<h2>b) Gaussian standalone</h2>", section_gaussian(gauss),
        "<h2>c) Other local pages</h2>", section_other(),
        "<h2>d) Quest</h2>", section_quest(),
        "<h2>e) How to run</h2>", HOWTO,
    ]
    page = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Grimes local test hub</title><style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    return OUT


def listening():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serve", action="store_true", help=f"start http.server {PORT} if nothing listens, then open the hub")
    args = ap.parse_args()
    print("wrote", build())
    if args.serve:
        if not listening():
            kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008}
            subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
            print(f"started http.server on {PORT}")
        webbrowser.open(f"{BASE}/work/local-test.html")


if __name__ == "__main__":
    main()
