"""Write small, web-friendly copies of the results for the dashboard.

Run with:  python -m ky_ree.export_app_data

The full pipeline outputs live in data/ (git-ignored, some are 10+ MB).
The dashboard reads only app/data/, which is committed so the app can run on
Streamlit Community Cloud without re-running the pipeline.
"""

import glob
import json
import shutil
import sys

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

from ky_ree import config

APP_DATA = config.ROOT / "app" / "data"

KY_COUNTY_NAMES = {
    13: "Bell", 19: "Boyd", 25: "Breathitt", 31: "Butler", 33: "Caldwell", 43: "Carter", 47: "Christian",
    51: "Clay", 55: "Crittenden", 59: "Daviess", 61: "Edmonson", 63: "Elliott", 65: "Estill", 71: "Floyd",
    85: "Grayson", 89: "Greenup", 91: "Hancock", 95: "Harlan", 101: "Henderson", 107: "Hopkins",
    109: "Jackson", 115: "Johnson", 119: "Knott", 121: "Knox", 125: "Laurel", 127: "Lawrence", 129: "Lee",
    131: "Leslie", 133: "Letcher", 147: "McCreary", 149: "McLean", 153: "Magoffin", 159: "Martin",
    165: "Menifee", 175: "Morgan", 177: "Muhlenberg", 183: "Ohio", 189: "Owsley", 193: "Perry", 195: "Pike",
    197: "Powell", 199: "Pulaski", 203: "Rockcastle", 205: "Rowan", 225: "Union", 231: "Wayne",
    233: "Webster", 235: "Whitley", 237: "Wolfe",
}

SITE_COLS = [
    "site_id", "site_name", "site_type", "coal_field", "county", "lat", "lon", "rank", "tier",
    "p_elevated_ree", "pred_y_ug_l", "p_bituminous_only", "drivers", "ph", "sulfate_mg_l", "al_ug_l",
    "fe_ug_l", "mn_ug_l", "sc_us_cm", "n_features", "n_out_of_range", "first_year", "last_year",
    "stale", "surface_water", "Y_ug_l", "Nd_ug_l", "org",
]


def polygons_only(geom):
    if geom is None or geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(parts) if parts else None


def main() -> int:
    APP_DATA.mkdir(parents=True, exist_ok=True)

    ky = pd.read_csv(config.PROCESSED_DIR / "ky_ranked.csv")
    ky["county"] = ky["county_fips"].map(KY_COUNTY_NAMES)
    ky = ky[ky["lat"].notna()]
    for f in sorted(glob.glob(str(config.PROCESSED_DIR / "upstream_mining_*.csv"))):
        up = pd.read_csv(f)[["site_id", "pct_mined", "pct_surface_mined", "pct_underground_mined",
                             "pct_basin_covered", "largest_upstream_mines"]]
        ky = ky.merge(up, on="site_id", how="left", suffixes=("", "_dup"))
    keep = SITE_COLS + [c for c in ky.columns if c.startswith("pct_") or c == "largest_upstream_mines"]
    ky[[c for c in dict.fromkeys(keep) if c in ky.columns]].to_csv(APP_DATA / "ky_sites.csv", index=False)
    print(f"  ky_sites.csv: {len(ky):,} sites")

    for f in sorted(glob.glob(str(config.PROCESSED_DIR / "mines_*.geojson"))):
        mines = gpd.read_file(f)
        # ~30 m outline precision and rounded coordinates: 14 MB -> a few MB.
        mines["geometry"] = mines.to_crs(5070).simplify(30).to_crs(4326)
        # Repairing invalid shapes can leave mixed "GeometryCollections" (polygons
        # plus stray lines/points) that web maps can't draw: keep only the polygons.
        mines["geometry"] = mines.geometry.make_valid().apply(polygons_only)
        empty = mines.geometry.isna() | mines.geometry.is_empty
        if empty.any():
            print(f"  dropped {empty.sum()} mines too small to draw after simplifying")
        mines = mines[~empty]
        mines = mines[["sfn", "mine_name", "company", "county", "mine_type", "seam_name", "acres",
                       "first_year", "last_year", "maps_url", "geometry"]]
        out = APP_DATA / f.replace("\\", "/").split("/")[-1]
        mines.to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)
        print(f"  {out.name}: {len(mines):,} mines, {out.stat().st_size / 1e6:.1f} MB")
        # A plain table (one point per mine) for the chat's find_mines tool.
        pts = mines.to_crs(5070).representative_point().to_crs(4326)
        table = mines.drop(columns="geometry").assign(lat=pts.y.round(5), lon=pts.x.round(5))
        table_out = out.with_suffix(".csv")
        table.to_csv(table_out, index=False)
        print(f"  {table_out.name}: mine table for the chat")

    shutil.copy(config.ROOT / "reports" / "metrics.json", APP_DATA / "metrics.json")

    # Report extractions for the "Ask the reports" chat: one compact JSON file
    # with each paper's citation info plus the values Claude extracted from it.
    manifest = pd.read_csv(config.DATA_DIR / "papers_manifest.csv").set_index("paper_id")
    papers = []
    for f in sorted((config.INTERIM_DIR / "extractions").glob("*.json")):
        meta = manifest.loc[f.stem] if f.stem in manifest.index else {}
        papers.append({
            "paper_id": f.stem,
            "url": meta.get("url") if len(meta) else None,
            "year": None if not len(meta) or pd.isna(meta.get("year")) else int(meta["year"]),
            **json.loads(f.read_text(encoding="utf-8")),
        })
    out = APP_DATA / "report_extractions.json"
    out.write_text(json.dumps(papers, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"  {out.name}: {len(papers)} papers, {out.stat().st_size / 1e3:.0f} KB")
    print(f"  Wrote {APP_DATA.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
