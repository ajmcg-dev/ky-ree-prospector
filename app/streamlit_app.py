"""KY REE Prospector dashboard.

Run locally:   streamlit run app/streamlit_app.py
Data:          app/data/ (refresh with: python -m ky_ree.export_app_data)
"""

import html
import json
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

APP_DIR = Path(__file__).parent
DATA = APP_DIR / "data"
FIGURES = APP_DIR.parent / "reports" / "figures"

TIER_COLORS = {
    "1 very likely": "#b2182b",
    "2 likely": "#ef8a62",
    "3 possible": "#e6c229",
    "4 unlikely": "#8c8c8c",
}
TIER_LABELS = {t: t.split(" ", 1)[1].capitalize() for t in TIER_COLORS}

st.set_page_config(page_title="KY REE Prospector", page_icon="⛏️", layout="wide")


@st.cache_data
def load_sites() -> pd.DataFrame:
    df = pd.read_csv(DATA / "ky_sites.csv")
    df["tier"] = df["tier"].astype(str)
    return df


@st.cache_data
def load_mines() -> dict | None:
    files = sorted(DATA.glob("mines_*.geojson"))
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


@st.cache_data
def load_metrics() -> dict:
    return json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))


def fmt(v, unit="", digits=1) -> str:
    if pd.isna(v):
        return "n/a"
    return f"{v:,.{digits}f}{unit}"


def year(v) -> str:
    return "n/a" if pd.isna(v) else str(int(v))


def popup_html(r: pd.Series) -> str:
    name = html.escape(str(r["site_name"]))
    rows = [
        ("Tier", TIER_LABELS.get(r["tier"], r["tier"])),
        ("P(elevated REE)", fmt(r["p_elevated_ree"], "", 2)),
        ("Predicted Y", fmt(r["pred_y_ug_l"], " µg/L", 1)),
        ("Why", html.escape(str(r["drivers"]))),
        ("pH", fmt(r["ph"], "", 1)),
        ("Sulfate", fmt(r["sulfate_mg_l"], " mg/L", 0)),
        ("Aluminum", fmt(r["al_ug_l"], " µg/L", 0)),
        ("Measured Y", fmt(r.get("Y_ug_l"), " µg/L", 1)),
        ("Watershed mined", fmt(r.get("pct_mined"), "%", 0)),
        ("Sampled", f"{year(r['first_year'])}–{year(r['last_year'])}"),
        ("County", f"{r['county']} ({r['coal_field']} coal field)"),
        ("Site type", html.escape(str(r["site_type"]))),
    ]
    body = "".join(f"<tr><td style='padding-right:8px;color:#555'>{k}</td><td>{v}</td></tr>" for k, v in rows)
    warn = ""
    if r["n_out_of_range"] >= 2:
        warn = "<p style='color:#b35806'>⚠ Chemistry outside training range: less certain</p>"
    if r["stale"]:
        warn += f"<p style='color:#b35806'>⚠ Last sampled {year(r['last_year'])}: conditions may have changed</p>"
    return f"<b>{name}</b><table style='font-size:12px'>{body}</table>{warn}<small>{html.escape(r['site_id'])}</small>"


def build_map(df: pd.DataFrame, show_mines: bool) -> folium.Map:
    center = [df["lat"].mean(), df["lon"].mean()] if len(df) else [37.5, -84.5]
    m = folium.Map(location=center, zoom_start=8, tiles="OpenStreetMap", control_scale=True)
    if show_mines and (mines := load_mines()):
        folium.GeoJson(
            mines, name="Mined-out areas (Pike & Floyd)",
            style_function=lambda f: {
                "fillColor": "#6a51a3" if f["properties"].get("mine_type") == "Underground" else "#41ab5d",
                "color": "#54278f", "weight": 0.3, "fillOpacity": 0.35,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["mine_name", "company", "mine_type", "seam_name", "acres"],
                aliases=["Mine", "Company", "Type", "Seam", "Acres"],
            ),
        ).add_to(m)
    # Draw unlikely sites first so likely ones sit on top.
    for _, r in df.sort_values("p_elevated_ree").iterrows():
        radius = 3 + 2.5 * np.clip(np.log10(max(r["pred_y_ug_l"], 0.01)) + 2, 0, 4.5)
        folium.CircleMarker(
            location=[r["lat"], r["lon"]], radius=radius,
            color="#333" if not r["stale"] else "#999", weight=0.8,
            fill=True, fill_color=TIER_COLORS.get(r["tier"], "#8c8c8c"), fill_opacity=0.85,
            popup=folium.Popup(popup_html(r), max_width=340),
            tooltip=f"{r['site_name']} · {TIER_LABELS.get(r['tier'], '')}",
        ).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def view_for(df: pd.DataFrame) -> tuple[list[float], int]:
    """Center and zoom that fit the shown sites (st_folium ignores fit_bounds)."""
    if not len(df):
        return [37.5, -84.5], 7
    span = max(df["lon"].max() - df["lon"].min(), 1.4 * (df["lat"].max() - df["lat"].min()), 0.05)
    zoom = int(np.clip(round(np.log2(360 / span)), 5, 13))
    return [(df["lat"].min() + df["lat"].max()) / 2, (df["lon"].min() + df["lon"].max()) / 2], zoom


