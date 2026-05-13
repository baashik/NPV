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

A Dash web app for modeling a licensing deal using Monte Carlo simulation and discounted cash flow analysis.

## Code Structure

- the full modular architecture (5 files instead of 1 monolith)
- vectorized Monte Carlo engine (~10-40x faster)
- optimized single-scenario DCF engine
- typed data models (ScenarioParams dataclass)
- precomputed static arrays (ADOPTION_ARRAY, RD_ARRAY)
- sensitivity analysis framework (6-variable sweep)
- clean Dash app with split layout/callbacks/engine
- fixed LCF (tax loss carry-forward) logic

## Files

```
app.py        — Entry point. Creates Dash app, registers callbacks, starts server.
config.py     — Constants, precomputed arrays, ScenarioParams dataclass.
engine.py     — Vectorized Monte Carlo, scenario runner, NPV stats, sensitivity.
ui.py         — Layout components, DCF table, chart builders.
callbacks.py  — Save/load/delete/export scenarios, run simulation, render tabs.
```

## Deal Setup

- **Drug:** Pipeline asset (Phase I)
- **Indication:** Fibrosis
- **Stage:** Phase I
- **Territory:** EU exclusive license
- **Parties:** Licensor and Licensee

## What it Estimates

- Licensee base-case eNPV
- Licensor base-case deal NPV
- Monte Carlo outcome distributions
- Annual DCF outputs
- Revenue and probability charts

## Technical Stack

- **Dash** + **Dash Bootstrap Components** (UI)
- **NumPy** (vectorized engine)
- **Plotly** (charts)
- **Docker** (Hugging Face Spaces deployment)
