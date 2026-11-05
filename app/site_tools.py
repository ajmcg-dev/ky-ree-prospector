"""Tools the chat can call to look up the project's own results.

Each tool is an ordinary Python function plus a JSON schema telling Claude
what it does and what arguments it takes. Claude decides when to call them;
our code runs them and sends the results back.

Tools:
  find_sites      search scored water sites by distance, county, name, tier
  county_summary  tier counts, acidity, and top sites for one county
  find_mines      largest historical mines (Pike & Floyd), by county or distance
"""

import json
import math
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"
MAX_ROWS = 25

SITE_FIELDS = ["site_name", "county", "site_type", "tier", "p_elevated_ree", "pred_y_ug_l", "Y_ug_l",
               "ph", "sulfate_mg_l", "al_ug_l", "pct_mined", "pct_basin_covered", "first_year",
               "last_year", "drivers", "lat", "lon", "site_id"]
MINE_FIELDS = ["mine_name", "company", "county", "mine_type", "seam_name", "acres", "first_year",
               "last_year", "lat", "lon", "maps_url"]

_cache: dict[str, pd.DataFrame] = {}


def _sites() -> pd.DataFrame:
    if "sites" not in _cache:
        _cache["sites"] = pd.read_csv(DATA / "ky_sites.csv")
    return _cache["sites"]


def _mines() -> pd.DataFrame:
    if "mines" not in _cache:
        files = sorted(DATA.glob("mines_*.csv"))
        _cache["mines"] = pd.concat([pd.read_csv(f) for f in files]) if files else pd.DataFrame()
    return _cache["mines"]


