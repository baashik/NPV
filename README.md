---
title: Biopharma Licensing Valuation Platform
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_file: app.py
pinned: false
---

# Biopharma Licensing Valuation Platform

A Dash web app for modeling a **biopharma licensing deal** using a modular DCF, risk-adjusted NPV, tiered royalties, licensor economics, and Monte Carlo simulation.

## Deal setup

This app models the following transaction:

- **Drug:** GATX-11
- **Indication:** Fibrosis
- **Stage:** Phase I
- **Territory:** EU exclusive license
- **Parties:** Licensor (biotech) and Licensee (pharma partner)

## What the app shows

The app estimates:

- Deterministic risk-adjusted rNPV
- Licensee eNPV after licensing payments
- Licensor NPV from upfront, milestones, and royalties
- Annual patient, revenue, cost, FCF, and discounted cash flow outputs
- Peak revenue and treated patient metrics
- Probability-adjusted development cash flows
- Monte Carlo NPV distributions
- Tornado / sensitivity analysis

## App structure

The app is designed in 3 sections:

1. **Assumptions + DCF**  
   Edit commercial, financial, tax, WACC, and phase-success assumptions; review the live DCF table, summary cards, charts, and tornado analysis.

2. **Licensor Model**  
   Model upfront payments, milestones, tiered royalties, licensor NPV, and licensor cash flow bridge.

3. **Monte Carlo**  
   Run stochastic valuation across WACC, price, penetration, probability of success, and development cost ranges.

## Core model inputs

The assumptions can include items such as:

- EU population
- Population growth
- Target patient share
- Diagnosis rate
- Treatment rate
- Peak penetration
- Price per patient
- COGS
- G&A
- Tax rate
- Licensee WACC
- Licensor WACC
- Upfront payment
- Milestones
- Tiered royalty rates
- Number of Monte Carlo simulations

## Technical setup

- Built with **Dash**
- Uses **NumPy**, **Pandas**, and **Plotly**
- Deployed as a **Docker-based Hugging Face Space**

## Notes

This repository is intended for interactive valuation analysis in the browser.  
After editing assumptions and re-running the model, the app recalculates outputs dynamically.
