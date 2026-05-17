"""NPV Model — Dash callbacks for modular layout."""

from dash import Input, Output, State, ctx
import plotly.graph_objs as go
import numpy as np
import pandas as pd

from model_engine import (
    EDITABLE_ROWS,
    build_dcf_model,
    clean_assumptions,
    parse_user_value,
    row_format_map,
    table_columns,
    table_data,
    run_sensitivity,
    DEFAULT_ASSUMPTIONS,
)
from monte_carlo import run_biotech_monte_carlo, validate_simulation_assumptions
from styles import COLORS


ASSUMPTION_INPUTS = {
    "start_year": "start-year",
    "forecast_years": "forecast-years",
    "currency": "currency",
    "units": "units",
    "initial_population": "initial-population",
    "population_growth": "population-growth",
    "target_patient_pct": "target-patient-pct",
    "diagnosis_rate": "diagnosis-rate",
    "treatment_rate": "treatment-rate",
    "peak_penetration": "peak-penetration",
    "price_per_unit": "price-per-unit",
    "launch_year": "launch-year",
    "cogs_pct": "cogs-pct",
    "ga_opex_pct": "ga-opex-pct",
    "phase_i_rd": "phase-i-rd",
    "phase_ii_rd": "phase-ii-rd",
    "phase_iii_rd": "phase-iii-rd",
    "approval_expense": "approval-expense",
    "pre_marketing": "pre-marketing",
    "tax_rate": "tax-rate",
    "asset_discount_rate": "asset-discount-rate",
    "licensee_wacc": "licensee-wacc",
    "licensor_discount_rate": "licensor-discount-rate",
    "phase_i_success": "phase-i-success",
    "phase_ii_success": "phase-ii-success",
    "phase_iii_success": "phase-iii-success",
    "approval_success": "approval-success",
    "upfront_payment": "upfront-payment",
    "development_milestone": "development-milestone",
    "regulatory_milestone": "regulatory-milestone",
    "commercial_milestone": "commercial-milestone",
    "royalty_tier_1_rate": "royalty-tier-1-rate",
    "royalty_tier_2_rate": "royalty-tier-2-rate",
    "royalty_tier_3_rate": "royalty-tier-3-rate",
    "royalty_tier_1_threshold": "royalty-tier-1-threshold",
    "royalty_tier_2_threshold": "royalty-tier-2-threshold",
    "royalty_start_year": "royalty-start-year",
    "royalty_end_year": "royalty-end-year",
}


def _money(value):
    return f"${value:.1f}M"


def _empty_fig(title=""):
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=300, title=title, margin=dict(t=40, b=30))
    return fig


