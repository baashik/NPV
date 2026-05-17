---
title: Licensing Monte Carlo NPV
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_file: app.py
pinned: false
---

# Licensing Monte Carlo NPV

A Dash web app for modelling a biopharma licensing deal using discounted cash flow analysis, licensor/licensee deal economics, one-way sensitivity, and biotech-focused Monte Carlo simulation.

## What the App Does

- Builds a deterministic DCF from editable market, cost, tax, discount-rate, phase-success, and licensing assumptions.
- Shows asset rNPV, licensee eNPV, licensor NPV, peak revenue, peak patients, launch year, and probability to approval.
- Links the licensee and licensor models through upfront, milestone, and tiered royalty economics.
- Provides a tornado sensitivity chart based on the current dashboard assumptions.
- Runs a Monte Carlo simulation around the current assumptions for rNPV distribution, mean, median, P10/P90, and probability of positive rNPV.

## Biotech Monte Carlo Logic

The simulation is designed for biotech valuation rather than generic NPV analysis:

- Phase success probabilities use **Beta distributions**, keeping draws bounded between 0% and 100%.
- Commercial assumptions such as price, peak penetration, patient pool, diagnosis, treatment, and COGS use **triangular distributions** around low / base / high cases.
- Launch timing and R&D costs are linked through a simple correlation rule: delayed programs tend to carry higher development costs.
- Discount rates are varied within sensible bounds to avoid impossible outputs.
- Inputs are validated before simulation so negative costs, impossible probabilities, and inverted royalty thresholds are corrected.

## Current File Structure

```text
app.py              — Dash entry point. Creates the app, exposes server, and registers callbacks.
callbacks.py        — Navigation, DCF updates, table overrides, sensitivity, charts, and Monte Carlo outputs.
layout.py           — Dashboard layout, assumption panel, tabs, tables, cards, and charts.
model_engine.py     — Deterministic DCF engine, licensor/licensee economics, formatting, and sensitivity logic.
monte_carlo.py      — Biotech Monte Carlo engine, distributions, timing/cost correlation, and validation guardrails.
styles.py           — Shared colours and layout styling.
tests/              — Starter pytest coverage for royalty, DCF, validation, and Monte Carlo outputs.
requirements.txt
Dockerfile
```

## Deal Setup

- **Asset:** Pipeline asset
- **Stage:** Phase I
- **Territory:** EU exclusive license
- **Parties:** Licensor and licensee

## Unit Note

Patient counts are expressed in millions. Revenue is shown in currency millions, so:

```text
Patients Treated (M) × Price Per Unit = Revenue ($M)
```

## Testing

Run the starter tests with:

```bash
pytest
```

These tests are not a replacement for Excel benchmark reconciliation, but they provide a first layer of protection as the model develops.

## Screenshot / GIF

Add a dashboard screenshot or short GIF here once the app is running. Suggested path:

```text
assets/dashboard-preview.png
```

Then reference it in this README with:

```markdown
![Dashboard preview](assets/dashboard-preview.png)
```

## Technical Stack

- Dash
- Dash Bootstrap Components
- NumPy
- Pandas
- Plotly
- Pytest
- Docker / Gunicorn deployment
