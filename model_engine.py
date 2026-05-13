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
    ("section_valuation", "VALUATION SUMMARY", "section", False),
    ("rnpv", "rNPV (risk-adjusted, M)", "currency", False),
    ("discount_rate", "Discount Rate (WACC)", "pct", True),
]

EDITABLE_ROWS = {row_key for row_key, _, _, editable in ROW_DEFS if editable}
SECTION_KEYS = {row_key for row_key, _, fmt, _ in ROW_DEFS if fmt == "section"}
SUBTOTAL_ROWS = {"revenue", "gross_profit", "ebitda", "free_cash_flow", "rnpv"}


DEFAULT_ASSUMPTIONS = {
    "start_year": 2026,
    "forecast_years": 17,
    "currency": "USD",
    "units": "Millions",
    "initial_population": 450.0,
    "population_growth": 0.20,
    "target_patient_pct": 1.00,
    "diagnosis_rate": 60.00,
    "treatment_rate": 50.00,
    "peak_penetration": 10.00,
    "price_per_unit": 1000.0,
    "launch_year": 2032,
    "cogs_pct": 20.00,
    "ga_opex_pct": 15.00,
    "phase_i_rd": 10.0,
    "phase_ii_rd": 25.0,
    "phase_iii_rd": 60.0,
    "approval_expense": 10.0,
    "pre_marketing": 15.0,
    "tax_rate": 21.00,
    "wacc": 12.00,
    "phase_i_success": 65.00,
    "phase_ii_success": 40.00,
    "phase_iii_success": 60.00,
    "approval_success": 85.00,
}


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
    return clean


def _pct(value: float) -> float:
    return float(value) / 100.0


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

    for i, year in enumerate(years):
        phase = _phase_for_index(i, year, a["launch_year"])
        if phase == "phase_i":
            sr, cpos = p1, p1 * p2 * p3 * p4
        elif phase == "phase_ii":
            sr, cpos = p2, p2 * p3 * p4
        elif phase == "phase_iii":
            sr, cpos = p3, p3 * p4
        elif phase == "approval":
            sr, cpos = p4, p4
        else:
            sr, cpos = 1.0, 1.0
        success_rate.append(_override(overrides, "success_rate", i, sr))
        cumulative_pos.append(cpos)

    discount_rate = [_override(overrides, "discount_rate", i, _pct(a["wacc"])) for i in range(n)]
    discount_factor = [
        _override(overrides, "discount_factor", i, 1 / ((1 + discount_rate[i]) ** (i + 1)))
        for i in range(n)
    ]
    risk_adjusted_cf = [free_cash_flow[i] * cumulative_pos[i] for i in range(n)]
    discounted_fcf = [risk_adjusted_cf[i] * discount_factor[i] for i in range(n)]
    rnpv_value = float(np.sum(discounted_fcf))

    rows.update(
        {
            "success_rate": success_rate,
            "cumulative_pos": cumulative_pos,
            "risk_adjusted_cf": risk_adjusted_cf,
            "discount_factor": discount_factor,
            "discounted_fcf": discounted_fcf,
            "rnpv": [rnpv_value] + [""] * (n - 1),
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
        "undiscounted_fcf": float(np.sum(free_cash_flow)),
        "peak_revenue": float(np.max(revenue)) if revenue else 0.0,
        "peak_patients": float(np.max(patients_treated)) if patients_treated else 0.0,
        "wacc": _pct(a["wacc"]),
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
