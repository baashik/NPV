"""
NPV Model — Financial engine (vectorised Monte Carlo, scenario, sensitivity).
"""

from typing import Dict, List, Tuple
import numpy as np

from config import (
    ScenarioParams,
    N_YEARS,
    YEAR_INDEX,
    ADOPTION_ARRAY,
    RD_ARRAY,
    ROYALTY_TIERS_DEFAULT,
)


# ============================================================================
# Royalty
# ============================================================================
def compute_royalty(rev_m: float, tiers: List[Tuple[float, float, float]]) -> float:
    """Scalar royalty for a single revenue value."""
    roy = 0.0
    for lo, hi, rate in tiers:
        if rev_m > lo:
            roy += min(rev_m - lo, hi - lo) * rate
    return roy


def compute_royalty_vectorised(
    rev: np.ndarray, tiers: List[Tuple[float, float, float]]
) -> np.ndarray:
    """Vectorised royalty — same shape as rev."""
    royalty = np.zeros_like(rev)
    for lo, hi, rate in tiers:
        tier_rev = np.minimum(np.maximum(rev - lo, 0), hi - lo)
        royalty += tier_rev * rate
    return royalty


# ============================================================================
# PTRS schedule
# ============================================================================
def compute_ptr(params: ScenarioParams) -> np.ndarray:
    """Cumulative probability of technical success — shape (N_YEARS,)."""
    p_sched = np.array([1.0, params.p1, 1.0, params.p2, 1.0, params.p3, params.p4]
                       + [1.0] * (N_YEARS - 7))
    return np.cumprod(p_sched[:N_YEARS])


# ============================================================================
# Single scenario (returns dict for DCF table rendering)
# ============================================================================
def run_scenario(
    pg: float, pp: float, pr: float,
    asset_dr: float, licensee_wacc: float, licensor_dr: float,
    params: ScenarioParams,
) -> Dict:
    """
    Single-scenario NPV engine.  Uses vectorised operations internally
    but returns per-year arrays (for the DCF table).
    """
    ptr = compute_ptr(params)

    # ---- Revenue -----------------------------------------------------------
    pop_vector = params.eu_pop * (1 + pg) ** YEAR_INDEX
    treated = (
        pop_vector
        * params.ts * params.dr * params.tr
        * (pp * ADOPTION_ARRAY)
    )
    rev = np.maximum(treated * pr, 0.0)

    # ---- FCF with depletable LCF -------------------------------------------
    cogs = rev * params.cogs
    ga = rev * params.ga
    ebitda = rev - cogs - ga - RD_ARRAY

    royalty = compute_royalty_vectorised(rev, params.tiers)
    pre_tax = ebitda - royalty

    fcf = np.zeros(N_YEARS)
    lcf_balance = 0.0
    for i in range(N_YEARS):
        pt = pre_tax[i]
        if pt < 0:
            lcf_balance += -pt
            fcf[i] = pt
        else:
            used_lcf = min(lcf_balance, pt)
            taxable = pt - used_lcf
            lcf_balance -= used_lcf
            fcf[i] = pt - taxable * params.tax

    # ---- Risk adjustment & licensee -----------------------------------------
    risk_adj_fcf = fcf * ptr

    # ---- Licensor -----------------------------------------------------------
    licensor_cf = royalty * ptr
    licensor_cf[0] += params.upfront
    for yr_idx, mil_m in params.milestones.items():
        if 0 < yr_idx < N_YEARS:
            licensor_cf[yr_idx] += mil_m * ptr[yr_idx]

    # ---- Discount -----------------------------------------------------------
    df_asset = (1 + asset_dr) ** -YEAR_INDEX
    df_ls = (1 + licensee_wacc) ** -YEAR_INDEX
    df_lr = (1 + licensor_dr) ** -YEAR_INDEX

    return {
        "rev":            rev,
        "cogs":           cogs,
        "ebitda":         ebitda,
        "royalty":        royalty,
        "fcf":            fcf,
        "risk_adj_fcf":   risk_adj_fcf,
        "licensor_cf":    licensor_cf,
        "ptr":            ptr,
        "df_asset":       df_asset,
        "df_ls":          df_ls,
        "asset_rnpv":     float(np.sum(risk_adj_fcf * df_asset)),
        "licensee_enpv":  float(np.sum(risk_adj_fcf * df_ls)),
        "licensor_npv":   float(np.sum(licensor_cf * df_lr)),
    }


