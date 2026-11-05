"""Phase 3: predict which Kentucky creeks are most likely to carry elevated REEs.

Run with:  python -m ky_ree.model

Target
    Yttrium (Y) is our stand-in for rare earths: across 360 sites it tracks
    neodymium (a magnet REE) almost perfectly (Spearman 0.96), and it is the
    most-measured REE. A site is "elevated" if its median Y >= 1 ug/L
    (~10x clean-water background).

Non-detects ("censored" data)
    A "not detected" result only tells us Y < detection limit. Labs used limits
    up to 10 ug/L, so a non-detect counts as "not elevated" ONLY if its limit
    was <= 1 ug/L. Otherwise the site's label is unknown and it is left out.
    This avoids the common shortcut of substituting DL/2, which here would
    invent fake high values.

Validation
    Spatial cross-validation: whole watersheds (HUC8) are held out together,
    so the model is always tested on places it never trained on. Random splits
    would let nearby, near-identical sites leak between train and test.

Outputs
    reports/metrics.json, reports/figures/*.png, data/processed/ky_ranked.csv,
    reports/ky_top_creeks.csv
"""

import json
import sys

import matplotlib

matplotlib.use("Agg")  # draw to files, no window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score, roc_curve
from sklearn.model_selection import GroupKFold

from ky_ree import config

THRESHOLD_UG_L = 1.0
FEATURES = ["ph", "log_sulfate", "log_al", "log_fe", "log_mn", "log_sc"]
FEATURE_LABELS = {
    "ph": "pH", "log_sulfate": "log10 sulfate", "log_al": "log10 aluminum",
    "log_fe": "log10 iron", "log_mn": "log10 manganese", "log_sc": "log10 conductivity",
}
SURFACE_WATER = ["Stream", "River/Stream", "River/Stream Perennial", "Mine/Mine Discharge",
                 "Spring", "Lake, Reservoir, Impoundment", "Pond", "River/Stream Intermittent"]
