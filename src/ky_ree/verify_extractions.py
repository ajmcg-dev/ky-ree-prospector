"""Check Claude's extractions against the source PDFs.

For every extracted REE value, look for that number in the PDF's text layer.
A "found" value is strong evidence it was copied, not invented. "Not found"
does not prove an error (numbers in tables can be split oddly in a PDF's
text), so those are listed for a human to check by hand.

Run with:  python -m ky_ree.verify_extractions
"""

import json
import re
import sys

from pypdf import PdfReader

from ky_ree import config

EXTRACT_DIR = config.INTERIM_DIR / "extractions"
PAPERS_DIR = config.RAW_DIR / "papers"
REPORT = config.INTERIM_DIR / "verification_not_found.csv"


def number_variants(x: float) -> set[str]:
    """Ways a number might be printed: 3140 -> {'3140', '3,140', '3140.0', ...}."""
    plain = f"{x:f}".rstrip("0").rstrip(".")
    variants = {plain, f"{x:,f}".rstrip("0").rstrip(".")}
    if "." in plain:  # also allow printed trailing zeros, e.g. 0.50
        for d in range(len(plain.split(".")[1]) + 1, 4):
            variants.add(f"{x:.{d}f}")
    return variants


def pdf_text(paper_id: str) -> str:
    reader = PdfReader(PAPERS_DIR / f"{paper_id}.pdf")
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    return re.sub(r"\s+", " ", text)


def main() -> int:
    total_found = total = 0
    missing_rows = ["paper_id,site_name,element,value,units,page"]
    for path in sorted(EXTRACT_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        text = pdf_text(path.stem)
        found = n = 0
        for site in data["sites"]:
            for v in site["ree_values"]:
                n += 1
                # Require the number not be part of a longer number (e.g. 2.1 inside 12.15).
                hit = any(re.search(rf"(?<![\d.]){re.escape(s)}(?![\d])", text) for s in number_variants(v["value"]))
                found += hit
                if not hit:
                    name = site["site_name"].replace(",", ";")
                    missing_rows.append(f"{path.stem},{name},{v['element']},{v['value']},{v['units']},{site['page']}")
        total_found += found
        total += n
        print(f"{path.stem:<22} {found:>4}/{n:<4} values found in PDF text ({found / n:.0%})")
    print(f"{'ALL':<22} {total_found:>4}/{total:<4} ({total_found / total:.0%})")
    REPORT.write_text("\n".join(missing_rows), encoding="utf-8")
    print(f"\nValues to check by hand: {REPORT.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
