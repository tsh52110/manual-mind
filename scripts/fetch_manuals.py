"""Download the corpus PDFs from their official public sources.

The Daimler-brand manuals are publicly distributed by Daimler Truck but are NOT
public domain, so this repo does not redistribute them — run this once after
cloning, then build the indexes:

    python -m scripts.fetch_manuals
    python -m src.ingest
"""
from __future__ import annotations

import sys
import urllib.request

from src.config import PDF_DIR, load_manifest

UA = {"User-Agent": "Mozilla/5.0 (ManualMind corpus fetch; personal learning project)"}


def main() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    for m in load_manifest():
        dest = PDF_DIR / m["file"]
        if dest.exists() and dest.stat().st_size > 10_000:
            print(f"  {m['id']}: already present")
            continue
        if m["source_url"] == "user-upload":
            print(f"  {m['id']}: user upload, no public URL — skipping")
            continue
        print(f"  {m['id']}: downloading…")
        try:
            req = urllib.request.Request(m["source_url"], headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                head = r.read(5)
                if head != b"%PDF-":
                    raise ValueError("response is not a PDF")
                f.write(head + r.read())
        except Exception as e:  # noqa: BLE001 — report every failed manual at the end
            failures.append((m["id"], str(e)))
            dest.unlink(missing_ok=True)
    if failures:
        for mid, err in failures:
            print(f"FAILED {mid}: {err}", file=sys.stderr)
        sys.exit(1)
    print("All manuals present.")


if __name__ == "__main__":
    main()
