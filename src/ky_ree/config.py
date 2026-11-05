"""Project-wide settings: folder paths and constants used across the pipeline.

Keeping paths in one place means no script hard-codes "C:/Users/..." and the
project runs the same on anyone's computer.
"""

from pathlib import Path

# Project root = two folders up from this file (src/ky_ree/config.py -> repo root)
ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
FIELD_DIR = DATA_DIR / "field"
FIGURES_DIR = ROOT / "reports" / "figures"

# The 14 lanthanides + yttrium (Y) and scandium (Sc), the elements we care about.
REE_ELEMENTS = [
    "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd",
    "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Y", "Sc",
]

# Coordinate reference system: WGS84 lat/lon, what GPS and most web maps use.
CRS = "EPSG:4326"
