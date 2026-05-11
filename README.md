---
title: Biopharma Licensing Monte Carlo NPV
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_file: app.py
pinned: false
---

# Biopharma Licensing Monte Carlo NPV

A Dash web app for modeling a **biopharma licensing deal** using Monte Carlo simulation and discounted cash flow analysis.

## Deal setup

This app models the following transaction:

- **Drug:** GATX-11
- **Indication:** Fibrosis
- **Stage:** Phase I
- **Territory:** EU exclusive license
- **Parties:** Licensor (biotech) and Licensee (pharma partner)

## What the app shows

The app estimates:

- Licensee base-case eNPV
- Licensor base-case deal NPV
- Monte Carlo outcome distributions
- Annual DCF outputs
- Revenue and probability charts

## App structure

The app is designed in 3 sections:

1. **Assumptions**  
   Edit core commercial, financial, probability, and deal inputs.

2. **DCF Table & NPVs**  
   Review the annual base-case DCF table and key valuation outputs.

3. **Figures**  
   View revenue, NPV distribution, and cumulative probability charts.

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
- Number of Monte Carlo simulations

## Technical setup

- Built with **Dash**
- Uses **NumPy**, **Pandas**, and **Plotly**
- Deployed as a **Docker-based Hugging Face Space**

## Notes

This repository is intended for interactive valuation analysis in the browser.  
After editing assumptions and re-running the model, the app recalculates outputs dynamically.
