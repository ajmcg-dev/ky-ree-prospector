"""Turn raw Water Quality Portal downloads into a clean, one-row-per-site table.

Run with:  python -m ky_ree.build_dataset

Inputs:  data/raw/wqp/*.csv              (from python -m ky_ree.wqp)
Outputs: data/interim/ree_water_long.csv one row per REE measurement, standard units
         data/processed/sites.csv        one row per site: location, chemistry, REEs

Key decisions (documented so they can be questioned in an interview):
- Water samples only. Sediment REEs are in different units and a different
  physical process; they can be added later as a separate target.
- All REE and metal concentrations converted to ug/L; sulfate to mg/L.
- "Below detection" results are kept in the long table (flagged) but are not
  averaged as if they were real numbers. Site summaries use detected values,
  plus a count of non-detects so we never hide them.
- Site chemistry is the median over all sample dates. Pairing chemistry and
  REE from the same day is stricter and is a Phase 3 option.
"""

import glob
import sys

import pandas as pd

from ky_ree import config

RAW = config.RAW_DIR / "wqp"

SYMBOL = {
    "Lanthanum": "La", "Cerium": "Ce", "Praseodymium": "Pr", "Neodymium": "Nd",
    "Samarium": "Sm", "Europium": "Eu", "Gadolinium": "Gd", "Terbium": "Tb",
    "Dysprosium": "Dy", "Holmium": "Ho", "Erbium": "Er", "Thulium": "Tm",
    "Ytterbium": "Yb", "Lutetium": "Lu", "Yttrium": "Y", "Scandium": "Sc",
}

# Multiply by this factor to convert to ug/L (micrograms per liter).
TO_UG_L = {"ug/l": 1, "ug/L": 1, "ppb": 1, "mg/l": 1000, "mg/L": 1000, "ng/l": 0.001, "ng/L": 0.001}
TO_MG_L = {"mg/l": 1, "mg/L": 1, "ug/l": 0.001, "ug/L": 0.001, "ppm": 1}
SC_UNITS = {"uS/cm @25C", "umho/cm", "uS/cm", "umho/cm @25C"}

CHEM = {  # characteristic -> (output column, unit conversion table or None)
    "pH": ("ph", None),
    "Specific conductance": ("sc_us_cm", None),
    "Sulfate": ("sulfate_mg_l", TO_MG_L),
    "Aluminum": ("al_ug_l", TO_UG_L),
    "Iron": ("fe_ug_l", TO_UG_L),
    "Manganese": ("mn_ug_l", TO_UG_L),
}

SITE_COLS = {
    "MonitoringLocationIdentifier": "site_id",
    "MonitoringLocationName": "site_name",
    "MonitoringLocationTypeName": "site_type",
    "LatitudeMeasure": "lat",
    "LongitudeMeasure": "lon",
    "StateCode": "state_fips",
    "CountyCode": "county_fips",
    "HUCEightDigitCode": "huc8",
    "OrganizationIdentifier": "org",
}
STATE_FROM_FIPS = {"21": "KY", "42": "PA", "54": "WV", "51": "VA", "39": "OH", "47": "TN"}


def read_all(pattern: str) -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW / pattern)))
    return pd.concat((pd.read_csv(f, dtype=str, low_memory=False) for f in files), ignore_index=True)


def tidy_ree() -> pd.DataFrame:
    r = read_all("ree_results_*.csv")
    r = r[(r["ActivityMediaName"] == "Water") & r["CharacteristicName"].isin(SYMBOL)]
    units = r["ResultMeasure/MeasureUnitCode"].fillna(r["DetectionQuantitationLimitMeasure/MeasureUnitCode"])
    factor = units.map(TO_UG_L)
    value = pd.to_numeric(r["ResultMeasureValue"], errors="coerce")
    dl = pd.to_numeric(r["DetectionQuantitationLimitMeasure/MeasureValue"], errors="coerce")
    dl_factor = r["DetectionQuantitationLimitMeasure/MeasureUnitCode"].map(TO_UG_L)

    out = pd.DataFrame({
        "site_id": r["MonitoringLocationIdentifier"],
        "date": pd.to_datetime(r["ActivityStartDate"], errors="coerce"),
        "element": r["CharacteristicName"].map(SYMBOL),
        "fraction": r["ResultSampleFractionText"].fillna("Unknown"),
        "value_ug_l": value * factor,
        "detection_limit_ug_l": dl * dl_factor,
    })
    # Detected = a real number AND no "not detected" flag.
    out["detected"] = out["value_ug_l"].notna() & r["ResultDetectionConditionText"].isna().to_numpy()
    out.loc[~out["detected"], "value_ug_l"] = pd.NA
    dropped = factor.isna().sum()
    print(f"  REE water results: {len(out):,} ({out['detected'].sum():,} detected); "
          f"{dropped} had unrecognized units and are kept as non-numeric")
    return out


