"""Historical coal mines from the Kentucky Mine Mapping Information System.

Run with:  python -m ky_ree.mines                 # Pike + Floyd (default)
           python -m ky_ree.mines Pike Floyd Knott

Source: KY Energy & Environment Cabinet ArcGIS services (https://minemaps.ky.gov)
  - Mined-out areas: polygons where coal was actually removed
  - Mine portals:    mine entrance points

The mined-out layer stores one polygon per mine per tax year, so the same
ground appears many times. We merge ("dissolve") all polygons of a mine,
identified by its state file number (SFN), into one footprint before
measuring area, so nothing is double-counted.

Outputs:
  data/raw/mines/mined_out_<county>.geojson    raw download
  data/processed/mines_<counties>.geojson      one footprint per mine
  reports/largest_mines_<counties>.csv         biggest mines by mined-out area
"""

import json
import sys

import geopandas as gpd
import pandas as pd
import requests

from ky_ree import config

SERVICE = "https://eppcgis.ky.gov/arcgis/rest/services/Mine_Mapping"
MINED_OUT_LAYERS = {
    "inactive": f"{SERVICE}/Ky_Mined_Out_Areas_WGS84WM/MapServer/1",
    "active": f"{SERVICE}/Ky_Mined_Out_Areas_WGS84WM/MapServer/0",
}
PORTALS_LAYER = f"{SERVICE}/Ky_Mine_Portals_WGS84WM/MapServer/0"
FIELDS = ["SFN", "MINE_NAME", "COMPANY", "OPERATOR", "SEAM_NAME", "MINE_TYPE1", "STREAM",
          "BRANCH", "FEDERAL_ID", "TAX_YEAR", "COUNTY", "MAPS_URL"]
RAW = config.RAW_DIR / "mines"
EQUAL_AREA = "EPSG:5070"  # USA Albers equal-area: correct for measuring acres
SQ_M_PER_ACRE = 4046.86
PAGE = 1000  # server max is 2000; smaller pages are gentler and less likely to time out


def fetch_layer(url: str, where: str) -> gpd.GeoDataFrame:
    """Download every feature matching `where`, page by page, as GeoJSON."""
    frames, offset = [], 0
    while True:
        params = {
            "where": where, "outFields": "*", "outSR": 4326, "f": "geojson",
            "resultOffset": offset, "resultRecordCount": PAGE, "orderByFields": "OBJECTID_1",
            "maxAllowableOffset": 0.00005,  # simplify outlines to ~5 m: plenty for our purpose
        }
        r = requests.get(f"{url}/query", params=params, timeout=300)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        feats = data.get("features", [])
        if not feats:
            break
        frames.append(gpd.GeoDataFrame.from_features(feats, crs=4326))
        offset += len(feats)
        print(f"    {offset:,} features", end="\r")
        if len(feats) < PAGE:
            break
    print()
    return pd.concat(frames, ignore_index=True) if frames else gpd.GeoDataFrame()


def clean_text(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    return s.where(~s.isin(["", "NULL", "None", "nan"]))


def download_county(county: str) -> gpd.GeoDataFrame:
    path = RAW / f"mined_out_{county.lower()}.geojson"
    if path.exists():
        print(f"  {county}: cached")
        return gpd.read_file(path)
    parts = []
    for status, url in MINED_OUT_LAYERS.items():
        print(f"  {county} {status}:")
        gdf = fetch_layer(url, f"UPPER(COUNTY)='{county.upper()}'")
        if len(gdf):
            parts.append(gdf.assign(layer_status=status))
    gdf = pd.concat(parts, ignore_index=True)
    gdf.to_file(path, driver="GeoJSON")
    return gdf


def dissolve_mines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per mine (SFN) with its merged footprint and summary attributes."""
    gdf = gdf.copy()
    for col in FIELDS:
        gdf[col] = clean_text(gdf[col]) if col in gdf else pd.NA
    gdf["geometry"] = gdf.geometry.make_valid()
    # Tax years are 2-digit ("89", "03"): before 30 -> 2000s, else 1900s.
    yy = pd.to_numeric(gdf["TAX_YEAR"], errors="coerce")
    gdf["year"] = yy.where(yy.isna(), yy.where(yy >= 30, yy + 100) + 1900)

    first = lambda s: s.dropna().mode().iat[0] if s.notna().any() else pd.NA  # most common value
    agg = {c: first for c in FIELDS if c not in ("SFN", "TAX_YEAR")}
    mines = gdf.dissolve(by="SFN", aggfunc=agg)
    years = gdf.groupby("SFN")["year"].agg(["min", "max"]).rename(columns={"min": "first_year", "max": "last_year"})
    mines = mines.join(years)
    mines["acres"] = (mines.to_crs(EQUAL_AREA).area / SQ_M_PER_ACRE).round(1)
    mines = mines.rename(columns=str.lower).rename(columns={"mine_type1": "mine_type"})
    mines.index.name = "sfn"
    return mines.sort_values("acres", ascending=False)


def main(counties: list[str]) -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    print("Downloading mined-out areas")
    raw = pd.concat([download_county(c) for c in counties], ignore_index=True)
    print(f"  {len(raw):,} polygons")

    mines = dissolve_mines(gpd.GeoDataFrame(raw, crs=4326))
    tag = "_".join(c.lower() for c in counties)
    out = config.PROCESSED_DIR / f"mines_{tag}.geojson"
    mines.reset_index().to_file(out, driver="GeoJSON")

    cols = ["mine_name", "company", "county", "mine_type", "seam_name", "stream", "federal_id",
            "first_year", "last_year", "acres", "maps_url"]
    table = mines.reset_index()[["sfn"] + cols]
    (config.ROOT / "reports").mkdir(exist_ok=True)
    table.head(50).to_csv(config.ROOT / "reports" / f"largest_mines_{tag}.csv", index=False)

    print(f"  {len(mines):,} distinct mines, {mines['acres'].sum():,.0f} acres mined out in total")
    print(mines.groupby(["county", "mine_type"])["acres"].agg(["count", "sum"]).round(0).to_string())
    print(f"  Wrote {out.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["Pike", "Floyd"]))
