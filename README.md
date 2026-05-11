---
title: GATX-11 Biopharma Licensing NPV Dashboard
emoji: 🧬
colorFrom: blue
colorTo: teal
sdk: docker
pinned: false
license: mit
app_port: 7860
---

# 🧬 GATX-11 Biopharma Licensing — Monte Carlo NPV Dashboard

> **Interactive web dashboard for biopharma deal valuation.**  
> Licensor (Biotech) ↔ Licensee (Pharma Partner) | EU Exclusive License | Fibrosis · Phase I

---

## Overview

This tool implements a **full biopharma licensing deal valuation model** combining:

- **Bottom-up epidemiology** revenue forecasting (2026–2042)
- **PTRS risk-adjustment** (Probability of Technical & Regulatory Success) per clinical phase
- **Depletable tax loss carry-forward** (LCF) logic for accurate FCF
- **Monte Carlo simulation** (up to 10,000 iterations) over stochastic inputs
- **Tiered royalty structure** linked to licensee revenue
- **Separate NPV perspectives**: Licensee eNPV vs Licensor Deal NPV

---

## Dashboard Tabs

| Tab | Content |
|-----|---------|
| 📈 Revenue & Cash Flows | Revenue build-up, COGS, R&D, risk-adjusted FCF fan |
| 🎲 Monte Carlo | NPV distributions, S-curve CDFs, percentile bar chart |
| 📊 DCF Table | Full annual model — years as rows, all line items as columns |
| 🌪️ Tornado / Sensitivity | Key driver tornado + price sensitivity sweep |
| 🏦 Licensor Bridge | Waterfall: upfront → milestones → royalties → total NPV |

---

## Key Inputs (left sidebar — all editable)

| Parameter | Default | Note |
|-----------|---------|------|
| EU Population | 450M | Evaluatepharma 2023 |
| Price / Patient / Year | $15,000 | Adjustable |
| Peak Penetration | 5% | Primary physician survey |
| COGS | 12% | Locust Walk 2017 |
| Tax Rate | 21% | — |
| Licensee WACC | 10% | — |
| Licensor WACC | 14% | — |
| Ph1→Ph2 PTRS | 63% | BIO/Biomedtracker 2006–2015 |
| Ph2→Ph3 PTRS | 30% | BIO/Biomedtracker 2006–2015 |
| Ph3→NDA PTRS | 58% | BIO/Biomedtracker 2006–2015 |
| NDA→Approval | 90% | BIO/Biomedtracker 2006–2015 |
| Upfront Payment | $2M | Deal term |
| Dev Milestone (each) | $1M | Ph1/Ph2/Ph3 trigger |
| Simulations | 5,000 | Up to 10,000 |

### Stochastic Variables (sampled each iteration)
- Population growth rate: N(0.2%, 1.0%)
- Peak market penetration: N(5%, 1.5%), clipped > 0
- Price per patient: N(input, 15% of input)
- Licensee WACC: N(10%, 2.5%)
- Licensor WACC: N(14%, 2.5%)

### Royalty Tiers
| Revenue Band | Rate |
|---|---|
| $0 – $100M | 5.0% |
| $100M – $200M | 7.0% |
| > $200M | 9.0% |

---

## Model Architecture

```
Assumptions (sidebar)
        │
        ▼
run_scenario()              ← deterministic single-path engine
  ├─ Revenue (epidemiology × adoption × price)
  ├─ COGS / R&D / G&A
  ├─ Royalty (tiered)
  ├─ FCF (with depletable LCF tax shield)
  ├─ PTRS risk-adjustment (per phase)
  └─ Discounted → eNPV (licensee) / Deal NPV (licensor)
        │
        ▼
run_montecarlo()            ← N_SIMS iterations of run_scenario()
  └─ Returns ls_npvs[], lr_npvs[] arrays
        │
        ▼
Dash Callbacks              ← render 5 tab views + 4 KPI cards
```

---

## Local Setup

```bash
git clone https://github.com/<your-handle>/npv-dashboard
cd npv-dashboard

pip install -r requirements.txt

python app.py
# Open http://localhost:7860
```

### Docker

```bash
docker build -t npv-dashboard .
docker run -p 7860:7860 npv-dashboard
```

---

## Deploy to HuggingFace Spaces

1. Create a new Space: **SDK = Docker**
2. Push this repo (including `Dockerfile`) to the Space
3. HuggingFace will build and serve automatically on port 7860

---

## File Structure

```
npv-dashboard/
├── app.py               ← Full Dash application
├── requirements.txt     ← Python dependencies
├── Dockerfile           ← HuggingFace / Docker deployment
└── README.md            ← This file
```

---

## References

- BIO / Biomedtracker / Amplion: *Clinical Development Success Rates 2006–2015*
- Locust Walk: *Biopharma Partnering Deal Terms 2017*
- EvaluatePharma: *World Preview 2023*

---

## License

MIT — free to use, modify, and deploy.