def register_callbacks(app):
    """Attach all callbacks to the Dash app instance."""

    nav_pages = [
        ("nav-dcf", "dcf"),
        ("nav-licensee", "licensee"),
        ("nav-licensor", "licensor"),
        ("nav-monte-carlo", "monte-carlo"),
        ("nav-sensitivity", "sensitivity"),
    ]
    page_ids = [p for _, p in nav_pages]

    @app.callback(
        [Output(f"page-{p}", "style") for p in page_ids]
        + [Output(n, "active") for n, _ in nav_pages],
        [Input(n, "n_clicks") for n, _ in nav_pages],
    )
    def navigate(*args):
        triggered = ctx.triggered
        active = "dcf" if not triggered else triggered[0]["prop_id"].split(".")[0].replace("nav-", "")
        styles = [{"display": "block" if p == active else "none"} for p in page_ids]
        actives = [p == active for p in page_ids]
        return styles + actives

    @app.callback(
        Output("manual-overrides", "data"),
        Input("dcf-table", "data_timestamp"),
        State("dcf-table", "data"),
        State("manual-overrides", "data"),
        prevent_initial_call=True,
    )
    def apply_overrides(ts, data, overrides):
        if not data or ts is None:
            return overrides or {}
        new_overrides = dict(overrides or {})
        for row in data:
            row_key = row.get("row_key", "")
            if row_key not in EDITABLE_ROWS:
                continue
            for col, raw in row.items():
                if col in ("row_key", "label", "edit", ""):
                    continue
                try:
                    yr_idx = int(col.replace("y", ""))
                    fmt = row_format_map().get(row_key, "number")
                    parsed = parse_user_value(raw, fmt)
                    if parsed is not None:
                        new_overrides[f"{row_key}|{yr_idx}"] = parsed
                except (ValueError, AttributeError):
                    pass
        return new_overrides

    assumption_input_ids = list(ASSUMPTION_INPUTS.values())

    @app.callback(
        Output("dcf-table", "columns"),
        Output("dcf-table", "data"),
        Output("dcf-table", "style_data_conditional"),
        Output("last-table-data", "data"),
        Output("override-status", "children"),
        Output("summary-rnpv", "children"),
        Output("summary-licensee-enpv", "children"),
        Output("summary-licensor-npv", "children"),
        Output("summary-peak-revenue", "children"),
        Output("summary-peak-patients", "children"),
        Output("summary-wacc", "children"),
        Output("summary-licensee-rate", "children"),
        Output("summary-licensor-rate", "children"),
        Output("summary-approval-prob", "children"),
        Output("summary-launch-year", "children"),
        Output("summary-tax-rate", "children"),
        Output("revenue-fcf-chart", "figure"),
        Output("discounted-fcf-chart", "figure"),
        Output("licensor-npv", "children"),
        Output("licensor-total-milestones", "children"),
        Output("licensor-total-royalties", "children"),
        Output("licensor-total-deal-value", "children"),
        Output("licensor-bridge-chart", "figure"),
        Output("licensor-annual-cf-chart", "figure"),
        Output("licensee-npv", "children"),
        Output("licensee-total-payments", "children"),
        Output("licensee-peak-revenue", "children"),
        Output("licensee-wacc-output", "children"),
        Output("licensee-annual-cf-chart", "figure"),
        Output("licensee-cumulative-pv-chart", "figure"),
        Output("mc-mean-rnpv", "children"),
        Output("mc-median-rnpv", "children"),
        Output("mc-p10-p90", "children"),
        Output("mc-prob-positive", "children"),
        Output("mc-histogram-chart", "figure"),
        Output("sens-base-npv", "children"),
        Output("sensitivity-tornado-chart", "figure"),
        Output("sensitivity-table", "data"),
        Output("sensitivity-table", "columns"),
        [Input(cid, "value") for cid in assumption_input_ids],
        State("manual-overrides", "data"),
        State("sens-metric", "value"),
    )
    def update_dcf(*vals_and_states):
        state_count = 2
        input_values = vals_and_states[:-state_count]
        overrides = vals_and_states[-state_count] or {}
        sens_metric = vals_and_states[-state_count + 1]

        a = dict(DEFAULT_ASSUMPTIONS)
        for (key, _), val in zip(ASSUMPTION_INPUTS.items(), input_values):
            if isinstance(val, str) and val == "":
                val = None
            if val is not None:
                if key in ("forecast_years", "start_year", "launch_year", "royalty_start_year", "royalty_end_year"):
                    try:
                        val = int(float(val))
                    except (TypeError, ValueError):
                        pass
                a[key] = val

        a = validate_simulation_assumptions(a)
        model = build_dcf_model(a, overrides)
        summary = model["summary"]
        rows = model["frame"]
        years = model["years"]

        columns = table_columns(years)
        tdata = table_data(model)
        style_cond = []

        for row_key in ["revenue", "gross_profit", "ebitda", "free_cash_flow", "rnpv", "licensee_enpv", "licensor_npv"]:
            style_cond.append({"if": {"filter_query": f"{{row_key}} = '{row_key}'"}, "backgroundColor": "#f8fafc", "fontWeight": "800"})

        for row_key in ["section_market", "section_pl", "section_ptrs", "section_licensing", "section_valuation"]:
            style_cond.append({"if": {"filter_query": f"{{row_key}} = '{row_key}'"}, "backgroundColor": "#e8f0fe", "fontWeight": "900", "color": "#172033"})

        style_cond.append({"if": {"column_id": "y0"}, "borderLeft": "2px solid #1f6feb"})
        override_status = f"{len(overrides)} manual override(s) applied" if overrides else ""

        s = summary
        cards = [
            _money(s.get("rnpv", 0)) if s.get("rnpv") is not None else "—",
            _money(s.get("licensee_npv", 0)) if s.get("licensee_npv") is not None else "—",
            _money(s.get("licensor_npv", 0)) if s.get("licensor_npv") is not None else "—",
            _money(s.get("peak_revenue", 0)) if s.get("peak_revenue") is not None else "—",
            f"{s.get('peak_patients', 0):.1f}M" if s.get("peak_patients") is not None else "—",
            f"{s.get('asset_discount_rate', 0) * 100:.1f}%" if s.get("asset_discount_rate") is not None else "—",
            f"{s.get('licensee_wacc', 0) * 100:.1f}%" if s.get("licensee_wacc") is not None else "—",
            f"{s.get('licensor_discount_rate', 0) * 100:.1f}%" if s.get("licensor_discount_rate") is not None else "—",
            f"{s.get('approval_probability', 0) * 100:.1f}%" if s.get("approval_probability") is not None else "—",
            str(s.get("launch_year", "—")),
            f"{s.get('tax_rate', 0) * 100:.1f}%" if s.get("tax_rate") is not None else "—",
        ]

        rev = rows["revenue"].values
        rafcf = rows["risk_adjusted_cf"].values
        ebitda = rows["ebitda"].values
        cogs = rows["cogs"].values

        fig1 = go.Figure()
        fig1.add_trace(go.Bar(x=years, y=rev, name="Revenue", marker_color=COLORS["blue"], opacity=0.85))
        fig1.add_trace(go.Bar(x=years, y=[-c for c in cogs], name="COGS", marker_color="#667085", opacity=0.7))
        fig1.add_trace(go.Scatter(x=years, y=ebitda, name="EBITDA", line=dict(color=COLORS["amber"], width=2.5), mode="lines+markers"))
        fig1.update_layout(template="plotly_white", height=340, title="Revenue vs EBITDA ($M)", legend=dict(orientation="h", y=1.02, x=1, xanchor="right"), margin=dict(t=40, b=30))

        fig2 = go.Figure()
        colors2 = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in rafcf]
        fig2.add_trace(go.Bar(x=years, y=rafcf, name="Risk-Adj FCF", marker_color=colors2, opacity=0.85))
        fig2.add_trace(go.Scatter(x=years, y=list(np.cumsum(rafcf)), name="Cumulative", line=dict(color=COLORS["blue"], width=2, dash="dot")))
        fig2.add_hline(y=0, line_width=1, line_color="black", opacity=0.4)
        fig2.update_layout(template="plotly_white", height=340, title="Risk-Adjusted FCF ($M)", legend=dict(orientation="h", y=1.02), margin=dict(t=40, b=30))

        lic_npv = s.get("licensor_npv", 0)
        lic_milestones = s.get("licensor_total_milestones", 0)
        lic_royalties = s.get("licensor_total_royalties", 0)
        lic_deal = lic_npv
        lic_risk_cf = rows.get("risk_adj_licensor_cash_flow", pd.Series([0] * len(years))).values
        disc_lic_cf = rows.get("discounted_licensor_cf", pd.Series([0] * len(years))).values

        fig3 = go.Figure(go.Waterfall(
            x=["Upfront", "Dev Milestone", "Reg Milestone", "Comm Milestone", "Royalties", "Total"],
            measure=["relative", "relative", "relative", "relative", "relative", "total"],
            y=[rows.get("upfront_income", pd.Series([0])).sum(), rows.get("development_milestone_income", pd.Series([0])).sum(), rows.get("regulatory_milestone_income", pd.Series([0])).sum(), rows.get("commercial_milestone_income", pd.Series([0])).sum(), rows.get("royalty_income", pd.Series([0])).sum(), 0],
            text=[_money(rows.get("upfront_income", pd.Series([0])).sum()), _money(rows.get("development_milestone_income", pd.Series([0])).sum()), _money(rows.get("regulatory_milestone_income", pd.Series([0])).sum()), _money(rows.get("commercial_milestone_income", pd.Series([0])).sum()), _money(rows.get("royalty_income", pd.Series([0])).sum()), _money(lic_npv)],
            textposition="inside",
            increasing={"marker": {"color": COLORS["blue"]}},
            totals={"marker": {"color": COLORS["teal"]}},
        ))
        fig3.update_layout(template="plotly_white", height=300, title=f"Licensor Bridge — {_money(lic_npv)}", margin=dict(t=30, b=20))

        fig4 = go.Figure()
        colors_lic = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in lic_risk_cf]
        fig4.add_trace(go.Bar(x=list(years), y=lic_risk_cf.tolist(), name="Risk-Adj CF", marker_color=colors_lic, opacity=0.85))
        fig4.add_trace(go.Scatter(x=list(years), y=np.cumsum(disc_lic_cf).tolist(), name="Cum. PV", line=dict(color=COLORS["amber"], width=2)))
        fig4.update_layout(template="plotly_white", height=280, title="Annual Risk-Adjusted Licensor CF", margin=dict(t=30, b=20), legend=dict(orientation="h", y=1.06))

        le_npv = s.get("licensee_npv", 0)
        le_payments = s.get("total_licensee_payments_to_licensor", 0)
        le_peak_rev = s.get("peak_revenue", 0)
        licensee_wacc = a.get("licensee_wacc", 10.0)
        licensee_risk_cf_vals = rows.get("licensee_risk_adjusted_cf", pd.Series([0] * len(years))).values
        le_disc_factor = rows.get("licensee_discount_factor", pd.Series([1.0] * len(years))).values

        fig5 = go.Figure()
        colors_le = [COLORS["blue"] if v >= 0 else COLORS["red"] for v in licensee_risk_cf_vals]
        fig5.add_trace(go.Bar(x=list(years), y=licensee_risk_cf_vals.tolist(), name="Risk-Adj CF", marker_color=colors_le, opacity=0.85))
        fig5.update_layout(template="plotly_white", height=300, title="Annual Risk-Adjusted Licensee CF", margin=dict(t=30, b=20), legend=dict(orientation="h", y=1.06))

        fig6 = go.Figure()
        fig6.add_trace(go.Scatter(x=list(years), y=np.cumsum(licensee_risk_cf_vals * le_disc_factor).tolist(), name="Cum. PV (Lic. WACC)", line=dict(color=COLORS["blue"], width=2.5), fill="tozeroy", fillcolor="rgba(31,111,235,0.1)"))
        fig6.update_layout(template="plotly_white", height=280, title="Cumulative Discounted Licensee CF", margin=dict(t=30, b=20), legend=dict(orientation="h", y=1.06))

        try:
            mc_df = run_biotech_monte_carlo(a, overrides)
            rnpv = mc_df["rnpv"]
            mc_mean = _money(float(rnpv.mean()))
            mc_median = _money(float(rnpv.median()))
            mc_p10_p90 = f"{_money(float(rnpv.quantile(0.10)))} / {_money(float(rnpv.quantile(0.90)))}"
            mc_prob_positive = f"{(rnpv.gt(0).mean() * 100):.1f}%"
            mc_fig = go.Figure()
            mc_fig.add_trace(go.Histogram(x=rnpv, nbinsx=40, name="rNPV", marker_color=COLORS["blue"], opacity=0.85))
            mc_fig.add_vline(x=0, line_color="black", line_width=1, annotation_text="Break-even", annotation_position="top")
            mc_fig.update_layout(template="plotly_white", height=360, title="Monte Carlo rNPV Distribution ($M)", xaxis_title="rNPV ($M)", yaxis_title="Simulation Count", margin=dict(t=40, b=35))
        except Exception:
            mc_mean = mc_median = mc_p10_p90 = mc_prob_positive = "—"
            mc_fig = _empty_fig("Monte Carlo rNPV Distribution ($M)")

        metric_key = sens_metric or "core_dcf_npv"
        if metric_key == "licensee_npv":
            base_display = f"Base: {_money(s.get('licensee_npv', 0))}"
        elif metric_key == "licensor_npv":
            base_display = f"Base: {_money(s.get('licensor_npv', 0))}"
        else:
            base_display = f"Base: {_money(s.get('rnpv', 0))}"

        try:
            sens_df = run_sensitivity(a, overrides, selected_metric=metric_key)
        except Exception:
            sens_df = pd.DataFrame(columns=["variable", "low_case", "base_case", "high_case", "low_npv", "base_npv", "high_npv", "delta_low", "delta_high", "absolute_impact"])

        fig7 = go.Figure()
        for _, row in sens_df.iterrows():
            fig7.add_trace(go.Bar(y=[row["variable"]], x=[row["delta_low"]], orientation="h", marker_color=COLORS["red"], showlegend=False))
            fig7.add_trace(go.Bar(y=[row["variable"]], x=[row["delta_high"]], orientation="h", marker_color=COLORS["blue"], showlegend=False))
        fig7.add_vline(x=0, line_color="black", line_width=1.5)
        fig7.update_layout(template="plotly_white", height=400, title=f"Tornado — {metric_key.replace('_', ' ').title()}", xaxis_title="Δ NPV ($M)", margin=dict(l=160, t=40, b=30), barmode="relative", showlegend=False)

        sens_table = [{"Variable": row["variable"], "Low": row["low_case"], "Base": row["base_case"], "High": row["high_case"], "Δ Low": f"{row['delta_low']:.1f}", "Δ High": f"{row['delta_high']:.1f}", "Impact": f"{row['absolute_impact']:.1f}"} for _, row in sens_df.iterrows()]
        sens_cols = [
            {"name": "Variable", "id": "Variable"},
            {"name": "Low Case", "id": "Low"},
            {"name": "Base", "id": "Base"},
            {"name": "High", "id": "High"},
            {"name": "Δ Low ($M)", "id": "Δ Low"},
            {"name": "Δ High ($M)", "id": "Δ High"},
            {"name": "|Impact|", "id": "Impact"},
        ]

        return (
            columns, tdata, style_cond, tdata, override_status,
            *cards,
            fig1, fig2,
            _money(lic_npv), _money(lic_milestones), _money(lic_royalties), _money(lic_deal),
            fig3, fig4,
            _money(le_npv), _money(le_payments), _money(le_peak_rev), f"{(licensee_wacc or 10.0):.1f}%",
            fig5, fig6,
            mc_mean, mc_median, mc_p10_p90, mc_prob_positive, mc_fig,
            base_display, fig7, sens_table, sens_cols,
        )

    @app.callback(
        Output("manual-overrides", "data", allow_duplicate=True),
        Input("reset-overrides", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_overrides(n):
        return {}
