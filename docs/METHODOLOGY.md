# Methodology

This document explains the financial logic used in the NPV biotech modelling tool and links the underlying valuation mathematics to the Python implementation.

## 1. Why NPV Matters

Net Present Value (NPV) is the core valuation method used to convert future cash flows into today's money. In corporate finance, M&A, licensing, and institutional investment analysis, NPV is often treated as the practical gold standard for estimating intrinsic value.

The logic is simple:

```math
NPV = \sum_{t=0}^{n} \frac{CF_t}{(1+r)^t}
```

Where:

- `CF_t` = cash flow in period `t`
- `r` = discount rate / hurdle rate
- `t` = period number

A positive NPV means the project is expected to create value above the selected hurdle rate. A negative NPV means the project is expected to destroy value under the current assumptions.

## 2. From Formula to Code

Simple fixed-payment examples can be solved with geometric series logic. Real biotech models cannot.

A geometric series works well when the cash flow is constant, for example a fixed monthly payment. But biotech valuation involves non-conventional cash flows:

- R&D costs vary by phase.
- Milestones occur in specific years.
- Royalties depend on future revenue tiers.
- Tax losses carry forward.
- Launch timing is uncertain.
- Clinical probabilities change the value of future cash flows.

That is why a Python engine is useful. It can model irregular annual cash flows, stochastic simulation, licensing economics, and scenario logic in a repeatable way.

> **Technical warning — NPV timing convention**
>
> Python and spreadsheet NPV functions can use different timing conventions. Some functions assume the first cash flow is at `t = 0`; others discount all listed cash flows as if they occur at the end of each period. Always check whether the upfront investment is included separately or inside the NPV cash-flow series.

## 3. Phone Contract Example: Geometric Series Logic

A fixed monthly contract can be valued as a finite annuity.

If a phone plan requires a `-$20` payment for 24 months and the annual discount rate is `1.5%`, the monthly discount rate is:

```math
r_m = (1 + 0.015)^{1/12} - 1
```

The present value of the 24 monthly payments is:

```math
PV = -20 \times \frac{1 - (1 + r_m)^{-24}}{r_m}
```

This gives approximately:

```text
PV ≈ -$473.17
```

If the upfront purchase price is `$475`, the monthly contract is slightly cheaper in present-value terms.

This example is useful because it shows the mathematical base of discounting. But it is still far simpler than biotech licensing, where cash flows are irregular and uncertain.

## 4. Three-Step Valuation Process

```text
1. Identify cash flows
   - Revenue
   - R&D costs
   - COGS
   - Operating costs
   - Taxes
   - Upfronts, milestones, and royalties

2. Select the hurdle rate
   - Asset discount rate
   - Licensee WACC
   - Licensor discount rate
   - Risk profile by asset stage

3. Discount and interpret results
   - Asset rNPV
   - Licensee eNPV
   - Licensor NPV
   - Sensitivity and Monte Carlo distribution
```

## 5. Core DCF

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

## 6. Tax Loss Carry-Forward

The model carries forward accumulated operating losses. If EBITDA is negative, the loss balance increases. If EBITDA becomes positive, the model uses prior losses to offset taxable income before calculating tax paid.

This avoids overstating early tax expense in development-stage biotech models.

## 7. Phase-Gate Probability Adjustment

Because the asset is assumed to be in Phase I, future cash flows are probability-adjusted using clinical success assumptions:

```text
Probability to Approval = Phase I success × Phase II success × Phase III success × Approval success
```

Post-launch commercial cash flows remain risk-adjusted by the cumulative probability of approval, because approval has not yet been achieved at the valuation date.

## 8. Licensor / Licensee Economics

The model separates economics for both sides of a licensing deal:

- Licensee pays upfronts, milestones, and royalties.
- Licensor receives upfronts, milestones, and royalties.
- Royalty payments are tiered by revenue thresholds.
- Licensor cash flows are discounted using the licensor discount rate.
- Licensee cash flows are discounted using the licensee WACC.

## 9. Deterministic NPV vs Monte Carlo Simulation

Traditional DCF gives one output number. This is useful, but it can create a deterministic trap: users may treat a single NPV as if it is certain.

Monte Carlo simulation solves this by producing a distribution of outcomes. Instead of only asking, “What is the NPV?”, the model can also ask:

- What is the probability NPV is positive?
- What is the downside case?
- What is the upside case?
- Which assumptions create the largest spread of outcomes?

This is especially important for high-risk ventures such as biotech, AI implementation, and other uncertain R&D projects.

## 10. Monte Carlo Simulation

The Monte Carlo engine varies key inputs around the current dashboard assumptions.

### Probability distributions

- Phase success probabilities use Beta distributions, which keep results between 0% and 100%.
- Price, penetration, patient pool, diagnosis, treatment, and COGS use triangular distributions.
- Discount rates use bounded normal distributions.

### Correlation rule

Launch timing and R&D costs are linked. If a simulation delays launch, the model increases development costs to reflect longer or more complex trials.

## 11. Sensitivity / Tornado Analysis

The tornado chart tests one variable at a time and measures the impact on selected NPV metrics. It is useful for seeing which assumptions drive the model most.

## 12. Spreadsheet vs Simulation Tool

| Area | Traditional Spreadsheet NPV | Python Simulation Tool |
|---|---|---|
| Cash flows | Often manually linked | Generated from assumptions |
| Sensitivity | Manual data tables / scenarios | Automated tornado analysis |
| Uncertainty | Usually one case at a time | Distribution of outcomes |
| Auditability | Cell-by-cell review | Function and test based |
| Speed | Slower for many simulations | Faster repeatable simulations |
| Version control | Difficult | Git-based workflow |

## 13. Model vs Data Parameterization

A strong financial modelling system separates the model logic from the input data.

In a spreadsheet, formulas and assumptions often sit together. In software, assumptions can be stored separately from the engine, for example in a `params.txt`, JSON, YAML, or database record. This allows rapid scenario iteration without editing the underlying model code.

This repo currently uses dashboard inputs and Python dictionaries for assumptions. A future version could add external scenario files or database-backed scenario persistence.

## 14. Advanced Valuation Extensions

The repo includes standalone helper functions for:

- Gordon Growth terminal value
- Exit multiple terminal value
- Black-Scholes-style expansion option value
- Simple abandonment option value

These are not yet wired into the main dashboard because they require careful methodology choices before being included in investor-facing outputs.

## 15. Current Limitations

- The Monte Carlo engine is directional and should be reconciled against Excel benchmarks before investor use.
- Dynamic phase-adjusted discount rates are not yet built into the main DCF.
- Scenario persistence and PDF/Excel export are not yet enabled.
- Real Options Valuation is currently provided as helper logic only, not a full binomial decision tree.
- External parameter files such as `params.txt` are not yet supported.
