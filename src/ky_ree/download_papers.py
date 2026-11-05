"""Download the reports listed in data/papers_manifest.csv into data/raw/papers/.

Run with:  python -m ky_ree.download_papers

- Skips files you already have (safe to re-run).
- Only keeps real PDFs: some sites return an HTML page instead (login wall,
  bot check). Those are reported so you can download them by hand in a browser.
"""

import csv
import sys

import requests

from ky_ree import config

MANIFEST = config.DATA_DIR / "papers_manifest.csv"
PAPERS_DIR = config.RAW_DIR / "papers"
HEADERS = {"User-Agent": "ky-ree-prospector research script (portfolio project)"}


def load_manifest() -> list[dict]:
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def download(paper: dict) -> str:
    dest = PAPERS_DIR / f"{paper['paper_id']}.pdf"
    if dest.exists():
        return "already have it"
    try:
        r = requests.get(paper["url"], headers=HEADERS, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        return f"FAILED ({e.__class__.__name__}): download manually"
    # Every PDF file starts with the bytes "%PDF". Anything else is a web page.
    if not r.content.startswith(b"%PDF"):
        return "FAILED (got a web page, not a PDF): download manually"
    dest.write_bytes(r.content)
    return f"saved ({len(r.content) / 1_000_000:.1f} MB)"


def main() -> int:
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    papers = [p for p in load_manifest() if p["kind"] == "pdf"]
    failures = 0
    for paper in papers:
        status = download(paper)
        failures += status.startswith("FAILED")
        print(f"{paper['paper_id']:<22} {status}")
    print(f"\n{len(papers) - failures}/{len(papers)} PDFs in {PAPERS_DIR.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
