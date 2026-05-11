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

A Dash web app for evaluating a biopharma EU licensing deal using Monte Carlo simulation.

## What the app does

This app models a licensing transaction for:

- **Drug:** GATX-11
- **Indication:** Fibrosis
- **Stage:** Phase I
- **Territory:** EU exclusive license
- **Parties:** Licensor (biotech) and Licensee (pharma partner)

The model estimates:

- Licensee base-case eNPV
- Licensor base-case deal NPV
- Monte Carlo distributions for both parties
- Annual DCF outputs
- Revenue fan chart and other valuation figures

## App structure

The app has 3 tabs:

1. **Assumptions**  
   Edit key commercial, financial, and deal inputs, then run the simulation.

2. **DCF Table & NPVs**  
   Review the annual base-case DCF table and headline valuation metrics.

3. **Figures**  
   View charts including revenue fan chart, NPV distributions, and cumulative probability curves.

## Core inputs

The assumptions section includes inputs such as:

- EU population
- Population growth
- Target patient share
- Diagnosis and treatment rates
- Peak penetration
- Price per patient
- COGS, G&A, and tax
- Licensee and licensor WACC
- Upfront payment
- Number of simulations

## Notes

- The app is implemented in **Dash** and served through a **Docker-based Hugging Face Space**.
- The Monte Carlo engine recalculates outputs when assumptions are changed and the simulation is re-run.
- This repository is focused on interactive valuation exploration rather than static chart export.
