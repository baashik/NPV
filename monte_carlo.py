"""Monte Carlo engine for the biotech licensing DCF dashboard.

The simulation intentionally stays transparent rather than over-engineered:
- Success probabilities use Beta distributions so draws stay between 0% and 100%.
- Commercial inputs use triangular distributions where low / base / high logic is intuitive.
- Launch timing and R&D cost are correlated so delayed trials also tend to cost more.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from model_engine import build_dcf_model, clean_assumptions


PROBABILITY_KEYS = [
    "phase_i_success",
    "phase_ii_success",
    "phase_iii_success",
    "approval_success",
]


def _triangular_pct(rng: np.random.Generator, base_pct: float, low_mult: float, high_mult: float) -> float:
    """Draw a percentage assumption using low / most-likely / high values."""
    low = max(0.01, base_pct * low_mult)
    high = min(100.0, max(low + 0.01, base_pct * high_mult))
    mode = min(max(base_pct, low), high)
    return float(rng.triangular(low, mode, high))


def _triangular_value(rng: np.random.Generator, base_value: float, low_mult: float, high_mult: float) -> float:
    """Draw a positive value using low / most-likely / high values."""
    low = max(0.0, base_value * low_mult)
    high = max(low + 0.01, base_value * high_mult)
    mode = min(max(base_value, low), high)
    return float(rng.triangular(low, mode, high))


def _beta_probability(rng: np.random.Generator, base_pct: float, concentration: float = 35.0) -> float:
    """Draw a bounded probability around the base case.

    A higher concentration keeps draws closer to the base case; a lower one widens
    the distribution. Values are returned as percentages, not decimals.
    """
    mean = float(np.clip(base_pct / 100.0, 0.01, 0.99))
    alpha = max(mean * concentration, 0.5)
    beta = max((1.0 - mean) * concentration, 0.5)
    return float(rng.beta(alpha, beta) * 100.0)


def validate_simulation_assumptions(assumptions: dict) -> dict:
    """Apply basic guardrails before simulation.

    This is not a full Pydantic implementation, but it prevents common edge-case
    inputs from breaking or producing impossible values.
    """
    clean = clean_assumptions(assumptions)

    for key in PROBABILITY_KEYS + [
        "population_growth",
        "target_patient_pct",
        "diagnosis_rate",
        "treatment_rate",
        "peak_penetration",
        "cogs_pct",
        "ga_opex_pct",
        "tax_rate",
        "asset_discount_rate",
        "licensee_wacc",
        "licensor_discount_rate",
        "royalty_tier_1_rate",
        "royalty_tier_2_rate",
        "royalty_tier_3_rate",
    ]:
        clean[key] = float(np.clip(clean[key], 0.0, 100.0))

    for key in [
        "initial_population",
        "price_per_unit",
        "phase_i_rd",
        "phase_ii_rd",
        "phase_iii_rd",
        "approval_expense",
        "pre_marketing",
        "upfront_payment",
        "development_milestone",
        "regulatory_milestone",
        "commercial_milestone",
        "royalty_tier_1_threshold",
        "royalty_tier_2_threshold",
    ]:
        clean[key] = max(0.0, float(clean[key]))

    if clean["royalty_tier_2_threshold"] <= clean["royalty_tier_1_threshold"]:
        clean["royalty_tier_2_threshold"] = clean["royalty_tier_1_threshold"] + 1.0

    if clean["royalty_end_year"] < clean["royalty_start_year"]:
        clean["royalty_end_year"] = clean["royalty_start_year"]

    return clean


def run_biotech_monte_carlo(base_assumptions: dict, overrides: dict | None = None,
                            n_sims: int = 1_000, seed: int = 42) -> pd.DataFrame:
    """Run a biotech-focused Monte Carlo simulation around current assumptions."""
    rng = np.random.default_rng(seed)
    base = validate_simulation_assumptions(base_assumptions)
    overrides = overrides or {}
    results = []

    for _ in range(n_sims):
        a = dict(base)

        # Commercial variables: triangular distributions are intuitive for
        # low / most-likely / high forecasting.
        a["price_per_unit"] = _triangular_value(rng, base["price_per_unit"], 0.75, 1.30)
        a["peak_penetration"] = _triangular_pct(rng, base["peak_penetration"], 0.65, 1.35)
        a["target_patient_pct"] = _triangular_pct(rng, base["target_patient_pct"], 0.75, 1.25)
        a["diagnosis_rate"] = _triangular_pct(rng, base["diagnosis_rate"], 0.85, 1.10)
        a["treatment_rate"] = _triangular_pct(rng, base["treatment_rate"], 0.80, 1.20)
        a["cogs_pct"] = _triangular_pct(rng, base["cogs_pct"], 0.80, 1.30)

        # Bounded clinical probabilities.
        for key in PROBABILITY_KEYS:
            a[key] = _beta_probability(rng, base[key])

        # Correlated timing / cost logic: delayed programs tend to cost more.
        timing_shock = rng.choice([-1, 0, 1, 2], p=[0.15, 0.50, 0.25, 0.10])
        a["launch_year"] = int(base["launch_year"] + timing_shock)
        cost_multiplier = 1.0 + max(timing_shock, 0) * 0.15 + rng.normal(0.0, 0.05)
        cost_multiplier = float(np.clip(cost_multiplier, 0.80, 1.60))
        for cost_key in ["phase_i_rd", "phase_ii_rd", "phase_iii_rd", "approval_expense", "pre_marketing"]:
            a[cost_key] = max(0.0, base[cost_key] * cost_multiplier)

        # Discount-rate uncertainty, bounded to avoid impossible outputs.
        a["asset_discount_rate"] = float(np.clip(rng.normal(base["asset_discount_rate"], 1.5), 0.1, 50.0))
        a["licensee_wacc"] = float(np.clip(rng.normal(base["licensee_wacc"], 1.0), 0.1, 50.0))
        a["licensor_discount_rate"] = float(np.clip(rng.normal(base["licensor_discount_rate"], 1.5), 0.1, 60.0))

        model = build_dcf_model(a, overrides)
        summary = model["summary"]
        results.append({
            "rnpv": summary["rnpv"],
            "licensee_npv": summary["licensee_npv"],
            "licensor_npv": summary["licensor_npv"],
            "launch_year": a["launch_year"],
            "price_per_unit": a["price_per_unit"],
            "peak_penetration": a["peak_penetration"],
            "approval_probability": summary["approval_probability"],
        })

    return pd.DataFrame(results)
