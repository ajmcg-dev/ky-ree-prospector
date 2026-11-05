"""Use Claude to extract rare earth element measurements from a PDF report.

Run with:
    python -m ky_ree.extract vass2019_part2        # one paper
    python -m ky_ree.extract --all                 # every downloaded paper

Outputs:
    data/interim/extractions/<paper_id>.json   full structured result per paper
    data/interim/api_costs.csv                 tokens + dollars for every call
"""

import argparse
import base64
import csv
import datetime as dt
import sys

import anthropic
from dotenv import load_dotenv

from ky_ree import config
from ky_ree.schema import PaperExtraction

MODEL = "claude-opus-5-5"
PRICE_PER_M_INPUT = 4.00    # USD per million input tokens (Claude Opus 5.5)
PRICE_PER_M_OUTPUT = 20.00  # USD per million output tokens (includes thinking)

PAPERS_DIR = config.RAW_DIR / "papers"
OUT_DIR = config.INTERIM_DIR / "extractions"
COST_LOG = config.INTERIM_DIR / "api_costs.csv"

INSTRUCTIONS = """You are extracting data from a scientific report for a research dataset
on rare earth elements (REEs) in coal mine drainage.

Extract every site or sample for which the report prints rare earth element
values (La, Ce, Pr, Nd, Sm, Eu, Gd, Tb, Dy, Ho, Er, Tm, Yb, Lu, Y, Sc, or a
total such as TREE / TREY / REY).

Rules:
- Copy numbers exactly as printed. Never convert units, round, or calculate.
- If a value is a summary (mean, median, min, max of many samples), set `stat`
  accordingly instead of 'single'.
- Leave a field null when the report does not state it. Never guess
  coordinates, states, or chemistry.
- Include pH, sulfate, Al, Fe, Mn only when printed for that same site, in mg/L.
  If printed in other units, leave them null and mention it in `notes`.
- Below-detection values (e.g. '<0.01') are not numbers: skip them.
- Record the PDF page and the table/figure label you took values from.
- If data are only in supplementary files not included in this PDF, say so in `notes`.
"""


def log_cost(paper_id: str, usage) -> float:
    cost = (usage.input_tokens * PRICE_PER_M_INPUT + usage.output_tokens * PRICE_PER_M_OUTPUT) / 1_000_000
    new_file = not COST_LOG.exists()
    with open(COST_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "paper_id", "model", "input_tokens", "output_tokens", "usd"])
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), paper_id, MODEL,
                    usage.input_tokens, usage.output_tokens, f"{cost:.4f}"])
    return cost


def extract_paper(client: anthropic.Anthropic, paper_id: str) -> float:
    pdf_path = PAPERS_DIR / f"{paper_id}.pdf"
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode()

    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        output_config={"effort": "medium"},
        output_format=PaperExtraction,
        # If a safety check ever declines a request, retry on a fallback model
        # automatically instead of failing.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": INSTRUCTIONS},
            ],
        }],
    ) as stream:
        message = stream.get_final_message()

    cost = log_cost(paper_id, message.usage)
    if message.stop_reason in ("refusal", "max_tokens"):
        print(f"  ! {paper_id}: stopped early ({message.stop_reason}); nothing saved")
        return cost

    result: PaperExtraction = message.parsed_output
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{paper_id}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    n_values = sum(len(s.ree_values) for s in result.sites)
    print(f"  {paper_id}: {len(result.sites)} sites, {n_values} REE values "
          f"| {message.usage.input_tokens:,} in / {message.usage.output_tokens:,} out tokens | ${cost:.2f}")
    return cost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paper_ids", nargs="*", help="paper_id(s) from data/papers_manifest.csv")
    parser.add_argument("--all", action="store_true", help="extract every downloaded PDF")
    args = parser.parse_args()

    load_dotenv(config.ROOT / ".env")
    ids = sorted(p.stem for p in PAPERS_DIR.glob("*.pdf")) if args.all else args.paper_ids
    if not ids:
        parser.error("give one or more paper_ids, or --all")

    client = anthropic.Anthropic()
    total = 0.0
    for paper_id in ids:
        total += extract_paper(client, paper_id)
    print(f"\nTotal this run: ${total:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