sites = load_sites()
metrics = load_metrics()

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")
fields = st.sidebar.multiselect("Coal field", ["east", "west"], default=["east", "west"])
counties = st.sidebar.multiselect("Counties (blank = all)", sorted(sites["county"].dropna().unique()))
tiers = st.sidebar.multiselect(
    "Likelihood tier", list(TIER_COLORS), default=["1 very likely", "2 likely", "3 possible"],
    format_func=TIER_LABELS.get,
)
surface_only = st.sidebar.checkbox("Surface water only (creeks, springs, discharges)", value=True)
min_year = st.sidebar.slider("Last sampled in or after", 1950, 2025, 1950, step=5)
hide_uncertain = st.sidebar.checkbox("Hide sites with chemistry far outside training data", value=False)
show_mines = st.sidebar.checkbox("Show mined-out areas (Pike & Floyd)", value=False)
st.sidebar.caption("Mine layer is ~4 MB and may take a few seconds to draw.")

f = sites[sites["coal_field"].isin(fields) & sites["tier"].isin(tiers) & (sites["last_year"] >= min_year)]
if counties:
    f = f[f["county"].isin(counties)]
if surface_only:
    f = f[f["surface_water"]]
if hide_uncertain:
    f = f[f["n_out_of_range"] <= 1]