SEED = 42
REPORTS = config.ROOT / "reports"
# PA counties in the anthracite fields. Eastern KY is bituminous coal, so we
# check whether these sites change the model.
ANTHRACITE_PA_COUNTIES = [107, 79, 69, 97, 25, 37, 43]
STALE_BEFORE = 1990  # sites last sampled earlier are flagged as stale


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Same feature engineering for training and Kentucky. Logs tame the huge
    range of concentrations (sulfate spans 1 to 3,000+ mg/L)."""
    out = df.copy()
    for col, src in [("log_sulfate", "sulfate_mg_l"), ("log_al", "al_ug_l"), ("log_fe", "fe_ug_l"),
                     ("log_mn", "mn_ug_l"), ("log_sc", "sc_us_cm")]:
        out[col] = np.log10(out[src].clip(lower=0.01))
    return out


def site_labels() -> pd.Series:
    """1 = elevated Y, 0 = confidently not elevated, missing = unknown."""
    long = pd.read_csv(config.INTERIM_DIR / "ree_water_long.csv")
    y = long[long["element"] == "Y"]
    det = y[y["detected"]].groupby("site_id")["value_ug_l"].median()
    # Non-detects informative only if the lab could see down to the threshold.
    nd_ok = y[~y["detected"] & (y["detection_limit_ug_l"] <= THRESHOLD_UG_L)]["site_id"].unique()
    label = (det >= THRESHOLD_UG_L).astype(int)
    only_nd = pd.Index(nd_ok).difference(det.index)
    label = pd.concat([label, pd.Series(0, index=only_nd)])
    label.name = "elevated_y"
    return label


def baseline_score(df: pd.DataFrame) -> pd.Series:
    """Knowledge-only score from the literature: lower pH = more REEs.
    When pH is missing, fall back to sulfate (also an AMD indicator)."""
    score = -df["ph"]
    fallback = df["log_sulfate"] - 10  # always ranks below any site with pH
    return score.fillna(fallback)


def make_model() -> HistGradientBoostingClassifier:
    # Small, regularized trees: we only have a few hundred labeled sites.
    return HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=15,
        l2_regularization=1.0, random_state=SEED,
    )


def spatial_cv(train: pd.DataFrame) -> dict:
    X, y, groups = train[FEATURES], train["elevated_y"], train["huc8"]
    oof = pd.Series(np.nan, index=train.index)
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        m = make_model().fit(X.iloc[tr], y.iloc[tr])
        oof.iloc[te] = m.predict_proba(X.iloc[te])[:, 1]
    base = baseline_score(train)
    return {
        "n_sites": int(len(train)),
        "n_elevated": int(y.sum()),
        "n_watersheds": int(groups.nunique()),
        "model_auc": round(roc_auc_score(y, oof), 3),
        "baseline_auc": round(roc_auc_score(y, base), 3),
        "_oof": oof, "_base": base,
    }


def site_log_y() -> pd.Series:
    """Median log10 of detected Y per site: the 'how much' target."""
    long = pd.read_csv(config.INTERIM_DIR / "ree_water_long.csv")
    y = long[(long["element"] == "Y") & long["detected"] & (long["value_ug_l"] > 0)]
    return np.log10(y.groupby("site_id")["value_ug_l"].median()).rename("log_y")


def make_regressor() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=15,
        l2_regularization=1.0, random_state=SEED,
    )


def regression_cv(train: pd.DataFrame) -> dict:
    """How well can we predict HOW MUCH yttrium, on held-out watersheds?"""
    X, y, groups = train[FEATURES], train["log_y"], train["huc8"]
    oof = pd.Series(np.nan, index=train.index)
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        oof.iloc[te] = make_regressor().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    with_ph = train["ph"].notna()
    return {
        "n_sites": int(len(train)),
        "r2_log10": round(r2_score(y, oof), 3),
        "mae_log10": round(mean_absolute_error(y, oof), 3),  # 0.3 ~ within a factor of 2
        "spearman_model": round(oof.rank().corr(y.rank()), 3),
        "spearman_baseline_low_ph": round((-train.loc[with_ph, "ph"]).rank().corr(y[with_ph].rank()), 3),
        "_oof": oof,
    }


def out_of_range(train: pd.DataFrame, df: pd.DataFrame) -> pd.Series:
    """How many of a site's features fall outside the training data's 1st-99th
    percentile. Predictions there are extrapolations and less trustworthy."""
    lo, hi = train[FEATURES].quantile(0.01), train[FEATURES].quantile(0.99)
    outside = (df[FEATURES] < lo) | (df[FEATURES] > hi)
    return outside.sum(axis=1)


def explain_sites(explainer, X: pd.DataFrame, train_X: pd.DataFrame, top: int = 2) -> pd.Series:
    """Plain-language reason for each site's score, from its SHAP values:
    e.g. 'high aluminum (+), low pH (+)'. (+) pushes toward elevated REE."""
    values = explainer(X).values
    medians = train_X.median()
    names = {"ph": "pH", "log_sulfate": "sulfate", "log_al": "aluminum", "log_fe": "iron",
             "log_mn": "manganese", "log_sc": "conductivity"}
    out = []
    for row_vals, (_, row) in zip(values, X.iterrows()):
        order = np.argsort(-np.abs(row_vals))[:top]
        parts = []
        for j in order:
            f = X.columns[j]
            if pd.isna(row[f]) or abs(row_vals[j]) < 0.1:
                continue
            level = "high" if row[f] > medians[f] else "low"
            parts.append(f"{level} {names[f]} ({'+' if row_vals[j] > 0 else '-'})")
        out.append(", ".join(parts) or "no strong signal")
    return pd.Series(out, index=X.index)


def plot_pred_vs_obs(y, pred, path) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(10 ** y, 10 ** pred, s=10, alpha=0.6)
    lims = [10 ** min(y.min(), pred.min()), 10 ** max(y.max(), pred.max())]
    ax.plot(lims, lims, "k:", lw=1, label="perfect prediction")
    ax.set(xscale="log", yscale="log", xlabel="Measured Y (ug/L)", ylabel="Predicted Y (ug/L)",
           title="Yttrium on held-out watersheds")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_roc(y, curves: dict, path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    for name, score in curves.items():
        fpr, tpr, _ = roc_curve(y, score)
        ax.plot(fpr, tpr, label=f"{name} (AUC {roc_auc_score(y, score):.2f})")
    ax.plot([0, 1], [0, 1], "k:", lw=1, label="random guess")
    ax.set(xlabel="False positive rate", ylabel="True positive rate", title=title)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> int:
    (REPORTS / "figures").mkdir(parents=True, exist_ok=True)

    sites = add_features(pd.read_csv(config.PROCESSED_DIR / "sites.csv", dtype={"huc8": str}, index_col="site_id"))
    sites = sites.join(site_labels(), how="left")
    labeled = sites[sites["elevated_y"].notna() & sites[FEATURES].notna().any(axis=1)].copy()
    labeled["elevated_y"] = labeled["elevated_y"].astype(int)
    train = labeled[labeled["state"] != "KY"]
    ky_test = labeled[labeled["state"] == "KY"]
    print(f"Labeled sites: {len(labeled)} ({labeled['elevated_y'].sum()} elevated). "
          f"Training (non-KY): {len(train)}; KY held out: {len(ky_test)}")

    # 1. Spatial cross-validation on the training states.
    cv = spatial_cv(train)
    print(f"Spatial CV over {cv['n_watersheds']} watersheds: "
          f"model AUC {cv['model_auc']} vs baseline (pH only) AUC {cv['baseline_auc']}")
    plot_roc(train["elevated_y"], {"Model": cv["_oof"], "Baseline: low pH": cv["_base"]},
             REPORTS / "figures" / "roc_spatial_cv.png", "Spatial CV (held-out watersheds)")

    # 2. Final model on all training states, then the Kentucky transfer test.
    model = make_model().fit(train[FEATURES], train["elevated_y"])
    transfer = {"n_sites": int(len(ky_test)), "n_elevated": int(ky_test["elevated_y"].sum())}
    if ky_test["elevated_y"].nunique() == 2:
        p = model.predict_proba(ky_test[FEATURES])[:, 1]
        transfer["model_auc"] = round(roc_auc_score(ky_test["elevated_y"], p), 3)
        transfer["baseline_auc"] = round(roc_auc_score(ky_test["elevated_y"], baseline_score(ky_test)), 3)
    else:
        transfer["note"] = "KY test set has only one class; AUC undefined"
    print(f"KY transfer test: {transfer}")

    # 3. SHAP: which features drive predictions, and in which direction.
    explainer = shap.TreeExplainer(model)
    sv = explainer(train[FEATURES])
    sv.feature_names = [FEATURE_LABELS[f] for f in FEATURES]
    shap.plots.beeswarm(sv, show=False)
    plt.title("What drives the prediction (SHAP)")
    plt.tight_layout()
    plt.savefig(REPORTS / "figures" / "shap_summary.png", dpi=150)
    plt.close("all")
    importance = dict(zip(FEATURES, np.abs(sv.values).mean(axis=0).round(3).tolist()))

    # 4. Magnitude model: how much Y, trained on sites where Y was detected.
    reg_data = sites.join(site_log_y(), how="inner")
    reg_data = reg_data[reg_data[FEATURES].notna().any(axis=1)]
    reg_train = reg_data[reg_data["state"] != "KY"]
    rcv = regression_cv(reg_train)
    print(f"Magnitude model, spatial CV: R2 {rcv['r2_log10']}, MAE {rcv['mae_log10']} log10 units, "
          f"Spearman {rcv['spearman_model']} vs low-pH baseline {rcv['spearman_baseline_low_ph']}")
    plot_pred_vs_obs(reg_train["log_y"], rcv["_oof"], REPORTS / "figures" / "pred_vs_obs_y.png")
    regressor = make_regressor().fit(reg_train[FEATURES], reg_train["log_y"])

    # 5. Sensitivity: does dropping PA anthracite sites change the Kentucky ranking?
    bituminous = ~((train["state"] == "PA") & train["county_fips"].isin(ANTHRACITE_PA_COUNTIES))
    cv_bit = spatial_cv(train[bituminous])
    model_bit = make_model().fit(train.loc[bituminous, FEATURES], train.loc[bituminous, "elevated_y"])

    # 6. Score every Kentucky coal-field site.
    ky = add_features(pd.read_csv(config.PROCESSED_DIR / "ky_sites.csv", index_col="site_id"))
    ky = ky[ky[FEATURES].notna().any(axis=1)].copy()
    ky["p_elevated_ree"] = model.predict_proba(ky[FEATURES])[:, 1].round(3)
    ky["pred_y_ug_l"] = (10 ** regressor.predict(ky[FEATURES])).round(2)
    ky["p_bituminous_only"] = model_bit.predict_proba(ky[FEATURES])[:, 1].round(3)
    ky["n_features"] = ky[FEATURES].notna().sum(axis=1)
    ky["n_out_of_range"] = out_of_range(train, ky)
    ky["drivers"] = explain_sites(explainer, ky[FEATURES], train[FEATURES])
    ky["surface_water"] = ky["site_type"].isin(SURFACE_WATER)
    ky["stale"] = ky["last_year"] < STALE_BEFORE
    sensitivity = {
        "n_training_sites_without_anthracite": int(bituminous.sum()),
        "spatial_cv_auc_without_anthracite": cv_bit["model_auc"],
        "ky_rank_correlation_with_vs_without": round(float(ky["p_elevated_ree"].rank().corr(ky["p_bituminous_only"].rank())), 3),
    }
    hi = ky["surface_water"] & (ky["p_elevated_ree"] >= 0.8)
    sensitivity["ky_high_sites_still_high_without_anthracite"] = f"{int((ky.loc[hi, 'p_bituminous_only'] >= 0.8).sum())}/{int(hi.sum())}"
    print(f"Anthracite sensitivity: {sensitivity}")

    # Ranking: group into likelihood tiers (0.998 vs 0.999 is not a real
    # difference), then rank by predicted amount within each tier.
    ky["tier"] = pd.cut(ky["p_elevated_ree"], [-0.01, 0.5, 0.8, 0.95, 1.0],
                        labels=["4 unlikely", "3 possible", "2 likely", "1 very likely"])
    ky = ky.sort_values(["tier", "pred_y_ug_l"], ascending=False)
    ky["rank"] = np.arange(1, len(ky) + 1)
    ky.to_csv(config.PROCESSED_DIR / "ky_ranked.csv")

    # 7. Field shortlist: surface water, likely elevated, trustworthy inputs.
    # Several site IDs can be the same spot (different agencies), so merge
    # sites within ~100 m (3 decimal places of lat/lon).
    cand = ky[ky["surface_water"] & (ky["p_elevated_ree"] >= 0.8)
              & (ky["n_features"] >= 3) & (ky["n_out_of_range"] <= 1)].copy()
    cand["spot"] = cand["lat"].round(3).astype(str) + "," + cand["lon"].round(3).astype(str)
    cand = cand.drop_duplicates("spot")
    cols = ["rank", "site_name", "coal_field", "county_fips", "site_type", "lat", "lon",
            "tier", "p_elevated_ree", "pred_y_ug_l", "ph", "sulfate_mg_l", "al_ug_l", "n_features",
            "n_out_of_range", "last_year", "stale", "Y_ug_l"]
    cand[cols].head(25).to_csv(REPORTS / "ky_top_creeks.csv")
    recent = cand[~cand["stale"]]
    recent[cols].head(15).to_csv(REPORTS / "ky_field_shortlist_recent.csv")

    metrics = {
        "target": f"median dissolved/total Y >= {THRESHOLD_UG_L} ug/L",
        "features": FEATURES,
        "spatial_cv": {k: v for k, v in cv.items() if not k.startswith("_")},
        "magnitude_spatial_cv": {k: v for k, v in rcv.items() if not k.startswith("_")},
        "ky_transfer_test": transfer,
        "anthracite_sensitivity": sensitivity,
        "mean_abs_shap": importance,
        "ky_sites_scored": int(len(ky)),
        "ky_surface_sites_p_over_0.5": int((ky["surface_water"] & (ky["p_elevated_ree"] > 0.5)).sum()),
        "ky_shortlist_candidates": int(len(cand)),
        "ky_shortlist_candidates_sampled_since_1990": int(len(recent)),
    }
    (REPORTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("ky_sites_scored", "ky_surface_sites_p_over_0.5",
                                              "ky_shortlist_candidates", "ky_shortlist_candidates_sampled_since_1990")}, indent=2))
    print(f"Top creeks -> {(REPORTS / 'ky_top_creeks.csv').relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
