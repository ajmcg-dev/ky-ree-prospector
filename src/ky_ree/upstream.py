"""How much of each water site's upstream watershed has been mined?

Run with:  python -m ky_ree.upstream                 # Pike + Floyd (default)
           python -m ky_ree.upstream Pike Floyd Knott

For each Kentucky water site in the chosen counties:
  1. Get its upstream watershed (drainage basin) from the USGS Network-Linked
     Data Index (NLDI): https://api.water.usgs.gov/nldi
  2. Intersect it with mined-out areas (from python -m ky_ree.mines)
  3. Report % of the watershed mined (surface and underground) and the largest
     mines draining to it.

Coverage caveat: we only have mine maps for the chosen KY counties. Pike borders
WV and VA, so a basin that extends there would look less mined than it is.
`pct_basin_covered` says how much of each basin our mine data actually covers.

Requires: data/processed/mines_<counties>.geojson (python -m ky_ree.mines ...)
Output:   data/processed/upstream_mining_<counties>.csv
"""

import json
import re
import sys
import time

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape

from ky_ree import config
from ky_ree.mines import EQUAL_AREA, SQ_M_PER_ACRE

NLDI = "https://api.water.usgs.gov/nldi/linked-data"
COUNTIES = "https://eppcgis.ky.gov/arcgis/rest/services/Mine_Mapping/Ky_County_Lines_Names_WGS84WM/MapServer/0/query"
BASIN_CACHE = config.RAW_DIR / "basins"
FIPS = {"Pike": 195, "Floyd": 71, "Knott": 119, "Letcher": 133, "Perry": 193, "Harlan": 95,
        "Martin": 159, "Johnson": 115, "Magoffin": 153, "Breathitt": 25, "Bell": 13, "McCreary": 147}


def get_json(url: str, params: dict | None = None):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    return None


def fetch_basin(site_id: str, lat: float, lon: float):
    """Upstream basin polygon for a site, cached on disk. Tries the site's WQP ID
    first; if NLDI doesn't index that site, snaps the coordinates to the nearest
    stream reach instead."""
    path = BASIN_CACHE / (re.sub(r"[^A-Za-z0-9_-]", "_", site_id) + ".geojson")
    if path.exists():
        data = json.loads(path.read_text())
        return shape(data["features"][0]["geometry"]) if data.get("features") else None

    data = get_json(f"{NLDI}/wqp/{site_id}/basin", {"f": "json"})
    if not data or not data.get("features"):
        reach = get_json(f"{NLDI}/comid/position", {"f": "json", "coords": f"POINT({lon} {lat})"})
        if reach and reach.get("features"):
            comid = reach["features"][0]["properties"]["comid"]
            data = get_json(f"{NLDI}/comid/{comid}/basin", {"f": "json"})
    data = data or {"features": []}
    path.write_text(json.dumps(data))
    return shape(data["features"][0]["geometry"]) if data["features"] else None


def county_shapes(names: list[str]) -> gpd.GeoDataFrame:
    where = "UPPER(NAME) IN (" + ",".join(f"'{n.upper()}'" for n in names) + ")"
    data = get_json(COUNTIES, {"where": where, "outFields": "NAME", "outSR": 4326, "f": "geojson"})
    return gpd.GeoDataFrame.from_features(data["features"], crs=4326)


def main(counties: list[str]) -> int:
    BASIN_CACHE.mkdir(parents=True, exist_ok=True)
    tag = "_".join(c.lower() for c in counties)
    mines = gpd.read_file(config.PROCESSED_DIR / f"mines_{tag}.geojson").to_crs(EQUAL_AREA)
    covered = county_shapes(counties).to_crs(EQUAL_AREA).union_all()

    sites = pd.read_csv(config.PROCESSED_DIR / "ky_ranked.csv")
    sites = sites[sites["county_fips"].isin([FIPS[c] for c in counties]) & sites["surface_water"]
                  & sites["lat"].notna()].reset_index(drop=True)
    print(f"Fetching upstream basins for {len(sites)} surface-water sites")

    rows = []
    for i, s in sites.iterrows():
        basin = fetch_basin(s["site_id"], s["lat"], s["lon"])
        print(f"  {i + 1}/{len(sites)}", end="\r")
        if basin is None:
            continue
        b = gpd.GeoSeries([basin], crs=4326).to_crs(EQUAL_AREA).iloc[0]
        inside = mines[mines.intersects(b)]
        clipped = inside.geometry.intersection(b)
        area_by_type = clipped.area.groupby(inside["mine_type"].fillna("Unknown")).sum()
        mined_total = clipped.union_all().area if len(clipped) else 0.0  # no double count where surface over underground
        top = inside.assign(a=clipped.area).sort_values("a", ascending=False).head(3)
        rows.append({
            "site_id": s["site_id"],
            "basin_acres": round(b.area / SQ_M_PER_ACRE, 1),
            "pct_basin_covered": round(100 * b.intersection(covered).area / b.area, 1),
            "pct_mined": round(100 * mined_total / b.area, 2),
            "pct_surface_mined": round(100 * area_by_type.get("Surface", 0) / b.area, 2),
            "pct_underground_mined": round(100 * area_by_type.get("Underground", 0) / b.area, 2),
            "n_mines_upstream": len(inside),
            "largest_upstream_mines": "; ".join(f"{r.mine_name or '?'} ({r.company or '?'})" for r in top.itertuples()),
        })
    print()
    out = pd.DataFrame(rows)
    path = config.PROCESSED_DIR / f"upstream_mining_{tag}.csv"
    out.to_csv(path, index=False)
    print(f"  basins found for {len(out)}/{len(sites)} sites; "
          f"median {out['pct_mined'].median():.1f}% mined; "
          f"{(out['pct_basin_covered'] < 90).sum()} basins extend beyond our mine data")
    print(f"  Wrote {path.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["Pike", "Floyd"]))