# ---------- Header ----------
st.title("KY REE Prospector")
st.markdown(
    "Which polluted Kentucky creeks are most likely to carry **elevated rare earth elements**? "
    "A model trained on 386 Appalachian sites with measured yttrium (a stand-in for magnet REEs) "
    "scores every sampled water site in Kentucky's coal fields from its water chemistry."
)
cv = metrics["spatial_cv"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Sites shown", f"{len(f):,}")
c2.metric("Very likely", f"{(f['tier'] == '1 very likely').sum():,}")
c3.metric("Model AUC (held-out watersheds)", f"{cv['model_auc']:.2f}", f"{cv['model_auc'] - cv['baseline_auc']:+.2f} vs pH-only")
c4.metric("Magnitude R² (held-out)", f"{metrics['magnitude_spatial_cv']['r2_log10']:.2f}")

tab_map, tab_list, tab_model, tab_about = st.tabs(["Map", "Field shortlist", "Model", "About"])

with tab_map:
    legend = " ".join(
        f"<span style='display:inline-block;width:11px;height:11px;border-radius:50%;background:{c};"
        f"margin:0 4px 0 12px;vertical-align:middle'></span>{TIER_LABELS[t]}"
        for t, c in TIER_COLORS.items()
    )
    st.markdown(f"<div style='font-size:14px'>{legend} &nbsp;·&nbsp; bigger circle = more predicted yttrium"
                f" &nbsp;·&nbsp; gray outline = last sampled before 1990</div>", unsafe_allow_html=True)
    if len(f) > 1500:
        st.info(f"Showing the top 1,500 of {len(f):,} sites. Narrow the filters to see the rest.")
    shown = f.nsmallest(1500, "rank")
    center, zoom = view_for(shown)
    # A key tied to the filters makes the map re-fit whenever they change.
    map_key = "map-" + str(abs(hash((tuple(fields), tuple(counties), tuple(tiers), surface_only,
                                     min_year, hide_uncertain, show_mines))))
    st_folium(build_map(shown, show_mines), height=620, center=center, zoom=zoom, key=map_key,
              use_container_width=True, returned_objects=[])

with tab_list:
    st.subheader("Candidate sites for field sampling")
    st.caption("Filtered sites ranked by likelihood tier, then predicted yttrium. Duplicate site IDs at "
               "the same spot (within ~100 m) are merged. Check access and permits before visiting: "
               "Blue Heron (McCreary) is inside Big South Fork NRRA (National Park Service).")
    short = f.copy()
    short["spot"] = short["lat"].round(3).astype(str) + "," + short["lon"].round(3).astype(str)
    short = short.sort_values("rank").drop_duplicates("spot")
    show = short[["rank", "site_name", "county", "tier", "p_elevated_ree", "pred_y_ug_l", "drivers", "ph",
                  "sulfate_mg_l", "al_ug_l", "Y_ug_l", "pct_mined", "last_year", "lat", "lon", "site_id"]]
    st.dataframe(
        show, hide_index=True, width="stretch", height=520,
        column_config={
            "tier": st.column_config.TextColumn("Tier"),
            "p_elevated_ree": st.column_config.ProgressColumn("P(elevated)", min_value=0, max_value=1, format="%.2f"),
            "pred_y_ug_l": st.column_config.NumberColumn("Pred. Y (µg/L)", format="%.1f"),
            "Y_ug_l": st.column_config.NumberColumn("Measured Y", format="%.1f"),
            "pct_mined": st.column_config.NumberColumn("% basin mined", format="%.0f"),
            "last_year": st.column_config.NumberColumn("Last sampled", format="%d"),
        },
    )
    st.download_button("Download as CSV", show.to_csv(index=False), "ky_ree_candidates.csv", "text/csv")

with tab_model:
    st.subheader("How well does it work?")
    t = metrics["ky_transfer_test"]
    a = metrics["anthracite_sensitivity"]
    st.markdown(f"""
- **Target:** probability that a site's median yttrium is ≥ 1 µg/L (~10× clean-water background).
  Yttrium tracks neodymium, a magnet REE, almost perfectly (Spearman 0.96).
- **Spatial cross-validation:** whole watersheds held out together. Classifier AUC **{cv['model_auc']}** vs
  **{cv['baseline_auc']}** for a low-pH-only baseline ({cv['n_sites']} sites, {cv['n_watersheds']} watersheds).
- **How much Y:** R² **{metrics['magnitude_spatial_cv']['r2_log10']}** on log10 scale, typical error about a factor of 2.
- **Kentucky transfer test:** trained without any Kentucky data, then checked on {t['n_sites']} KY sites
  with measured yttrium. Knott/Floyd predictions landed within ~2× of measured values. With only one
  "not elevated" KY site, this is encouraging but **not conclusive**. Field samples will be the real test.
- **Robustness:** dropping Pennsylvania anthracite sites kept {a['ky_high_sites_still_high_without_anthracite']}
  high-probability Kentucky sites high.
""")
    cols = st.columns(3)
    for col, (name, cap) in zip(cols, [
        ("roc_spatial_cv.png", "Classifier vs. baseline on held-out watersheds"),
        ("pred_vs_obs_y.png", "Predicted vs. measured yttrium"),
        ("shap_summary.png", "What drives predictions: aluminum and pH lead"),
    ]):
        if (FIGURES / name).exists():
            col.image(str(FIGURES / name), caption=cap, width="stretch")

with tab_about:
    st.markdown("""
### What this is
A portfolio project combining **LLM-based literature mining**, a **public-data pipeline**, a
**spatially validated ML model**, and (in progress) **field validation** to find Kentucky creeks
where acid mine drainage may carry rare earth elements.

### Data sources
- **Water Quality Portal** (USGS/EPA): water chemistry and REE results
- **Kentucky Mine Mapping Information System** (KY Energy & Environment Cabinet): mined-out areas
- **USGS NLDI**: upstream watershed boundaries
- **Published studies**: Cravotta (2008), Vass et al. (2019), Stewart et al. (2017), Honaker group (UK),
  read with the Claude API (909/909 extracted values traced to the source PDFs)

### Important limitations
- Scores are **relative likelihood of elevated dissolved REEs**, not evidence of a mineable deposit.
- Many high-scoring sites were last sampled decades ago; mine reclamation may have changed them.
- Training data is mostly Pennsylvania; Kentucky transfer is promising but based on few sites.
- Heavily mined Pike/Floyd creeks are neutral pH: REEs there may sit in **stream-bed sediment**
  rather than water, which this water-based model can't see.
- Do not enter private land without permission, and never enter mine openings.
""")
