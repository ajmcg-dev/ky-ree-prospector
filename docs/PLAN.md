# Project Plan

Timeline: ~10–12 weeks. Check items off as you go; this file doubles as a progress log.

## Phase 0: Setup (week 1)
- [x] Repo structure, README, .gitignore, requirements
- [x] Virtual environment working, `python -m ky_ree.check_setup` passes
- [x] First commit
- [x] Push to GitHub
- [ ] Learn: `git status`, `git add`, `git commit`, `git push`

## Phase 1: LLM literature miner (weeks 2–3)
- [ ] Collect ~20–40 public reports/papers (USGS, EPA, KGS, UKy, DOE/NETL) into `data/raw/papers/`
- [ ] Define the extraction schema (site, lat/lon, state, sample type, element, value, units, source, page)
- [ ] Claude API extraction with structured output
- [ ] Hand-check a sample and report extraction accuracy
- [ ] Budget: keep total API spend under ~$20

## Phase 2: Data pipeline (weeks 3–5)
- [ ] Pennsylvania REE data (USGS 2024 release, EPA Shamokin) → harmonized table
- [ ] Water Quality Portal pull for the Eastern KY Coal Field (pH, SO4, Al, Fe, Mn, conductivity, REEs)
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
