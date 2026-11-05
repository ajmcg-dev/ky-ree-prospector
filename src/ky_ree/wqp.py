"""Download data from the Water Quality Portal (WQP), the USGS/EPA national
database of water samples: https://www.waterqualitydata.us

Run with:  python -m ky_ree.wqp

Step 1: every rare earth element result in KY and nearby coal states.
Step 2: the water chemistry (pH, sulfate, Al, Fe, Mn, conductivity) measured
        at those same sites, which becomes our model's input features.

Downloads are cached in data/raw/wqp/; delete a file to re-download it.
"""

import io
import sys
import time

import pandas as pd
import requests

from ky_ree import config

BASE = "https://www.waterqualitydata.us/data"
OUT_DIR = config.RAW_DIR / "wqp"

# FIPS state codes: KY plus the Appalachian coal states we train on.
STATES = {"KY": "US:21", "PA": "US:42", "WV": "US:54", "VA": "US:51", "OH": "US:39", "TN": "US:47"}

REE_NAMES = [
    "Lanthanum", "Cerium", "Praseodymium", "Neodymium", "Samarium", "Europium",
    "Gadolinium", "Terbium", "Dysprosium", "Holmium", "Erbium", "Thulium",
    "Ytterbium", "Lutetium", "Yttrium", "Scandium",
]

CHEMISTRY_NAMES = [
    "pH", "Sulfate", "Aluminum", "Iron", "Manganese", "Specific conductance",
]


def wqp_post(endpoint: str, query: dict, retries: int = 3) -> pd.DataFrame:
    """POST a query to WQP and return the CSV result as a DataFrame."""
    url = f"{BASE}/{endpoint}/search?mimeType=csv&zip=no"
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, json=query, timeout=600)
            r.raise_for_status()
            return pd.read_csv(io.StringIO(r.text), dtype=str, low_memory=False)
        except (requests.RequestException, pd.errors.EmptyDataError) as e:
            if attempt == retries:
                raise
            print(f"    retry {attempt} after {e.__class__.__name__}")
            time.sleep(10 * attempt)
    raise RuntimeError("unreachable")


def cached(name: str, fetch) -> pd.DataFrame:
    path = OUT_DIR / f"{name}.csv"
    if path.exists():
        print(f"  {name}: cached")
        return pd.read_csv(path, dtype=str, low_memory=False)
    df = fetch()
    df.to_csv(path, index=False)
    print(f"  {name}: {len(df):,} rows")
    return df


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Step 1: rare earth results + site info")
    ree_frames, site_frames = [], []
    for state, code in STATES.items():
        q = {"statecode": [code], "characteristicName": REE_NAMES}
        ree_frames.append(cached(f"ree_results_{state}", lambda q=q: wqp_post("Result", q)))
        site_frames.append(cached(f"ree_sites_{state}", lambda q=q: wqp_post("Station", q)))
    ree = pd.concat(ree_frames, ignore_index=True)
    site_ids = sorted(ree["MonitoringLocationIdentifier"].dropna().unique())
    print(f"  -> {len(ree):,} REE results at {len(site_ids):,} sites")

    print("Step 2: water chemistry at those sites")
    for i, batch in enumerate(chunks(site_ids, 200)):
        q = {"siteid": batch, "characteristicName": CHEMISTRY_NAMES}
        cached(f"chem_results_{i:03d}", lambda q=q: wqp_post("Result", q))
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
