# KY REE Prospector

[![Open the live dashboard](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ky-ree-prospector.streamlit.app/)

**Ranking Kentucky's acid-mine-drainage streams by rare earth element (REE) potential, using machine learning, LLM-based literature mining, and field validation.**

**▶ Live dashboard: [ky-ree-prospector.streamlit.app](https://ky-ree-prospector.streamlit.app/)**

## Results so far

| | |
|---|---|
| Literature mining | Claude API extracted 909 REE values from 5 reports; **909/909 traced to the source PDFs** (~$3 total) |
| Training data | 17,336 REE water results from the Water Quality Portal → 386 labeled sites across 6 states |
| Classifier | **AUC 0.96** on held-out watersheds (spatial CV) vs 0.92 for a low-pH baseline |
| Magnitude model | **R² 0.85** (log10 yttrium) on held-out watersheds; Kentucky checks within ~2× of measured |
| Scored | 3,756 Kentucky coal-field water sites; 37-site field shortlist sampled since 1990 |
| Mining context | 2,243 historical mines (300,000 acres) in Pike & Floyd; % of each creek's watershed mined |

> 🚧 Work in progress: field validation (Phase 5) is next. See [docs/PLAN.md](docs/PLAN.md).

## The question

Decades of coal mining left many eastern Kentucky creeks polluted with **acid mine drainage (AMD)**. Research in Pennsylvania and Appalachia has shown that AMD, and especially the orange iron/aluminum sludge it deposits, can be enriched in rare earth elements, which are critical minerals for magnets, batteries, and electronics.

**Which polluted Kentucky creeks are most likely to carry elevated rare earth elements?**

This project ranks streams by *relative* REE potential. It does **not** claim any site is an economically mineable deposit.

## Approach

| Phase | What | Skills shown |
|---|---|---|
| 1. Literature miner | Claude API extracts reported REE measurements from USGS / EPA / KGS reports into a structured table | LLM engineering, structured output, evaluation |
| 2. Data pipeline | Water chemistry (Water Quality Portal), KY 303(d) impaired streams, abandoned mine lands, coal geology, and Pennsylvania REE datasets | Data engineering, geospatial joins |
| 3. Model | Literature-based baseline score + ML model trained on PA + KY labeled sites, spatial cross-validation, SHAP explanations | Data science, ML validation |
| 4. Dashboard | Interactive Streamlit map of ranked creeks with an "ask the reports" assistant | Product, deployment |
| 5. Field validation | Sample top-ranked and control creeks, lab ICP-MS analysis, compare to predictions | Scientific rigor |

## Repository layout

```
ky-ree-prospector/
├── app/              # Streamlit dashboard (Phase 4)
├── data/
│   ├── raw/          # Downloaded source data, never edited by hand (not committed)
│   ├── interim/      # Partially cleaned data (not committed)
│   ├── processed/    # Model-ready datasets (not committed)
│   └── field/        # Our own field sampling + lab results
├── docs/             # Plan, methods, data source notes
├── notebooks/        # Exploration and analysis notebooks
├── reports/figures/  # Charts and maps for the write-up
├── src/ky_ree/       # Reusable Python code (the pipeline)
└── tests/            # Automated tests
```

## Getting started

```bash
# 1. Create and activate a virtual environment (Windows / Git Bash)
python -m venv .venv
source .venv/Scripts/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Check everything works
python -m ky_ree.check_setup
```

To use the LLM features, copy `.env.example` to `.env` and add your Anthropic API key. `.env` is git-ignored and never committed.

### Run the pipeline

```bash
python -m ky_ree.download_papers      # Phase 1: reports
python -m ky_ree.extract --all        # Phase 1: Claude extraction (~$3)
python -m ky_ree.verify_extractions   # Phase 1: check values against PDFs
python -m ky_ree.wqp                  # Phase 2: Water Quality Portal downloads
python -m ky_ree.build_dataset        # Phase 2: clean site tables
python -m ky_ree.mines Pike Floyd     # Mine footprints
python -m ky_ree.upstream Pike Floyd  # % of each watershed mined
python -m ky_ree.model                # Phase 3: train, validate, rank
python -m ky_ree.export_app_data      # Phase 4: small files for the dashboard
```

### Run the dashboard

```bash
streamlit run app/streamlit_app.py
```

Interactive map of every scored Kentucky coal-field site (filter by county, tier, recency),
mined-out areas for Pike & Floyd, a downloadable field-sampling shortlist, and model diagnostics.

## Data sources

- [USGS: Coal mine drainage effluents and solids, REE data (PA, 2024)](https://www.usgs.gov/data/coal-mine-drainage-effluents-and-associated-solids-major-trace-rare-earth-element-and-radium)
- [EPA: REE data from AMD and refuse piles, Shamokin PA (2024)](https://catalog.data.gov/dataset/rare-earth-element-data-from-acid-mine-drainage-and-refuse-piles-in-shamokin-pennsylvania)
- [Water Quality Portal (USGS / EPA)](https://www.waterqualitydata.us/)
- Kentucky 303(d) impaired waters list (KY Energy and Environment Cabinet)
- OSMRE Abandoned Mine Land Inventory (e-AMLIS)
- Kentucky Geological Survey coal and geochemistry data

## Limitations

- Few sites have direct REE measurements, so the model is trained on a small labeled set and reports uncertainty.
- Pennsylvania training data come from a related but different geology (anthracite vs. bituminous); transfer to Kentucky is tested explicitly, not assumed.
- Field sampling is done only with public access or landowner permission.

## License

MIT, see [LICENSE](LICENSE).
