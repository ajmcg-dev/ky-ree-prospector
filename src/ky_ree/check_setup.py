"""Quick sanity check that your environment is ready.

Run with:  python -m ky_ree.check_setup
"""

import importlib
import os
import sys

from ky_ree import config

# (import name, what we use it for)
PACKAGES = [
    ("pandas", "tables of data"),
    ("numpy", "math on arrays"),
    ("requests", "downloading data from APIs"),
    ("dotenv", "loading the API key from .env"),
    ("geopandas", "maps and spatial joins"),
    ("sklearn", "machine learning"),
    ("shap", "explaining model predictions"),
    ("anthropic", "Claude API for reading reports"),
    ("folium", "interactive maps"),
    ("streamlit", "the dashboard"),
]


def main() -> int:
    print(f"Python {sys.version.split()[0]}")
    failed = []
    for name, purpose in PACKAGES:
        try:
            mod = importlib.import_module(name)
            version = getattr(mod, "__version__", "?")
            print(f"  OK   {name:<10} {version:<10} ({purpose})")
        except ImportError:
            print(f"  MISSING {name:<10} ({purpose})")
            failed.append(name)

    for folder in (config.RAW_DIR, config.PROCESSED_DIR, config.FIELD_DIR):
        status = "OK  " if folder.exists() else "MISSING"
        print(f"  {status} {folder.relative_to(config.ROOT)}/")

    from dotenv import load_dotenv

    load_dotenv(config.ROOT / ".env")
    key = os.getenv("ANTHROPIC_API_KEY", "")
    has_key = bool(key) and key != "your-key-here"
    print(f"  {'OK  ' if has_key else 'TODO'} ANTHROPIC_API_KEY in .env (needed from Phase 1)")

    if failed:
        print(f"\nMissing packages: {', '.join(failed)}. Run: pip install -r requirements.txt")
        return 1
    print("\nSetup looks good!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
