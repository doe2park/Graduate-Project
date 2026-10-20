#!/usr/bin/env python3
"""Open local review material for the owner (cross-platform). Used by the 'Review:' VS Code tasks.

    python3 scripts/review_open.py privacy   # Oct 18 Level 1 privacy contact sheets + checklist
    python3 scripts/review_open.py gaussian  # Gaussian before/after image + live compare URL
    python3 scripts/review_open.py floors    # localhost-only multifloor walk URL

Nothing here changes or publishes data. Pages need the site server (Task: 'Local: serve site (8790) + open test hub').
"""
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8790"
CHECKLIST = """
PRIVACY REVIEW CHECKLIST (Oct 18 Level 1 photos, review before anything is published)
  1. Faces: any readable face left unblurred (also reflections in glass, photos on walls)?
  2. Screens: monitors/laptops/phones showing text, mail, names or other private content?
  3. Documents: papers, whiteboards, posters with names, schedules, room numbers of people, IDs?
  4. Restroom: any photo taken inside or through a restroom door -> mark for removal.
  5. Anything else private: badges/name tags, license plates, open doors into offices.
Write down the contact-sheet number and tile of every problem; do not publish until each is fixed.
"""


def open_target(target):
    t = str(target)
    if sys.platform == "darwin":
        subprocess.run(["open", t], check=False)
    elif os.name == "nt":
        os.startfile(t)  # noqa: S606 (local review file)
    else:
        subprocess.run(["xdg-open", t], check=False)


def need(path):
    if not path.exists():
        print(f"missing: {path.relative_to(ROOT)}")
        return False
    return True


def main(argv):
    what = argv[1] if len(argv) > 1 else ""
    if what == "privacy":
        sheets = sorted((ROOT / "capture-local" / "grimes-L1-2026-10-18-review").glob("contact-sheet-*.jpg"))
        if not sheets:
            print("No contact sheets in capture-local/grimes-L1-2026-10-18-review")
            return 1
        for s in sheets:
            open_target(s)
        print(f"Opened {len(sheets)} contact sheets.")
        print(CHECKLIST)
    elif what == "gaussian":
        img = ROOT / "work" / "web-matrix" / "quality" / "before-after.png"
        if need(img):
            open_target(img)
        url = f"{BASE}/scan-compare.html?capture=2026-10-18&mode=splat"
        print("Live (needs the 8790 server):", url)
        webbrowser.open(url)
    elif what == "floors":
        url = f"{BASE}/scan-compare.html?capture=2026-10-18&floors=all&view=overlay"
        print("Local multifloor walk (localhost only, provisional):", url)
        print("Keys: W/A/S/D walk, PageUp/PageDown take the stairs.")
        webbrowser.open(url)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
