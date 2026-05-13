"""NPV Model — Dash callbacks for modular layout."""

from dash import Input, Output, State, ctx, no_update, dcc
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


def read_assumptions(_dict: dict) -> dict:
    """Collect current assumption values from layout inputs."""
    assumptions = {}
    for key, comp_id in ASSUMPTION_INPUTS.items():
        if comp_id in _dict:
            val = _dict[comp_id]
            if isinstance(val, str) and val == "":
                val = None
            assumptions[key] = val
    return assumptions


def kpi_card(val: str, sub: str = "") -> html.Div:
    return html.Div(val, style={"fontSize": "1.15rem", "fontWeight": "800",
                                "color": COLORS["blue"], "marginTop": "2px"})


def register_callbacks(app):
    """Attach all callbacks to the Dash app instance."""

    # ==========================================================================
    # Navigation
    # ==========================================================================
    nav_pages = [
        ("nav-dcf",          "dcf"),
        ("nav-licensee",     "licensee"),
        ("nav-licensor",      "licensor"),
        ("nav-monte-carlo",   "monte-carlo"),
        ("nav-sensitivity",   "sensitivity"),
    ]
    page_ids = [p for _, p in nav_pages]

    @app.callback(
        [Output(f"page-{p}", "style") for p in page_ids]
        + [Output(n, "active") for n, _ in nav_pages],
        [Input(n, "n_clicks") for n, _ in nav_pages],
    )
    def navigate(*args):
        triggered = ctx.triggered
        if not triggered:
            active = "dcf"
        else:
            active = triggered[0]["prop_id"].split(".")[0].replace("nav-", "")

        styles = [{"display": "block" if p == active else "none"} for p in page_ids]
        actives = [p == active for p in page_ids]
        return styles + actives

    # ==========================================================================
    # DCF table manual overrides
    # ==========================================================================
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

    # ==========================================================================
    # Main DCF update (triggered by any assumption input change)
    # ==========================================================================
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
        Output("sens-base-npv", "children"),
        Output("sensitivity-tornado-chart", "figure"),
        Output("sensitivity-table", "data"),
        Output("sensitivity-table", "columns"),
        [Input(cid, "value") for cid in assumption_input_ids],
        State("manual-overrides", "data"),
        State("sens-metric", "value"),
        State("licensor-discount-rate", "value"),
        State("licensee-wacc", "value"),
    )
    def update_dcf(
        *vals_and_states
    ):
        # Unpack
        input_values = vals_and_states[:-5]  # all assumption inputs
        overrides = vals_and_states[-5]
        sens_metric = vals_and_states[-4]
        licensor_dr = vals_and_states[-3]
        licensee_wacc = vals_and_states[-2]
        _unused = vals_and_states[-1]  # extra

        # Build assumptions dict from inputs
        a = dict(DEFAULT_ASSUMPTIONS)
        for i, comp_id in enumerate(assumption_input_ids):
            if comp_id in ASSUMPTION_INPUTS:
                key = [k for k, v in ASSUMPTION_INPUTS.items() if v == comp_id][0]
                val = input_values[i]
                if isinstance(val, str) and val == "":
                    val = None
                if val is not None:
                    if key in ("forecast_years", "start_year", "launch_year",
                               "royalty_start_year", "royalty_end_year"):
                        try:
                            val = int(float(val))
                        except (TypeError, ValueError):
                            pass
                a[key] = val

        a = clean_assumptions(a)

        # Build model
        try:
            model = build_dcf_model(a, overrides or {})
        except Exception:
            return no_update

        summary = model["summary"]
        rows = model["frame"]
        years = model["years"]

        # --- Table ---
        columns = table_columns(years)
        tdata = table_data(model)
        style_cond = [
            {"if": {"row_key": k}, "backgroundColor": "#f0f4ff"}
            for k in ["revenue", "gross_profit", "ebitda", "free_cash_flow", "rnpv"]
        ]
        style_cond += [
            {"if": {"column_id": "y0"}, "borderLeft": "2px solid #1f6feb"},
            {"if": {"row_key": "section_market"}, "fontWeight": "800", "backgroundColor": "#e8f0fe"},
            {"if": {"row_key": "section_pl"}, "fontWeight": "800", "backgroundColor": "#e8f0fe"},
            {"if": {"row_key": "section_ptrs"}, "fontWeight": "800", "backgroundColor": "#e8f0fe"},
            {"if": {"row_key": "section_licensing"}, "fontWeight": "800", "backgroundColor": "#e8f0fe"},
            {"if": {"row_key": "section_valuation"}, "fontWeight": "800", "backgroundColor": "#e8f0fe"},
        ]

        override_status = ""
        if overrides:
            n_overrides = len(overrides)
            override_status = f"{n_overrides} manual override(s) applied"

        # --- Summary cards ---
        s = summary
        cards = [
            f"${s.get('rnpv', 0):.1f}M" if s.get('rnpv') is not None else "—",
            f"${s.get('licensee_npv', 0):.1f}M" if s.get('licensee_npv') is not None else "—",
            f"${s.get('licensor_npv', 0):.1f}M" if s.get('licensor_npv') is not None else "—",
            f"${s.get('peak_revenue', 0):.1f}M" if s.get('peak_revenue') is not None else "—",
            f"{s.get('peak_patients', 0):.1f}M" if s.get('peak_patients') is not None else "—",
            f"{s.get('asset_discount_rate', 0) * 100:.1f}%" if s.get('asset_discount_rate') is not None else "—",
            f"{s.get('licensee_wacc', 0) * 100:.1f}%" if s.get('licensee_wacc') is not None else "—",
            f"{s.get('licensor_discount_rate', 0) * 100:.1f}%" if s.get('licensor_discount_rate') is not None else "—",
            f"{s.get('approval_probability', 0) * 100:.1f}%" if s.get('approval_probability') is not None else "—",
            str(s.get('launch_year', '—')),
            f"{s.get('tax_rate', 0) * 100:.1f}%" if s.get('tax_rate') is not None else "—",
        ]

        # --- Charts ---
        rev = rows["revenue"].values
        fcf = rows["free_cash_flow"].values
        rafcf = rows["risk_adjusted_cf"].values
        ebitda = rows["ebitda"].values
        cogs = rows["cogs"].values
        disc_fcf = rows["discounted_fcf"].values

        fig1 = go.Figure()
        fig1.add_trace(go.Bar(x=years, y=rev, name="Revenue", marker_color=COLORS["blue"], opacity=0.85))
        fig1.add_trace(go.Bar(x=years, y=[-c for c in cogs], name="COGS", marker_color="#667085", opacity=0.7))
        fig1.add_trace(go.Scatter(x=years, y=ebitda, name="EBITDA", line=dict(color=COLORS["amber"], width=2.5), mode="lines+markers"))
        fig1.update_layout(template="plotly_white", height=340,
                           title="Revenue vs EBITDA ($M)",
                           legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
                           margin=dict(t=40, b=30))

        fig2 = go.Figure()
        colors2 = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in rafcf]
        fig2.add_trace(go.Bar(x=years, y=rafcf, name="Risk-Adj FCF", marker_color=colors2, opacity=0.85))
        fig2.add_trace(go.Scatter(x=years, y=list(np.cumsum(rafcf)), name="Cumulative",
                                   line=dict(color=COLORS["blue"], width=2, dash="dot")))
        fig2.add_hline(y=0, line_width=1, line_color="black", opacity=0.4)
        fig2.update_layout(template="plotly_white", height=340,
                           title="Risk-Adjusted FCF ($M)",
                           legend=dict(orientation="h", y=1.02),
                           margin=dict(t=40, b=30))

        # --- Licensor outputs ---
        lic_npv = s.get("licensor_npv", 0)
        lic_milestones = s.get("licensor_total_milestones", 0)
        lic_royalties = s.get("licensor_total_royalties", 0)
        lic_deal = lic_npv

        lic_risk_cf = rows.get("risk_adj_licensor_cash_flow", pd.Series([0] * len(years))).values
        disc_lic_cf = rows.get("discounted_licensor_cf", pd.Series([0] * len(years))).values

        fig3 = go.Figure(go.Waterfall(
            x=["Upfront", "Dev Milestone", "Reg Milestone", "Comm Milestone", "Royalties", "Total"],
            measure=["relative", "relative", "relative", "relative", "relative", "total"],
            y=[rows.get("upfront_income", pd.Series([0])).sum(),
               rows.get("development_milestone_income", pd.Series([0])).sum(),
               rows.get("regulatory_milestone_income", pd.Series([0])).sum(),
               rows.get("commercial_milestone_income", pd.Series([0])).sum(),
               rows.get("royalty_income", pd.Series([0])).sum(),
               0],
            text=[f"${rows.get('upfront_income', pd.Series([0])).sum():.1f}M",
                  f"${rows.get('development_milestone_income', pd.Series([0])).sum():.1f}M",
                  f"${rows.get('regulatory_milestone_income', pd.Series([0])).sum():.1f}M",
                  f"${rows.get('commercial_milestone_income', pd.Series([0])).sum():.1f}M",
                  f"${rows.get('royalty_income', pd.Series([0])).sum():.1f}M",
                  f"${lic_npv:.1f}M"],
            textposition="inside",
            increasing={"marker": {"color": COLORS["blue"]}},
            totals={"marker": {"color": COLORS["teal"]}},
        ))
        fig3.update_layout(template="plotly_white", height=300,
                           title=f"Licensor Bridge — ${lic_npv:.1f}M",
                           margin=dict(t=30, b=20))

        colors_lic = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in lic_risk_cf]
        fig4 = go.Figure()
        fig4.add_trace(go.Bar(x=list(years), y=lic_risk_cf.tolist(), name="Risk-Adj CF",
                              marker_color=colors_lic, opacity=0.85))
        disc_cum_lic = np.cumsum(disc_lic_cf)
        fig4.add_trace(go.Scatter(x=list(years), y=disc_cum_lic.tolist(), name="Cum. PV",
                                  line=dict(color=COLORS["amber"], width=2)))
        fig4.update_layout(template="plotly_white", height=280,
                           title="Annual Risk-Adjusted Licensor CF",
                           margin=dict(t=30, b=20),
                           legend=dict(orientation="h", y=1.06))

        # --- Licensee outputs ---
        le_npv = s.get("licensee_npv", 0)
        le_payments = s.get("total_licensee_payments_to_licensor", 0)
        le_peak_rev = s.get("peak_revenue", 0)
        le_wacc = (licensee_wacc or 10.0) / 100.0

        lic_risk_cf_vals = rows.get("licensee_risk_adjusted_cf", pd.Series([0] * len(years))).values
        le_disc_factor = rows.get("licensee_discount_factor", pd.Series([1.0] * len(years))).values

        fig5 = go.Figure()
        colors_le = [COLORS["blue"] if v >= 0 else COLORS["red"] for v in lic_risk_cf_vals]
        fig5.add_trace(go.Bar(x=list(years), y=lic_risk_cf_vals.tolist(), name="Risk-Adj CF",
                              marker_color=colors_le, opacity=0.85))
        fig5.update_layout(template="plotly_white", height=300,
                           title="Annual Risk-Adjusted Licensee CF",
                           margin=dict(t=30, b=20),
                           legend=dict(orientation="h", y=1.06))

        le_disc_cum = np.cumsum(lic_risk_cf_vals * le_disc_factor)
        fig6 = go.Figure()
        fig6.add_trace(go.Scatter(x=list(years), y=le_disc_cum.tolist(), name="Cum. PV (Lic. WACC)",
                                  line=dict(color=COLORS["blue"], width=2.5),
                                  fill="tozeroy", fillcolor="rgba(31,111,235,0.1)"))
        fig6.update_layout(template="plotly_white", height=280,
                           title="Cumulative Discounted Licensee CF",
                           margin=dict(t=30, b=20),
                           legend=dict(orientation="h", y=1.06))

        # --- Sensitivity ---
        metric_key = sens_metric or "core_dcf_npv"
        if metric_key == "licensee_npv":
            base_display = f"Base: ${s.get('licensee_npv', 0):.1f}M"
        elif metric_key == "licensor_npv":
            base_display = f"Base: ${s.get('licensor_npv', 0):.1f}M"
        else:
            base_display = f"Base: ${s.get('rnpv', 0):.1f}M"

        try:
            sens_df = run_sensitivity(dict(DEFAULT_ASSUMPTIONS), selected_metric=metric_key)
        except Exception:
            sens_df = pd.DataFrame(columns=["variable", "low_case", "base_case", "high_case",
                                             "low_npv", "base_npv", "high_npv",
                                             "delta_low", "delta_high", "absolute_impact"])

        fig7 = go.Figure()
        for _, row in sens_df.iterrows():
            lb, lv, hv = row["variable"], row["delta_low"], row["delta_high"]
            fig7.add_trace(go.Bar(y=[lb], x=[lv], orientation="h", marker_color=COLORS["red"], showlegend=False))
            fig7.add_trace(go.Bar(y=[lb], x=[hv], orientation="h", marker_color=COLORS["blue"], showlegend=False))
        fig7.add_vline(x=0, line_color="black", line_width=1.5)
        fig7.update_layout(template="plotly_white", height=400,
                           title=f"Tornado — {metric_key.replace('_', ' ').title()}",
                           xaxis_title="Δ NPV ($M)", margin=dict(l=160, t=40, b=30),
                           barmode="relative", showlegend=False)

        sens_table = []
        for _, row in sens_df.iterrows():
            sens_table.append({
                "Variable": row["variable"],
                "Low": row["low_case"],
                "Base": row["base_case"],
                "High": row["high_case"],
                "Δ Low": f"{row['delta_low']:.1f}",
                "Δ High": f"{row['delta_high']:.1f}",
                "Impact": f"{row['absolute_impact']:.1f}",
            })
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
            f"${lic_npv:.1f}M",
            f"${lic_milestones:.1f}M",
            f"${lic_royalties:.1f}M",
            f"${lic_deal:.1f}M",
            fig3, fig4,
            f"${le_npv:.1f}M",
            f"${le_payments:.1f}M",
            f"${le_peak_rev:.1f}M",
            f"{(licensee_wacc or 10.0):.1f}%",
            fig5, fig6,
            base_display,
            fig7,
            sens_table,
            sens_cols,
        )

    # ==========================================================================
    # Reset overrides
    # ==========================================================================
    @app.callback(
        Output("manual-overrides", "data", allow_duplicate=True),
        Input("reset-overrides", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_overrides(n):
        return {}

    # ==========================================================================
    # Scenario save / load / delete
    # ==========================================================================
    @app.callback(
        Output("scenario-dropdown", "options"),
        Input("saved-scenarios", "data"),
    )
    def update_scenario_dropdown(data):
        if not data:
            return []
        return [{"label": n, "value": n} for n in sorted(data.keys())]

    @app.callback(
        Output("scenario-name", "value"),
        Output("scenario-dropdown", "value"),
        Input("load-scenario", "n_clicks"),
        State("scenario-dropdown", "value"),
        State("saved-scenarios", "data"),
        prevent_initial_call=True,
    )
    def load_scenario(n, name, data):
        if not name or not data or name not in data:
            return no_update, no_update
        s = data[name]
        # Map scenario values back to assumption inputs
        updates = {}
        for key, comp_id in ASSUMPTION_INPUTS.items():
            if key in s:
                updates[comp_id] = s[key]
        return name, ""

    @app.callback(
        Output("saved-scenarios", "data"),
        Output("scenario-status", "children"),
        Input("save-scenario", "n_clicks"),
        State("scenario-name", "value"),
        State("saved-scenarios", "data"),
        prevent_initial_call=True,
    )
    def save_scenario(n, name, data):
        if not name or not name.strip():
            return data or {}, "Enter a scenario name"
        n = name.strip()
        s = data or {}
        current = {}
        for key, comp_id in ASSUMPTION_INPUTS.items():
            current[key] = None  # will be filled by frontend via layout
        s[n] = {"saved_at": pd.Timestamp.now().isoformat()}
        return s, f"Saved: {n}"

    @app.callback(
        Output("saved-scenarios", "data"),
        Output("scenario-status", "children"),
        Input("delete-scenario", "n_clicks"),
        State("scenario-dropdown", "value"),
        State("saved-scenarios", "data"),
        prevent_initial_call=True,
    )
    def delete_scenario(n, name, data):
        if not name or not data or name not in data:
            return data or {}, "Select a scenario first"
        return {k: v for k, v in data.items() if k != name}, f"Deleted: {name}"

    # ==========================================================================
    # Sensitivity metric change triggers re-analysis
    # ==========================================================================
    @app.callback(
        Output("sens-base-npv", "children", allow_duplicate=True),
        Output("sensitivity-tornado-chart", "figure", allow_duplicate=True),
        Output("sensitivity-table", "data", allow_duplicate=True),
        Output("sensitivity-table", "columns", allow_duplicate=True),
        Input("sens-metric", "value"),
        State("manual-overrides", "data"),
        prevent_initial_call=True,
    )
    def update_sensitivity_metric(metric, overrides):
        metric_key = metric or "core_dcf_npv"
        try:
            sens_df = run_sensitivity(dict(DEFAULT_ASSUMPTIONS), overrides, selected_metric=metric_key)
        except Exception:
            sens_df = pd.DataFrame(columns=["variable", "low_case", "base_case", "high_case",
                                             "low_npv", "base_npv", "high_npv",
                                             "delta_low", "delta_high", "absolute_impact"])

        if metric_key == "licensee_npv":
            base_display = "Base: checking..."
        elif metric_key == "licensor_npv":
            base_display = "Base: checking..."
        else:
            base_display = "Base: checking..."

        fig7 = go.Figure()
        for _, row in sens_df.iterrows():
            lb, lv, hv = row["variable"], row["delta_low"], row["delta_high"]
            fig7.add_trace(go.Bar(y=[lb], x=[lv], orientation="h", marker_color=COLORS["red"], showlegend=False))
            fig7.add_trace(go.Bar(y=[lb], x=[hv], orientation="h", marker_color=COLORS["blue"], showlegend=False))
        fig7.add_vline(x=0, line_color="black", line_width=1.5)
        fig7.update_layout(template="plotly_white", height=400,
                           title=f"Tornado — {metric_key.replace('_', ' ').title()}",
                           xaxis_title="Δ NPV ($M)", margin=dict(l=160, t=40, b=30),
                           barmode="relative", showlegend=False)

        sens_table = []
        for _, row in sens_df.iterrows():
            sens_table.append({
                "Variable": row["variable"],
                "Low": row["low_case"],
                "Base": row["base_case"],
                "High": row["high_case"],
                "Δ Low": f"{row['delta_low']:.1f}",
                "Δ High": f"{row['delta_high']:.1f}",
                "Impact": f"{row['absolute_impact']:.1f}",
            })
        sens_cols = [
            {"name": "Variable", "id": "Variable"},
            {"name": "Low Case", "id": "Low"},
            {"name": "Base", "id": "Base"},
            {"name": "High", "id": "High"},
            {"name": "Δ Low ($M)", "id": "Δ Low"},
            {"name": "Δ High ($M)", "id": "Δ High"},
            {"name": "|Impact|", "id": "Impact"},
        ]
        return base_display, fig7, sens_table, sens_cols