# ============================================================================
# Vectorised Monte Carlo  (~10–40× faster than original Python loop)
# ============================================================================
def run_montecarlo(
    n_sims: int, params: ScenarioParams, price: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Fully vectorised Monte Carlo simulation.

    Generates all random draws upfront, then computes every scenario using
    matrix operations.  Only loops over years (17 iterations) for the LCF
    carry-forward, which is inherently sequential.

    Returns
    -------
    ls_npvs : np.ndarray  (n_sims,)   Licensee eNPVs
    lr_npvs : np.ndarray  (n_sims,)   Licensor NPVs
    """
    rng = np.random.default_rng(42)

    pgs  = np.clip(rng.normal(0.002,  0.010, size=n_sims), -0.05, 0.05)
    pps  = np.clip(rng.normal(0.05,   0.015, size=n_sims),  0.005, 0.20)
    prs  = np.maximum(rng.normal(price, price * 0.15, size=n_sims), 5.0)
    asset_dr = np.clip(rng.normal(params.asset_discount_rate, 0.025, size=n_sims), 0.04, 0.25)
    lsws = np.clip(rng.normal(params.licensee_wacc, 0.025, size=n_sims), 0.04, 0.25)
    lrws = np.clip(rng.normal(params.licensor_discount_rate, 0.025, size=n_sims), 0.04, 0.30)

    ptr = compute_ptr(params)                 # (N_YEARS,)  — same for all sims

    # Population & revenue  (n_sims, N_YEARS)
    pop = params.eu_pop * (1 + pgs[:, None]) ** YEAR_INDEX
    treated = pop * params.ts * params.dr * params.tr * (pps[:, None] * ADOPTION_ARRAY)
    rev = np.maximum(treated * prs[:, None], 0.0)

    cogs = rev * params.cogs
    ga   = rev * params.ga
    ebitda = rev - cogs - ga - RD_ARRAY       # (n_sims, N_YEARS)

    royalty = compute_royalty_vectorised(rev, params.tiers)
    pre_tax = ebitda - royalty                 # (n_sims, N_YEARS)

    # LCF loop — only over years (≈17 iterations, vs 10k in the original)
    fcf = np.zeros((n_sims, N_YEARS))
    lcf_balance = np.zeros(n_sims)
    for i in range(N_YEARS):
        pt = pre_tax[:, i]
        loss = pt < 0

        lcf_balance[loss] += -pt[loss]
        fcf[loss, i] = pt[loss]

        gain = ~loss
        used = np.minimum(lcf_balance[gain], pt[gain])
        taxable = pt[gain] - used
        lcf_balance[gain] -= used
        fcf[gain, i] = pt[gain] - taxable * params.tax

    risk_adj_fcf = fcf * ptr                   # (n_sims, N_YEARS)

    licensor_cf = royalty * ptr
    licensor_cf[:, 0] += params.upfront
    for yr_idx, mil_m in params.milestones.items():
        if 0 < yr_idx < N_YEARS:
            licensor_cf[:, yr_idx] += mil_m * ptr[yr_idx]

    df_ls = (1 + lsws[:, None]) ** -YEAR_INDEX  # (n_sims, N_YEARS)
    df_lr = (1 + lrws[:, None]) ** -YEAR_INDEX

    ls_npvs = np.sum(risk_adj_fcf * df_ls, axis=1)
    lr_npvs = np.sum(licensor_cf  * df_lr, axis=1)

    return ls_npvs, lr_npvs


# ============================================================================
# NPV statistics
# ============================================================================
def npv_stats(arr: np.ndarray) -> Dict:
    p = np.percentile(arr, [5, 10, 25, 50, 75, 90, 95])
    return {
        "mean":     float(np.mean(arr)),
        "std":      float(np.std(arr)),
        "min":      float(np.min(arr)),
        "p5":  p[0], "p10": p[1], "p25": p[2], "p50": p[3],
        "p75": p[4], "p90": p[5], "p95": p[6],
        "max":      float(np.max(arr)),
        "prob_pos": float(np.mean(arr > 0)),
    }


# ============================================================================
# Sensitivity analysis
# ============================================================================
def run_sensitivity(params: ScenarioParams, price: float, base_enpv: float) -> List[Dict]:
    """
    Sweep 6 key variables up / down and measure eNPV impact.

    Returns list of dicts sorted by impact range (largest first).
    """
    sens_vars = {
        "Peak Penetration":  ("peak_pen",    params.peak_pen * 0.4, params.peak_pen * 1.8, False, None),
        "Price / Patient":   ("price_sens",  price * 0.6,          price * 1.5,            True,  None),
        "Ph2→Ph3 PTRS":      ("p2",         params.p2 * 0.6,      params.p2 * 1.5,        False, "p2"),
        "Asset Discount Rate": ("asset_dr", params.asset_discount_rate * 0.7, params.asset_discount_rate * 1.4, True, "asset_discount_rate"),
        "Licensee WACC":     ("lsw_sens",    params.licensee_wacc * 0.7, params.licensee_wacc * 1.4, True, "licensee_wacc"),
        "COGS %":            ("cogs",       params.cogs * 0.6,     params.cogs * 1.5,      False, "cogs"),
        "Tax Rate":          ("tax",        params.tax * 0.6,      params.tax * 1.5,       False, "tax"),
    }

    rows = []
    for label, (_, lo_v, hi_v, is_price_or_dr, attr) in sens_vars.items():
        def _enpv(v, attr=attr, is_price_or_dr=is_price_or_dr):
            p = ScenarioParams(**{f.name: getattr(params, f.name) for f in params.__dataclass_fields__.values()})
            pr_v = float(price)
            if is_price_or_dr:
                if label == "Price / Patient":
                    pr_v = v
                elif label == "Asset Discount Rate":
                    p.asset_discount_rate = v
                elif label == "Licensee WACC":
                    p.licensee_wacc = v
            elif attr is not None:
                setattr(p, attr, v)
            return run_scenario(
                0.002, p.peak_pen if label != "Peak Penetration" else v,
                pr_v, p.asset_discount_rate, p.licensee_wacc, p.licensor_discount_rate,
                p,
            )["licensee_enpv"]

        rows.append({
            "label": label,
            "npv_lo": _enpv(lo_v), "npv_hi": _enpv(hi_v),
            "lo_v": lo_v, "hi_v": hi_v,
        })

    rows.sort(key=lambda r: abs(r["npv_hi"] - r["npv_lo"]), reverse=True)
    return rows