def site_ree_summary(ree: pd.DataFrame) -> pd.DataFrame:
    # Prefer dissolved results at a site; fall back to total if that's all there is.
    has_dissolved = ree[ree["fraction"] == "Dissolved"]["site_id"].unique()
    keep = (ree["fraction"] == "Dissolved") | ~ree["site_id"].isin(has_dissolved)
    ree = ree[keep]
    g = ree.groupby(["site_id", "element"])
    summary = pd.DataFrame({
        "median": g["value_ug_l"].median(),
        "n": g.size(),
        "n_detected": g["detected"].sum(),
    }).unstack("element")
    summary.columns = [f"{el}_{stat}" if stat != "median" else f"{el}_ug_l" for stat, el in summary.columns]
    summary["ree_fraction"] = ree.groupby("site_id")["fraction"].agg(lambda s: s.mode().iat[0])
    summary["n_ree_results"] = ree.groupby("site_id").size()
    summary["n_ree_detected"] = ree.groupby("site_id")["detected"].sum()
    return summary


def site_chemistry(pattern: str = "chem_results_*.csv") -> pd.DataFrame:
    c = read_all(pattern)
    c = c[(c["ActivityMediaName"] == "Water") & c["CharacteristicName"].isin(CHEM)]
    dates = pd.to_datetime(c["ActivityStartDate"], errors="coerce")
    value = pd.to_numeric(c["ResultMeasureValue"], errors="coerce")
    unit = c["ResultMeasure/MeasureUnitCode"]
    cols = {}
    for name, (col, table) in CHEM.items():
        mask = c["CharacteristicName"] == name
        if table is not None:
            v = value[mask] * unit[mask].map(table)
        elif name == "Specific conductance":
            v = value[mask].where(unit[mask].isin(SC_UNITS))
        else:  # pH: drop impossible values
            v = value[mask].where(value[mask].between(0, 14))
        df = pd.DataFrame({"site_id": c.loc[mask, "MonitoringLocationIdentifier"], "v": v}).dropna()
        cols[col] = df.groupby("site_id")["v"].median()
        cols[f"{col}_n"] = df.groupby("site_id").size()
    out = pd.DataFrame(cols)
    by_site = dates.groupby(c["MonitoringLocationIdentifier"])
    out["first_year"] = by_site.min().dt.year
    out["last_year"] = by_site.max().dt.year
    return out


def site_info(pattern: str = "ree_sites_*.csv") -> pd.DataFrame:
    s = read_all(pattern).drop_duplicates("MonitoringLocationIdentifier")
    s = s[list(SITE_COLS)].rename(columns=SITE_COLS).set_index("site_id")
    s["state"] = s["state_fips"].str.zfill(2).map(STATE_FROM_FIPS)
    s["lat"] = pd.to_numeric(s["lat"], errors="coerce")
    s["lon"] = pd.to_numeric(s["lon"], errors="coerce")
    return s


def main() -> int:
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ree = tidy_ree()
    ree.to_csv(config.INTERIM_DIR / "ree_water_long.csv", index=False)

    sites = (site_info()
             .join(site_ree_summary(ree), how="inner")
             .join(site_chemistry(), how="left"))
    sites.index.name = "site_id"
    out = config.PROCESSED_DIR / "sites.csv"
    sites.to_csv(out)

    print(f"  Sites with REE water data: {len(sites):,}")
    print(f"  ...with >=1 detected REE: {(sites['n_ree_detected'] > 0).sum():,}")
    print(f"  ...and pH + sulfate too:  {((sites['n_ree_detected'] > 0) & sites['ph'].notna() & sites['sulfate_mg_l'].notna()).sum():,}")
    print(f"  Wrote {out.relative_to(config.ROOT)}")

    if glob.glob(str(RAW / "ky_chem_*.csv")):
        build_ky_prediction_set()
    return 0


def build_ky_prediction_set() -> None:
    """Every sampled water site in the KY coal fields, with median chemistry.

    These are the creeks the model will score. Sites that also have REE
    measurements keep them, so we can check predictions against reality.
    """
    info = site_info("ky_sites_*.csv")
    field = {}
    for f in glob.glob(str(RAW / "ky_sites_*.csv")):
        name = f.replace("\\", "/").split("/")[-1]  # ky_sites_east_119.csv
        ids = pd.read_csv(f, dtype=str, usecols=["MonitoringLocationIdentifier"])["MonitoringLocationIdentifier"]
        field.update(dict.fromkeys(ids, name.split("_")[2]))
    info["coal_field"] = info.index.map(field)

    ky = info.join(site_chemistry("ky_chem_*.csv"), how="inner")
    known_ree = pd.read_csv(config.PROCESSED_DIR / "sites.csv", index_col="site_id")
    ree_cols = [c for c in known_ree.columns if c.endswith("_ug_l") and c.split("_")[0] in SYMBOL.values()]
    ky = ky.join(known_ree[ree_cols + ["n_ree_detected"]], how="left")
    ky.index.name = "site_id"

    out = config.PROCESSED_DIR / "ky_sites.csv"
    ky.to_csv(out)
    acidic = ky["ph"] < 5.5
    print(f"  KY coal-field sites with chemistry: {len(ky):,} "
          f"(east {(ky['coal_field'] == 'east').sum():,}, west {(ky['coal_field'] == 'west').sum():,})")
    print(f"  ...with pH: {ky['ph'].notna().sum():,}; acidic (median pH < 5.5): {acidic.sum():,}")
    print(f"  ...that already have a detected REE: {(ky['n_ree_detected'] > 0).sum():,}")
    print(f"  Wrote {out.relative_to(config.ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
