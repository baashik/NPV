"""Deterministic biotech DCF engine.

The model is intentionally algorithmic rather than copied cell-by-cell from
Excel. Assumptions are the base case; table edits are stored as manual
overrides and then folded back into the yearly forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


SECTION_ROWS = {
    "market_build": "MARKET BUILD",
    "profit_loss": "PROFIT & LOSS",
    "ptrs": "PRTS RISK ADJUSTMENT",
    "licensing": "LICENSING ECONOMICS",
    "valuation": "VALUATION SUMMARY",
}

ROW_DEFS = [
    ("section_market", "MARKET BUILD", "section", False),
    ("total_population", "Total Population (EU)", "number", True),
    ("target_patients", "Target Patient Population (M)", "number", True),
    ("diagnosed_patients", "Diagnosed Patients (M)", "number", True),
    ("treated_patients", "Treated Patients (M)", "number", True),
    ("adoption_pct", "Adoption % of Peak", "pct", True),
    ("market_penetration", "Market Penetration (%)", "pct", True),
    ("patients_treated", "Patients Treated (M)", "number", True),
    ("price_per_unit", "Price Per Unit", "price", True),
    ("section_pl", "PROFIT & LOSS", "section", False),
    ("revenue", "REVENUE (M)", "currency", False),
    ("cogs", "Less: COGS (M)", "currency", True),
    ("gross_profit", "GROSS PROFIT (M)", "currency", False),
    ("phase_i_rd", "Phase I R&D expense (M)", "currency", True),
    ("phase_ii_rd", "Phase II R&D expense (M)", "currency", True),
    ("phase_iii_rd", "Phase III R&D expense (M)", "currency", True),
    ("approval_expense", "Approval expense (M)", "currency", True),
    ("pre_marketing", "Pre-marketing expenses (M)", "currency", True),
    ("ga_opex", "Less: G&A/OpEx (M)", "currency", True),
    ("ebitda", "EBITDA (M)", "currency", False),
    ("tax_rate", "Tax", "pct", True),
    ("accumulated_loss", "Accumulated Loss", "currency", False),
    ("tax_paid", "Tax Paid", "currency", False),
    ("free_cash_flow", "FREE CASH FLOW (M)", "currency", False),
    ("section_ptrs", "PRTS RISK ADJUSTMENT", "section", False),
    ("success_rate", "Success Rate", "pct", True),
    ("cumulative_pos", "Cumulative Probability of Success", "pct", False),
    ("risk_adjusted_cf", "Risk-Adjusted Cash Flow (M)", "currency", False),
    ("discount_factor", "Discount Factor (WACC)", "factor", True),
    ("discounted_fcf", "Discounted FCF – eNPV (M)", "currency", False),
    ("section_licensing", "LICENSING ECONOMICS", "section", False),
    ("royalty_paid", "Royalty Payments (M)", "currency", False),
    ("milestone_payments", "Milestone Payments (M)", "currency", False),
    ("licensee_risk_adjusted_cf", "Licensee Risk-Adjusted CF (M)", "currency", False),
    ("licensor_cash_flow", "Licensor Cash Flow (M)", "currency", False),
    ("section_valuation", "VALUATION SUMMARY", "section", False),
    ("rnpv", "rNPV (risk-adjusted, M)", "currency", False),
    ("licensee_enpv", "Licensee eNPV (M)", "currency", False),
    ("licensor_npv", "Licensor NPV (M)", "currency", False),
    ("discount_rate", "Asset Discount Rate (%)", "pct", True),
]

EDITABLE_ROWS = {row_key for row_key, _, _, editable in ROW_DEFS if editable}
SECTION_KEYS = {row_key for row_key, _, fmt, _ in ROW_DEFS if fmt == "section"}
SUBTOTAL_ROWS = {"revenue", "gross_profit", "ebitda", "free_cash_flow", "rnpv"}


DEFAULT_ASSUMPTIONS = {
    "start_year": 2026,
    "forecast_years": 17,
    "currency": "USD",
    "units": "Millions",
    # Population / Market
    "initial_population": 450.0,
    "population_growth": 0.20,
    "target_patient_pct": 9.00,
    "diagnosis_rate": 80.00,
    "treatment_rate": 50.00,
    "peak_penetration": 5.00,
    "price_per_unit": 15000.0,
    "launch_year": 2033,
    # Costs
    "cogs_pct": 12.00,
    "ga_opex_pct": 1.00,
    "phase_i_rd": 4.0,
    "phase_ii_rd": 5.0,
    "phase_iii_rd": 7.0,
    "approval_expense": 2.0,
    "pre_marketing": 0.0,
    # Tax / Discount Rates
    "tax_rate": 21.00,
    "asset_discount_rate": 12.00,
    "licensee_wacc": 10.00,
    "licensor_discount_rate": 14.00,
    # PTRS
    "phase_i_success": 63.00,
    "phase_ii_success": 30.00,
    "phase_iii_success": 58.00,
    "approval_success": 90.00,
    # License Terms
    "upfront_payment": 2.0,
    "development_milestone": 1.0,
    "regulatory_milestone": 2.0,
    "commercial_milestone": 0.0,
    "royalty_tier_1_rate": 5.00,
    "royalty_tier_2_rate": 7.00,
    "royalty_tier_3_rate": 9.00,
    "royalty_tier_1_threshold": 100.0,
    "royalty_tier_2_threshold": 200.0,
    "royalty_start_year": 2033,
    "royalty_end_year": 2042,
}

ROYALTY_TIER_BREAKS = (100.0, 200.0)


@dataclass(frozen=True)
class TableRow:
    row_key: str
    label: str
    fmt: str
    editable: bool
    values: list[float | str]


def clean_assumptions(values: dict[str, Any]) -> dict[str, Any]:
    clean = {**DEFAULT_ASSUMPTIONS}
    clean.update({k: v for k, v in values.items() if v is not None})
    clean["start_year"] = int(clean["start_year"])
    clean["forecast_years"] = max(1, min(int(clean["forecast_years"]), 30))
    clean["launch_year"] = int(clean["launch_year"])
    clean["royalty_start_year"] = int(clean["royalty_start_year"])
    clean["royalty_end_year"] = int(clean["royalty_end_year"])
    return clean


def _pct(value: float) -> float:
    return float(value) / 100.0


def _discount_factors(rate: float, n_periods: int) -> list[float]:
    return [1 / ((1 + rate) ** (i + 1)) for i in range(n_periods)]


def royalty_tiers_from_assumptions(assumptions: dict[str, Any]) -> list[tuple[float, float, float]]:
    """Build revenue tiers with configurable thresholds."""
    t1 = assumptions.get("royalty_tier_1_threshold", 100.0)
    t2 = assumptions.get("royalty_tier_2_threshold", 200.0)
    return [
        (0.0, t1, _pct(assumptions["royalty_tier_1_rate"])),
        (t1, t2, _pct(assumptions["royalty_tier_2_rate"])),
        (t2, float("inf"), _pct(assumptions["royalty_tier_3_rate"])),
    ]


def compute_tiered_royalty(revenue_m: float, tiers: list[tuple[float, float, float]]) -> float:
    royalty = 0.0
    for lower, upper, rate in tiers:
        if revenue_m <= lower:
            continue
        tier_revenue = min(revenue_m, upper) - lower
        royalty += tier_revenue * rate
    return royalty


def build_milestone_schedule(assumptions: dict[str, Any], years: list[int]) -> list[float]:
    """Spread milestone assumptions over relevant years."""
    schedule = [0.0 for _ in years]
    n = len(years)
    if not years:
        return schedule

    launch_year = assumptions.get("launch_year", 2033)
    start_year = assumptions.get("start_year", 2026)

    # Upfront payment at year 0
    schedule[0] += float(assumptions.get("upfront_payment", 0))

    # Development milestone at year 2 (Ph2 completion)
    dev_milestone = float(assumptions.get("development_milestone", 0))
    if 2 < n:
        schedule[2] += dev_milestone

    # Regulatory milestone at approval year (year 7 / 2033)
    reg_milestone = float(assumptions.get("regulatory_milestone", 0))
    approval_idx = launch_year - start_year
    if approval_idx < n:
        schedule[approval_idx] += reg_milestone

    # Commercial milestone at launch + 1 year
    comm_milestone = float(assumptions.get("commercial_milestone", 0))
    comm_idx = launch_year - start_year + 1
    if comm_idx < n:
        schedule[comm_idx] += comm_milestone

    return schedule


def _override(overrides: dict[str, Any], row_key: str, index: int, default: float) -> float:
    key = f"{row_key}|{index}"
    if key not in (overrides or {}):
        return float(default)
    try:
        return float(overrides[key])
    except (TypeError, ValueError):
        return float(default)


def _adoption_for_year(calendar_year: int, launch_year: int) -> float:
    delta = calendar_year - launch_year
    if delta < 0:
        return 0.0
    if delta == 0:
        return 0.10
    if delta == 1:
        return 0.25
    if delta == 2:
        return 0.45
    if delta == 3:
        return 0.65
    if delta == 4:
        return 0.80
    return 1.00


def _phase_for_index(index: int, calendar_year: int, launch_year: int) -> str:
    if index <= 1:
        return "phase_i"
    if index <= 3:
        return "phase_ii"
    if index <= 6:
        return "phase_iii"
    if index == 7:
        return "approval"
    if calendar_year >= launch_year:
        return "commercial"
    return "pre_commercial"


def build_dcf_model(assumptions: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    a = clean_assumptions(assumptions)
    overrides = overrides or {}

    n = a["forecast_years"]
    years = [a["start_year"] + i for i in range(n)]
    rows: dict[str, list[float]] = {}

    population = []
    for i in range(n):
        base = a["initial_population"] if i == 0 else population[i - 1] * (1 + _pct(a["population_growth"]))
        population.append(_override(overrides, "total_population", i, base))
    rows["total_population"] = population

    target_patients = []
    diagnosed = []
    treated = []
    adoption = []
    penetration = []
    patients_treated = []
    price = []

    for i, year in enumerate(years):
        target = rows["total_population"][i] * _pct(a["target_patient_pct"])
        target = _override(overrides, "target_patients", i, target)
        target_patients.append(target)

        dx = target * _pct(a["diagnosis_rate"])
        dx = _override(overrides, "diagnosed_patients", i, dx)
        diagnosed.append(dx)

        tx = dx * _pct(a["treatment_rate"])
        tx = _override(overrides, "treated_patients", i, tx)
        treated.append(tx)

        adopt = _adoption_for_year(year, a["launch_year"])
        adopt = _override(overrides, "adoption_pct", i, adopt)
        adoption.append(adopt)

        pen = _pct(a["peak_penetration"]) * adopt
        pen = _override(overrides, "market_penetration", i, pen)
        penetration.append(pen)

        pts = tx * pen
        pts = _override(overrides, "patients_treated", i, pts)
        patients_treated.append(pts)

        price.append(_override(overrides, "price_per_unit", i, a["price_per_unit"]))

    rows["target_patients"] = target_patients
    rows["diagnosed_patients"] = diagnosed
    rows["treated_patients"] = treated
    rows["adoption_pct"] = adoption
    rows["market_penetration"] = penetration
    rows["patients_treated"] = patients_treated
    rows["price_per_unit"] = price

    revenue = [patients_treated[i] * price[i] for i in range(n)]
    cogs = [_override(overrides, "cogs", i, revenue[i] * _pct(a["cogs_pct"])) for i in range(n)]
    gross_profit = [revenue[i] - cogs[i] for i in range(n)]

    phase_i_rd = [_override(overrides, "phase_i_rd", i, a["phase_i_rd"] if i in (0, 1) else 0.0) for i in range(n)]
    phase_ii_rd = [_override(overrides, "phase_ii_rd", i, a["phase_ii_rd"] if i in (2, 3) else 0.0) for i in range(n)]
    phase_iii_rd = [_override(overrides, "phase_iii_rd", i, a["phase_iii_rd"] if i in (4, 5, 6) else 0.0) for i in range(n)]
    approval_expense = [_override(overrides, "approval_expense", i, a["approval_expense"] if i == 7 else 0.0) for i in range(n)]
    pre_marketing = [_override(overrides, "pre_marketing", i, a["pre_marketing"] if i in (6, 7) else 0.0) for i in range(n)]
    ga_opex = [_override(overrides, "ga_opex", i, revenue[i] * _pct(a["ga_opex_pct"])) for i in range(n)]

    ebitda = []
    tax_rate = []
    accumulated_loss = []
    tax_paid = []
    free_cash_flow = []
    loss_balance = 0.0

    for i in range(n):
        e = (
            gross_profit[i]
            - phase_i_rd[i]
            - phase_ii_rd[i]
            - phase_iii_rd[i]
            - approval_expense[i]
            - pre_marketing[i]
            - ga_opex[i]
        )
        ebitda.append(e)
        rate = _override(overrides, "tax_rate", i, _pct(a["tax_rate"]))
        tax_rate.append(rate)

        if e < 0:
            loss_balance += abs(e)
            paid = 0.0
        else:
            taxable_after_nol = max(e - loss_balance, 0.0)
            loss_balance = max(loss_balance - e, 0.0)
            paid = taxable_after_nol * rate

        accumulated_loss.append(loss_balance)
        tax_paid.append(paid)
        free_cash_flow.append(e - paid)

    rows.update(
        {
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "phase_i_rd": phase_i_rd,
            "phase_ii_rd": phase_ii_rd,
            "phase_iii_rd": phase_iii_rd,
            "approval_expense": approval_expense,
            "pre_marketing": pre_marketing,
            "ga_opex": ga_opex,
            "ebitda": ebitda,
            "tax_rate": tax_rate,
            "accumulated_loss": accumulated_loss,
            "tax_paid": tax_paid,
            "free_cash_flow": free_cash_flow,
        }
    )

    success_rate = []
    cumulative_pos = []
    p1 = _pct(a["phase_i_success"])
    p2 = _pct(a["phase_ii_success"])
    p3 = _pct(a["phase_iii_success"])
    p4 = _pct(a["approval_success"])

    # Because this is a Phase I asset, post-launch cash flows remain
    # probability-adjusted by cumulative probability of approval.
    cumulative_prob_approval = p1 * p2 * p3 * p4

    for i, year in enumerate(years):
        phase = _phase_for_index(i, year, a["launch_year"])
        if phase == "phase_i":
            sr = _override(overrides, "success_rate", i, p1)
            cpos = sr * p2 * p3 * p4
        elif phase == "phase_ii":
            sr = _override(overrides, "success_rate", i, p2)
            cpos = sr * p3 * p4
        elif phase == "phase_iii":
            sr = _override(overrides, "success_rate", i, p3)
            cpos = sr * p4
        elif phase == "approval":
            sr = _override(overrides, "success_rate", i, p4)
            cpos = sr
        else:
            # Commercial / post-launch years: still probability-adjusted
            # because this is a Phase I asset that hasn't been approved yet
            sr = _override(overrides, "success_rate", i, cumulative_prob_approval)
            cpos = cumulative_prob_approval
        success_rate.append(sr)
        cumulative_pos.append(cpos)

    discount_rate = [_override(overrides, "discount_rate", i, _pct(a["asset_discount_rate"])) for i in range(n)]
    discount_factor = [
        _override(overrides, "discount_factor", i, 1 / ((1 + discount_rate[i]) ** (i + 1)))
        for i in range(n)
    ]
    risk_adjusted_cf = [free_cash_flow[i] * cumulative_pos[i] for i in range(n)]
    discounted_fcf = [risk_adjusted_cf[i] * discount_factor[i] for i in range(n)]
    rnpv_value = float(np.sum(discounted_fcf))

    tiers = royalty_tiers_from_assumptions(a)
    royalty_paid = []
    for i, year in enumerate(years):
        if a["royalty_start_year"] <= year <= a["royalty_end_year"]:
            royalty_paid.append(compute_tiered_royalty(revenue[i], tiers))
        else:
            royalty_paid.append(0.0)

    milestone_payments = build_milestone_schedule(a, years)
    licensee_discount_factor = _discount_factors(_pct(a["licensee_wacc"]), n)
    licensor_discount_factor = _discount_factors(_pct(a["licensor_discount_rate"]), n)

    # ========== LICENSOR CALCULATIONS (mirrors licensee payments) ==========
    # Licensor receipts = mirror of licensee payments (positive cash flows for licensor)
    # Risk-adjustment follows Phase I asset logic:
    # - Upfront (year 0): no probability adjustment (received immediately)
    # - Development milestone (year 2): risk-adjusted by Ph2→Ph3→Approval
    # - Regulatory milestone (approval year): risk-adjusted by full cumulative POS
    # - Commercial milestone (launch+1): risk-adjusted by full cumulative POS
    # - Royalties: risk-adjusted by full cumulative POS

    p2_to_approval = p3 * p4
    full_prob = p1 * p2 * p3 * p4

    upfront_income = [milestone_payments[0]] + [0.0] * (n - 1)
    dev_milestone_income = [0.0] * n
    if 2 < n:
        dev_milestone_income[2] = milestone_payments[2]

    reg_milestone_income = [0.0] * n
    comm_milestone_income = [0.0] * n
    launch_idx = a["launch_year"] - a["start_year"]
    if launch_idx < n:
        reg_milestone_income[launch_idx] = float(a.get("regulatory_milestone", 0))
        if launch_idx + 1 < n:
            comm_milestone_income[launch_idx + 1] = float(a.get("commercial_milestone", 0))

    royalty_income = royalty_paid.copy()

    licensor_cf_raw = [
        upfront_income[i] + dev_milestone_income[i] + reg_milestone_income[i] +
        comm_milestone_income[i] + royalty_income[i]
        for i in range(n)
    ]

    risk_adj_licensor_cf = []
    for i in range(n):
        if i == 0:
            risk_adj = upfront_income[0]
        elif i == 2:
            risk_adj = dev_milestone_income[2] * p2_to_approval
        elif i == launch_idx:
            risk_adj = reg_milestone_income[launch_idx] * full_prob
        elif i == launch_idx + 1 and launch_idx + 1 < n:
            risk_adj = comm_milestone_income[launch_idx + 1] * full_prob
        else:
            risk_adj = (royalty_income[i] + dev_milestone_income[i] +
                       reg_milestone_income[i] + comm_milestone_income[i]) * cumulative_pos[i]
        risk_adj_licensor_cf.append(risk_adj)

    discounted_licensor_cf = [
        risk_adj_licensor_cf[i] * licensor_discount_factor[i]
        for i in range(n)
    ]
    licensor_npv = float(np.sum(discounted_licensor_cf))

    # ========== LICENSEE PAYMENT ARRAYS ==========
    # Negative cash flows for licensee (mirrors positive licensor receipts)
    licensee_upfront_payment = [-upfront_income[i] for i in range(n)]
    licensee_dev_milestone_payment = [-dev_milestone_income[i] for i in range(n)]
    licensee_reg_milestone_payment = [-reg_milestone_income[i] for i in range(n)]
    licensee_comm_milestone_payment = [-comm_milestone_income[i] for i in range(n)]
    licensee_royalty_payment = [-royalty_income[i] for i in range(n)]

    licensee_cash_flow = [
        free_cash_flow[i] - royalty_paid[i] - milestone_payments[i]
        for i in range(n)
    ]
    licensee_risk_adjusted_cf = [
        licensee_cash_flow[i] * cumulative_pos[i]
        for i in range(n)
    ]
    discounted_licensee_cf = [
        licensee_risk_adjusted_cf[i] * licensee_discount_factor[i]
        for i in range(n)
    ]
    licensee_enpv = float(np.sum(discounted_licensee_cf))

    total_licensee_payments_to_licensor = (
        float(np.sum(milestone_payments)) + float(np.sum(royalty_paid))
    )

    licensee_discounted_cf = [
        licensee_risk_adjusted_cf[i] * licensee_discount_factor[i]
        for i in range(n)
    ]
    licensee_enpv = float(np.sum(licensee_discounted_cf))

    rows.update(
        {
            "success_rate": success_rate,
            "cumulative_pos": cumulative_pos,
            "risk_adjusted_cf": risk_adjusted_cf,
            "discount_factor": discount_factor,
            "discounted_fcf": discounted_fcf,
            "royalty_paid": royalty_paid,
            "milestone_payments": milestone_payments,
            # Licensee payment arrays (negative for licensee)
            "licensee_upfront_payment": licensee_upfront_payment,
            "licensee_dev_milestone_payment": licensee_dev_milestone_payment,
            "licensee_reg_milestone_payment": licensee_reg_milestone_payment,
            "licensee_comm_milestone_payment": licensee_comm_milestone_payment,
            "licensee_royalty_payment": licensee_royalty_payment,
            "licensee_cash_flow": licensee_cash_flow,
            "licensee_risk_adjusted_cf": licensee_risk_adjusted_cf,
            "licensee_discounted_cf": discounted_licensee_cf,
            "licensee_discount_factor": licensee_discount_factor,
            # Licensor rows
            "upfront_income": upfront_income,
            "development_milestone_income": dev_milestone_income,
            "regulatory_milestone_income": reg_milestone_income,
            "commercial_milestone_income": comm_milestone_income,
            "royalty_income": royalty_income,
            "licensor_cash_flow": licensor_cf_raw,
            "risk_adj_licensor_cash_flow": risk_adj_licensor_cf,
            "licensor_discount_factor": licensor_discount_factor,
            "discounted_licensor_cf": discounted_licensor_cf,
            "rnpv": [rnpv_value] + [""] * (n - 1),
            "licensee_enpv": [licensee_enpv] + [""] * (n - 1),
            "licensor_npv": [licensor_npv] + [""] * (n - 1),
            "discount_rate": discount_rate,
        }
    )

    table_rows = []
    for row_key, label, fmt, editable in ROW_DEFS:
        values = [""] * n if row_key in SECTION_KEYS else rows[row_key]
        table_rows.append(TableRow(row_key, label, fmt, editable, values))

    frame = pd.DataFrame({row_key: rows[row_key] for row_key in rows if row_key not in SECTION_KEYS})
    frame.insert(0, "year", years)

    summary = {
        "rnpv": rnpv_value,
        "licensee_npv": licensee_enpv,
        "licensee_enpv": licensee_enpv,
        "licensor_npv": licensor_npv,
        "undiscounted_fcf": float(np.sum(free_cash_flow)),
        "licensee_undiscounted_fcf": float(np.sum(licensee_cash_flow)),
        # Licensee totals
        "total_royalties": float(np.sum(royalty_paid)),
        "total_milestones": float(np.sum(milestone_payments)),
        "total_deal_value": float(np.sum(royalty_paid) + float(np.sum(milestone_payments)) + float(a.get("upfront_payment", 0))),
        "total_licensee_payments_to_licensor": total_licensee_payments_to_licensor,
        # Licensor-specific totals
        "licensor_total_upfront": float(a.get("upfront_payment", 0)),
        "licensor_total_dev_milestone": float(a.get("development_milestone", 0)),
        "licensor_total_reg_milestone": float(a.get("regulatory_milestone", 0)),
        "licensor_total_comm_milestone": float(a.get("commercial_milestone", 0)),
        "licensor_total_royalties": float(np.sum(royalty_income)),
        "licensor_total_milestones": float(np.sum(upfront_income) + np.sum(dev_milestone_income) +
                                           np.sum(reg_milestone_income) + np.sum(comm_milestone_income)),
        "peak_revenue": float(np.max(revenue)) if revenue else 0.0,
        "peak_patients": float(np.max(patients_treated)) if patients_treated else 0.0,
        "asset_discount_rate": _pct(a["asset_discount_rate"]),
        "licensee_wacc": _pct(a["licensee_wacc"]),
        "licensor_discount_rate": _pct(a["licensor_discount_rate"]),
        "approval_probability": p1 * p2 * p3 * p4,
        "launch_year": a["launch_year"],
        "tax_rate": _pct(a["tax_rate"]),
    }

    return {
        "assumptions": a,
        "years": years,
        "table_rows": table_rows,
        "frame": frame,
        "summary": summary,
    }


def parse_user_value(value: Any, fmt: str) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace(",", "").replace("$", "").replace("M", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    is_percent = "%" in text
    text = text.replace("%", "")
    try:
        parsed = float(text)
    except ValueError:
        return None
    if negative:
        parsed *= -1
    if fmt == "pct" or is_percent:
        parsed /= 100.0
    return parsed


def format_value(value: Any, fmt: str) -> str:
    if value == "" or value is None:
        return ""
    val = float(value)
    if fmt == "pct":
        return f"{val * 100:.1f}%"
    if fmt == "factor":
        return f"{val:.4f}"
    if fmt == "price":
        return f"{val:,.0f}"
    if fmt == "number":
        return f"{val:,.1f}"
    if fmt == "currency":
        if val < 0:
            return f"({abs(val):,.1f})"
        return f"{val:,.1f}"
    return str(value)


def table_columns(years: list[int]) -> list[dict[str, Any]]:
    columns = [
        {"name": ["", "Row Label"], "id": "label", "editable": False},
        {"name": ["", "Edit"], "id": "edit", "editable": False},
    ]
    columns.extend(
        {"name": [f"Year {i + 1}", str(year)], "id": f"y{i}", "editable": True}
        for i, year in enumerate(years)
    )
    return columns


def table_data(model: dict[str, Any]) -> list[dict[str, Any]]:
    data = []
    for row in model["table_rows"]:
        item = {"row_key": row.row_key, "label": row.label, "edit": "✎" if row.editable else ""}
        for i, value in enumerate(row.values):
            item[f"y{i}"] = format_value(value, row.fmt)
        data.append(item)
    return data


def row_format_map() -> dict[str, str]:
    return {row_key: fmt for row_key, _, fmt, _ in ROW_DEFS}


def run_sensitivity(base_assumptions: dict[str, Any], overrides: dict[str, Any] | None = None,
                    selected_metric: str = "core_dcf_npv") -> pd.DataFrame:
    """
    One-way sensitivity analysis on the deterministic DCF model.
    Tests each variable at low / base / high values and measures NPV impact.

    Parameters
    ----------
    base_assumptions : dict
        Full assumptions dict (as from clean_assumptions).
    overrides : dict, optional
        Manual overrides to pass through.
    selected_metric : str
        Which NPV to compute per scenario.
        Options: "core_dcf_npv" | "licensee_npv" | "licensor_npv"

    Returns
    -------
    pd.DataFrame with columns:
        variable, low_case, base_case, high_case,
        low_npv, base_npv, high_npv,
        delta_low, delta_high, absolute_impact
    """
    base_assumptions = clean_assumptions(base_assumptions)

    SENS_VARS = {
        "Asset Discount Rate": {
            "key": "asset_discount_rate",
            "base": base_assumptions["asset_discount_rate"] / 100,
            "low": base_assumptions["asset_discount_rate"] / 100 - 0.02,
            "high": base_assumptions["asset_discount_rate"] / 100 + 0.02,
            "fmt": "pct",
        },
        "Peak Penetration": {
            "key": "peak_penetration",
            "base": base_assumptions["peak_penetration"] / 100,
            "low": base_assumptions["peak_penetration"] / 100 * 0.75,
            "high": base_assumptions["peak_penetration"] / 100 * 1.25,
            "fmt": "pct",
        },
        "Price Per Unit": {
            "key": "price_per_unit",
            "base": base_assumptions["price_per_unit"],
            "low": base_assumptions["price_per_unit"] * 0.75,
            "high": base_assumptions["price_per_unit"] * 1.25,
            "fmt": "price",
        },
        "Launch Year": {
            "key": "launch_year",
            "base": float(base_assumptions["launch_year"]),
            "low": float(base_assumptions["launch_year"] - 1),
            "high": float(base_assumptions["launch_year"] + 1),
            "fmt": "int",
        },
        "Ph1 → Ph2": {
            "key": "phase_i_success",
            "base": base_assumptions["phase_i_success"] / 100,
            "low": max(0.01, base_assumptions["phase_i_success"] / 100 - 0.20),
            "high": min(1.00, base_assumptions["phase_i_success"] / 100 + 0.20),
            "fmt": "pct",
        },
        "Ph2 → Ph3": {
            "key": "phase_ii_success",
            "base": base_assumptions["phase_ii_success"] / 100,
            "low": max(0.01, base_assumptions["phase_ii_success"] / 100 - 0.20),
            "high": min(1.00, base_assumptions["phase_ii_success"] / 100 + 0.20),
            "fmt": "pct",
        },
        "Ph3 → NDA": {
            "key": "phase_iii_success",
            "base": base_assumptions["phase_iii_success"] / 100,
            "low": max(0.01, base_assumptions["phase_iii_success"] / 100 - 0.20),
            "high": min(1.00, base_assumptions["phase_iii_success"] / 100 + 0.20),
            "fmt": "pct",
        },
        "NDA → Approval": {
            "key": "approval_success",
            "base": base_assumptions["approval_success"] / 100,
            "low": max(0.01, base_assumptions["approval_success"] / 100 - 0.20),
            "high": min(1.00, base_assumptions["approval_success"] / 100 + 0.20),
            "fmt": "pct",
        },
        "COGS %": {
            "key": "cogs_pct",
            "base": base_assumptions["cogs_pct"] / 100,
            "low": base_assumptions["cogs_pct"] / 100 * 0.75,
            "high": base_assumptions["cogs_pct"] / 100 * 1.25,
            "fmt": "pct",
        },
        "Target Patient %": {
            "key": "target_patient_pct",
            "base": base_assumptions["target_patient_pct"] / 100,
            "low": base_assumptions["target_patient_pct"] / 100 * 0.75,
            "high": base_assumptions["target_patient_pct"] / 100 * 1.25,
            "fmt": "pct",
        },
    }

    base_model = build_dcf_model(base_assumptions, overrides)
    if selected_metric == "licensee_npv":
        base_npv = base_model["summary"]["licensee_npv"]
    elif selected_metric == "licensor_npv":
        base_npv = base_model["summary"]["licensor_npv"]
    else:
        base_npv = base_model["summary"]["rnpv"]

    rows = []
    for label, cfg in SENS_VARS.items():
        key = cfg["key"]
        npv_vals = {"low": None, "base": None, "high": None}

        for case_name, case_val in {"low": cfg["low"], "base": cfg["base"], "high": cfg["high"]}.items():
            assumptions = {**base_assumptions, key: case_val}
            model = build_dcf_model(assumptions, overrides)
            if selected_metric == "licensee_npv":
                npv = model["summary"]["licensee_npv"]
            elif selected_metric == "licensor_npv":
                npv = model["summary"]["licensor_npv"]
            else:
                npv = model["summary"]["rnpv"]
            npv_vals[case_name] = npv

        npv_base = npv_vals["base"]
        npv_low = npv_vals["low"]
        npv_high = npv_vals["high"]

        delta_low = npv_low - npv_base
        delta_high = npv_high - npv_base
        abs_impact = max(abs(delta_low), abs(delta_high))

        if cfg["fmt"] == "pct":
            def fmt(v): return f"{v * 100:.1f}%"
        elif cfg["fmt"] == "price":
            def fmt(v): return f"${v:,.0f}"
        elif cfg["fmt"] == "int":
            def fmt(v): return f"{int(v)}"
        else:
            def fmt(v): return f"{v:.2f}"

        rows.append({
            "variable": label,
            "low_case": fmt(cfg["low"]),
            "base_case": fmt(cfg["base"]),
            "high_case": fmt(cfg["high"]),
            "low_npv": npv_low,
            "base_npv": npv_base,
            "high_npv": npv_high,
            "delta_low": delta_low,
            "delta_high": delta_high,
            "absolute_impact": abs_impact,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("absolute_impact", ascending=False).reset_index(drop=True)
    return df
