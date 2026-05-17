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

A Dash web app for modelling a biopharma licensing deal using discounted cash flow analysis, licensor/licensee deal economics, one-way sensitivity, and a lightweight Monte Carlo simulation.

## What the App Does

- Builds a deterministic DCF from editable market, cost, tax, discount-rate, phase-success, and licensing assumptions.
- Shows asset rNPV, licensee eNPV, licensor NPV, peak revenue, peak patients, launch year, and probability to approval.
- Links the licensee and licensor models through upfront, milestone, and tiered royalty economics.
- Provides a tornado sensitivity chart based on the current dashboard assumptions.
- Runs a lightweight Monte Carlo simulation around the current assumptions for rNPV distribution, mean, median, P10/P90, and probability of positive rNPV.

## Current File Structure

```text
app.py          — Dash entry point. Creates the app, exposes server, and registers callbacks.
callbacks.py    — Navigation, DCF updates, table overrides, sensitivity, charts, and Monte Carlo outputs.
layout.py       — Dashboard layout, assumption panel, tabs, tables, cards, and charts.
model_engine.py — Deterministic DCF engine, licensor/licensee economics, formatting, and sensitivity logic.
styles.py       — Shared colours and layout styling.
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

## Monte Carlo Note

The current Monte Carlo simulation is intentionally lightweight and transparent. It varies key commercial, timing, cost, discount-rate, and phase-success assumptions around the current dashboard inputs. It is useful for directional investor discussion, but it should be refined further before being treated as a formal statistical valuation.

## Technical Stack

- Dash
- Dash Bootstrap Components
- NumPy
- Pandas
- Plotly
- Docker / Gunicorn deployment
