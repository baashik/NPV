# Methodology

This document explains the financial logic used in the NPV biotech modelling tool.

## 1. Core DCF

The model builds an annual forecast from market and commercial assumptions:

```text
Total Population
× Target Patient %
× Diagnosis Rate
× Treatment Rate
× Market Penetration
= Patients Treated

Patients Treated (M) × Price Per Unit = Revenue ($M)
```

Costs include COGS, R&D by clinical phase, approval expense, pre-marketing, and G&A / OpEx. Free cash flow is calculated after tax.

## 2. Tax Loss Carry-Forward

The model carries forward accumulated operating losses. If EBITDA is negative, the loss balance increases. If EBITDA becomes positive, the model uses prior losses to offset taxable income before calculating tax paid.

This avoids overstating early tax expense in development-stage biotech models.

## 3. Phase-Gate Probability Adjustment

Because the asset is assumed to be in Phase I, future cash flows are probability-adjusted using clinical success assumptions:

```text
Probability to Approval = Phase I success × Phase II success × Phase III success × Approval success
```

Post-launch commercial cash flows remain risk-adjusted by the cumulative probability of approval, because approval has not yet been achieved at the valuation date.

## 4. Licensor / Licensee Economics

The model separates economics for both sides of a licensing deal:

- Licensee pays upfronts, milestones, and royalties.
- Licensor receives upfronts, milestones, and royalties.
- Royalty payments are tiered by revenue thresholds.
- Licensor cash flows are discounted using the licensor discount rate.
- Licensee cash flows are discounted using the licensee WACC.

## 5. Monte Carlo Simulation

The Monte Carlo engine varies key inputs around the current dashboard assumptions.

### Probability distributions

- Phase success probabilities use Beta distributions, which keep results between 0% and 100%.
- Price, penetration, patient pool, diagnosis, treatment, and COGS use triangular distributions.
- Discount rates use bounded normal distributions.

### Correlation rule

Launch timing and R&D costs are linked. If a simulation delays launch, the model increases development costs to reflect longer or more complex trials.

## 6. Sensitivity / Tornado Analysis

The tornado chart tests one variable at a time and measures the impact on selected NPV metrics. It is useful for seeing which assumptions drive the model most.

## 7. Advanced Valuation Extensions

The repo includes standalone helper functions for:

- Gordon Growth terminal value
- Exit multiple terminal value
- Black-Scholes-style expansion option value
- Simple abandonment option value

These are not yet wired into the main dashboard because they require careful methodology choices before being included in investor-facing outputs.

## 8. Current Limitations

- The Monte Carlo engine is directional and should be reconciled against Excel benchmarks before investor use.
- Dynamic phase-adjusted discount rates are not yet built into the main DCF.
- Scenario persistence and PDF/Excel export are not yet enabled.
- Real Options Valuation is currently provided as helper logic only, not a full binomial decision tree.
