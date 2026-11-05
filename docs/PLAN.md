# Project Plan

Timeline: ~10–12 weeks. Check items off as you go; this file doubles as a progress log.

## Phase 0: Setup (week 1)
- [x] Repo structure, README, .gitignore, requirements
- [x] Virtual environment working, `python -m ky_ree.check_setup` passes
- [x] First commit
- [x] Push to GitHub
- [ ] Learn: `git status`, `git add`, `git commit`, `git push`

## Phase 1: LLM literature miner (weeks 2–3)
- [ ] Collect ~20–40 public reports/papers (USGS, EPA, KGS, UKy, DOE/NETL) into `data/raw/papers/`. 5 so far (`data/papers_manifest.csv`)
- [x] Define the extraction schema (`src/ky_ree/schema.py`)
- [x] Claude API extraction with structured output (`src/ky_ree/extract.py`), first test on vass2019_part2: $0.46, values spot-checked against PDF
- [x] Ran all 5 papers: 61 sample groups, 909 REE values, total API spend $2.86
- [x] Automated check (`verify_extractions.py`): 909/909 values found in source PDFs (one needed a manual look: a broken "0. 07" in the PDF text, which Claude read correctly)
- [ ] Hand-check ~30 random values for correct element/site attribution
- Findings:
  - Most papers print only summaries; Vass Part 2 has basin averages only, no KY sites.
  - Cravotta 2008: per-site data for all 140 PA sites is in USGS NWIS → pull in Phase 2.
  - Vass Part 1: 10 WV/PA sites with per-site means (water + precipitate).
  - Only KY data so far: one western KY coal-refuse AMD (TREE 6.6 ppm), not eastern KY creeks.
  - Several papers print major ions in ppm; currently left null (ppm ≈ mg/L for dilute water; decide in Phase 2).
- [ ] Hand-check a sample and report extraction accuracy
- [ ] Budget: keep total API spend under ~$20

## Phase 2: Data pipeline (weeks 3–5)
- [x] Water Quality Portal: REE results for KY, PA, WV, VA, OH, TN + chemistry at those sites (`wqp.py`)
- [x] Clean one-row-per-site table (`build_dataset.py` → `data/processed/sites.csv`)
  - 17,336 REE water results (9,960 detected) at 1,791 sites; 383 sites have detected REE + pH + sulfate
  - Sanity check: Spearman(REE, pH) = −0.86 to −0.88; median Y 22 µg/L at pH<5 vs 0.08 at pH≥6.5 (matches literature)
  - Training sites are 375/383 PA (mostly mine discharges) → domain shift to KY must be tested
  - KY: 11 sites with detected REE, mostly Knott/Floyd Co. streams (EPA Region 4, 2013; Y 3–15 µg/L) but no pH/sulfate in WQP for them
  - Check: Red River site with Y 18.6 µg/L at pH 8.0 looks unusual, verify
- [x] Pull KY coal-field water chemistry at ALL sites (49 counties) → `data/processed/ky_sites.csv`
  - 3,760 sites (east 2,469, west 1,291); 2,879 with pH; 187 acidic (median pH < 5.5)
  - Acidic hotspots: McCreary (49), Pulaski (25), Hopkins (20, western KY), Bell (13)
  - Most extreme: Copperas Creek, Hopkins Co., pH 2.7, sulfate ~2,700 mg/L, Al ~150,000 µg/L, but last sampled 1965–67
  - 81 of 187 acidic sites were last sampled before 1990; conditions may have changed (reclamation). Weight recency, and field-check old hotspots
  - 46 acidic sites are wells (groundwater); the "creeks" ranking should filter to surface water
  - Knott Co. REE sites (Y up to 15 µg/L) have sulfate but no pH → model must handle missing features
  - Feature gaps on acidic sites: sulfate 87/187, Al 94/187 → use a model that tolerates missing values (e.g. HistGradientBoosting)
- [ ] USGS 2024 release + EPA Shamokin (extra PA sites with solids data)
- [ ] KY 303(d) impaired streams (AMD-related causes)
- [ ] Abandoned mine land features (OSMRE e-AMLIS)
- [ ] Coal seam / geology layers (KGS)
- [ ] One rerunnable script: raw → processed

## Phase 3: Scoring + ML (weeks 5–7)
- [ ] Literature-based baseline score
- [ ] ML model on labeled PA + KY sites (tag coal type: anthracite vs. bituminous)
- [ ] Spatial cross-validation; "train on PA, test on KY" transfer experiment
- [ ] SHAP explanations, uncertainty estimates
- [ ] Ranked list of KY creeks

## Phase 4: Dashboard (weeks 7–8)
- [ ] Streamlit + Folium map of ranked creeks
- [ ] Site detail panel (score, drivers, nearby mines)
- [ ] "Ask the reports" assistant over Phase 1 data
- [ ] Deploy to Streamlit Community Cloud

## Phase 5: Field validation (weeks 8–11)
- [ ] Choose ~3 top-ranked + ~2 low-ranked control creeks with public access or written permission
- [ ] Get ICP-MS lab quotes and sampling/preservation instructions
- [ ] Collect water + orange sediment; record GPS, pH, conductivity, photos
- [ ] Safety: nitrile gloves, eye protection, never enter mine openings, don't go alone
- [ ] Compare lab results to predictions and report honestly

## Phase 6: Polish (weeks 11–12)
- [ ] README results section, architecture diagram, limitations
- [ ] Write-up / blog post
- [ ] 2-minute demo video
- [ ] Resume bullet with real numbers
