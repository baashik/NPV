"""Monte Carlo and sensitivity helpers for the valuation dashboard."""

from __future__ import annotations

from typing import Any

import numpy as np

from model_engine import build_dcf_model, clean_assumptions


def parse_low_base_high(value: Any, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if value is None:
        return default
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(float(v) for v in value)

    parts = str(value).replace(",", "").replace("%", "").replace("|", "/").split("/")
    if len(parts) != 3:
        return default
    try:
        low, base, high = (float(part.strip()) for part in parts)
    except ValueError:
        return default
    if low > high:
        low, high = high, low
    base = min(max(base, low), high)
    return low, base, high


def npv_stats(values: list[float] | np.ndarray) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    percentiles = np.percentile(arr, [5, 10, 25, 50, 75, 90, 95])
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "p5": float(percentiles[0]),
        "p10": float(percentiles[1]),
        "p25": float(percentiles[2]),
        "p50": float(percentiles[3]),
        "p75": float(percentiles[4]),
        "p90": float(percentiles[5]),
        "p95": float(percentiles[6]),
        "max": float(np.max(arr)),
        "prob_pos": float(np.mean(arr > 0)),
    }


def _clinical_probability(assumptions: dict[str, Any]) -> float:
    return (
        assumptions["phase_i_success"]
        * assumptions["phase_ii_success"]
        * assumptions["phase_iii_success"]
        * assumptions["approval_success"]
    ) / (100 ** 4)


def _scale_success_rates(assumptions: dict[str, Any], target_probability_pct: float) -> dict[str, Any]:
    current = max(_clinical_probability(assumptions), 0.0001)
    target = max(target_probability_pct / 100.0, 0.0001)
    scale = (target / current) ** 0.25
    updated = dict(assumptions)
    for key in ("phase_i_success", "phase_ii_success", "phase_iii_success", "approval_success"):
        updated[key] = min(max(updated[key] * scale, 1.0), 99.0)
    return updated


def run_monte_carlo(
    assumptions: dict[str, Any],
    overrides: dict[str, Any] | None = None,
    n_sims: int = 5000,
    seed: int = 42,
    ranges: dict[str, tuple[float, float, float]] | None = None,
) -> dict[str, Any]:
    base = clean_assumptions(assumptions)
    overrides = overrides or {}
    ranges = ranges or {}
    rng = np.random.default_rng(seed)
    n_sims = max(100, min(int(n_sims or 5000), 50000))

    wacc_range = ranges.get("wacc", (base["wacc"] * 0.8, base["wacc"], base["wacc"] * 1.25))
    peak_range = ranges.get("peak_penetration", (base["peak_penetration"] * 0.6, base["peak_penetration"], base["peak_penetration"] * 1.4))
    price_range = ranges.get("price_per_unit", (base["price_per_unit"] * 0.75, base["price_per_unit"], base["price_per_unit"] * 1.25))
    prob_range = ranges.get("probability_success", (10.0, max(_clinical_probability(base) * 100, 1.0), 35.0))
    cost_range = ranges.get("development_cost_multiplier", (0.8, 1.0, 1.3))

    rnpv = []
    licensee_enpv = []
    licensor_npv = []

    for _ in range(n_sims):
        sampled = dict(base)
        sampled["wacc"] = float(rng.triangular(*wacc_range))
        sampled["licensee_discount_rate"] = sampled["wacc"]
        sampled["licensor_discount_rate"] = float(np.clip(rng.normal(base["licensor_discount_rate"], 2.0), 4.0, 30.0))
        sampled["peak_penetration"] = float(rng.triangular(*peak_range))
        sampled["price_per_unit"] = float(max(rng.triangular(*price_range), 1.0))
        sampled = _scale_success_rates(sampled, float(rng.triangular(*prob_range)))

        cost_multiplier = float(rng.triangular(*cost_range))
        for key in ("phase_i_rd", "phase_ii_rd", "phase_iii_rd", "approval_expense", "pre_marketing"):
            sampled[key] = sampled[key] * cost_multiplier

        summary = build_dcf_model(sampled, overrides)["summary"]
        rnpv.append(summary["rnpv"])
        licensee_enpv.append(summary["licensee_enpv"])
        licensor_npv.append(summary["licensor_npv"])

    return {
        "rnpv": rnpv,
        "licensee_enpv": licensee_enpv,
        "licensor_npv": licensor_npv,
        "rnpv_stats": npv_stats(rnpv),
        "licensee_stats": npv_stats(licensee_enpv),
        "licensor_stats": npv_stats(licensor_npv),
        "n_sims": n_sims,
    }


def run_sensitivity(assumptions: dict[str, Any], overrides: dict[str, Any] | None = None) -> list[dict[str, float | str]]:
    base = clean_assumptions(assumptions)
    overrides = overrides or {}
    base_value = build_dcf_model(base, overrides)["summary"]["licensee_enpv"]

    drivers = [
        ("Peak Penetration", "peak_penetration", 0.70, 1.30),
        ("Price Per Unit", "price_per_unit", 0.75, 1.25),
        ("Asset WACC", "wacc", 0.80, 1.25),
        ("Licensee Discount Rate", "licensee_discount_rate", 0.80, 1.25),
        ("Phase II Success", "phase_ii_success", 0.70, 1.30),
        ("COGS %", "cogs_pct", 0.75, 1.25),
        ("Tax Rate", "tax_rate", 0.75, 1.25),
        ("Development Costs", "phase_iii_rd", 0.75, 1.25),
    ]

    rows = []
    for label, key, low_mult, high_mult in drivers:
        low_case = dict(base)
        high_case = dict(base)
        low_case[key] = base[key] * low_mult
        high_case[key] = base[key] * high_mult
        low_value = build_dcf_model(low_case, overrides)["summary"]["licensee_enpv"]
        high_value = build_dcf_model(high_case, overrides)["summary"]["licensee_enpv"]
        rows.append(
            {
                "label": label,
                "low": float(low_value),
                "high": float(high_value),
                "base": float(base_value),
                "impact": float(abs(high_value - low_value)),
            }
        )

    return sorted(rows, key=lambda row: row["impact"], reverse=True)