def _km(df: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    """Approximate distance in km (fine at the scale of a county)."""
    dy = (df["lat"] - lat) * 111.0
    dx = (df["lon"] - lon) * 111.0 * math.cos(math.radians(lat))
    return (dx ** 2 + dy ** 2) ** 0.5


def _records(df: pd.DataFrame, fields: list[str]) -> list[dict]:
    out = df[[f for f in fields if f in df.columns]].round(3)
    return json.loads(out.to_json(orient="records"))


def _check_point(near_lat, near_lon, radius_km) -> None:
    if (near_lat is None) != (near_lon is None):
        raise ValueError("give both near_lat and near_lon, or neither")
    if near_lat is not None and not (36 <= near_lat <= 40 and -90 <= near_lon <= -81):
        raise ValueError("point is outside the Kentucky area")
    if radius_km is not None and not (0 < radius_km <= 100):
        raise ValueError("radius_km must be between 0 and 100")


def find_sites(near_lat=None, near_lon=None, radius_km=10, county=None, name_contains=None,
               tier=None, surface_water_only=True, limit=15) -> dict:
    _check_point(near_lat, near_lon, radius_km)
    df = _sites()
    if surface_water_only:
        df = df[df["surface_water"]]
    if county:
        df = df[df["county"].str.lower() == county.strip().lower()]
    if name_contains:
        df = df[df["site_name"].str.contains(name_contains, case=False, na=False, regex=False)]
    if tier:
        df = df[df["tier"].str.contains(tier, case=False, na=False)]
    if near_lat is not None:
        df = df.assign(km=_km(df, near_lat, near_lon).round(1))
        df = df[df["km"] <= (radius_km or 10)].sort_values("km")
    else:
        df = df.sort_values("rank")
    limit = max(1, min(int(limit or 15), MAX_ROWS))
    fields = (["km"] if "km" in df else []) + SITE_FIELDS
    return {"n_matches": int(len(df)), "showing": min(limit, len(df)), "sites": _records(df.head(limit), fields)}


def county_summary(county: str) -> dict:
    df = _sites()
    c = df[df["county"].str.lower() == county.strip().lower()]
    if c.empty:
        raise ValueError(f"no scored sites for county '{county}'. Known counties: "
                         + ", ".join(sorted(df["county"].dropna().unique())))
    surf = c[c["surface_water"]]
    return {
        "county": c["county"].iat[0],
        "coal_field": c["coal_field"].iat[0],
        "n_sites": int(len(c)),
        "n_surface_water_sites": int(len(surf)),
        "surface_sites_by_tier": surf["tier"].value_counts().to_dict(),
        "median_ph": None if surf["ph"].isna().all() else round(float(surf["ph"].median()), 2),
        "n_sites_ph_below_5_5": int((surf["ph"] < 5.5).sum()),
        "n_sites_with_measured_Y": int(surf["Y_ug_l"].notna().sum()),
        "median_pct_basin_mined": None if surf.get("pct_mined") is None or surf["pct_mined"].isna().all()
        else round(float(surf["pct_mined"].median()), 1),
        "top_sites": _records(surf.sort_values("rank").head(5), SITE_FIELDS),
    }


def find_mines(county=None, near_lat=None, near_lon=None, radius_km=10, limit=10) -> dict:
    _check_point(near_lat, near_lon, radius_km)
    df = _mines()
    if df.empty:
        return {"note": "No mine data is loaded in this app.", "mines": []}
    if county:
        df = df[df["county"].str.lower() == county.strip().lower()]
    if near_lat is not None:
        df = df.assign(km=_km(df, near_lat, near_lon).round(1))
        df = df[df["km"] <= (radius_km or 10)]
    df = df.sort_values("acres", ascending=False)
    limit = max(1, min(int(limit or 10), MAX_ROWS))
    fields = (["km"] if "km" in df else []) + MINE_FIELDS
    return {
        "coverage_note": "Mine maps are loaded for Pike and Floyd counties only. first_year/last_year are "
                         "state tax-record years (records start ~1989), not when mining began.",
        "n_matches": int(len(df)),
        "total_acres": round(float(df["acres"].sum()), 0),
        "mines": _records(df.head(limit), fields),
    }


_POINT = {
    "near_lat": {"type": "number", "description": "Latitude of the point to search around (decimal degrees)."},
    "near_lon": {"type": "number", "description": "Longitude of the point to search around (decimal degrees, negative in KY)."},
    "radius_km": {"type": "number", "description": "Search radius in km around the point (default 10, max 100)."},
}

TOOLS = [
    {
        "name": "find_sites",
        "description": (
            "Search the project's scored Kentucky coal-field water sites. Each site has a likelihood tier "
            "('1 very likely' ... '4 unlikely') for elevated dissolved REE (yttrium >= 1 ug/L), a predicted "
            "yttrium concentration, measured chemistry (pH, sulfate, aluminum), measured Y where it exists, "
            "% of its upstream watershed mined (Pike/Floyd only), and sampling years. Search by distance from "
            "a point, county name, site-name text, and/or tier. To search near a town, pass its approximate "
            "coordinates from your own knowledge. Results are sorted by distance (if a point is given) or by rank."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **_POINT,
                "county": {"type": "string", "description": "Kentucky county name, e.g. 'Pike'."},
                "name_contains": {"type": "string", "description": "Text to match in the site name, e.g. 'Elkhorn Creek'."},
                "tier": {"type": "string", "description": "Filter by tier text, e.g. 'very likely' or 'unlikely'."},
                "surface_water_only": {"type": "boolean", "description": "Only creeks, springs, discharges, lakes (default true)."},
                "limit": {"type": "integer", "description": "Max rows to return (default 15, max 25)."},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "county_summary",
        "description": "Summary of scored sites in one Kentucky coal-field county: counts by tier, median pH, "
                       "acidic site count, median % of watershed mined, and the 5 top-ranked sites.",
        "input_schema": {
            "type": "object",
            "properties": {"county": {"type": "string", "description": "Kentucky county name, e.g. 'Floyd'."}},
            "required": ["county"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_mines",
        "description": "Largest historical coal mines by mined-out area (acres), from the Kentucky Mine Mapping "
                       "Information System. Loaded for Pike and Floyd counties only. Filter by county and/or "
                       "distance from a point. Each mine has company, seam, type, and a link to its scanned map.",
        "input_schema": {
            "type": "object",
            "properties": {
                "county": {"type": "string", "description": "'Pike' or 'Floyd'."},
                **_POINT,
                "limit": {"type": "integer", "description": "Max rows to return (default 10, max 25)."},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
]

_FUNCTIONS = {"find_sites": find_sites, "county_summary": county_summary, "find_mines": find_mines}


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Run a tool call from Claude. Returns (result_json, is_error). Bad input
    becomes an error message Claude can read and correct, never a crash."""
    try:
        if name not in _FUNCTIONS:
            raise ValueError(f"unknown tool {name}")
        if not isinstance(args, dict):
            raise ValueError("tool input must be an object")
        return json.dumps(_FUNCTIONS[name](**args), ensure_ascii=False), False
    except (TypeError, ValueError, KeyError) as e:
        return f"Error: {e}", True
