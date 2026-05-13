"""Dash callbacks for the modular valuation dashboard."""

from __future__ import annotations

import json

from dash import Input, Output, State, ctx, dcc, no_update
import plotly.graph_objs as go

from model_engine import (
    DEFAULT_ASSUMPTIONS,
    EDITABLE_ROWS,
    ROW_DEFS,
    SECTION_KEYS,
    SUBTOTAL_ROWS,
    build_dcf_model,
    parse_user_value,
    row_format_map,
    table_columns,
    table_data,
)
from scenario_io import export_payload, make_scenario, scenario_options
from simulation import parse_low_base_high, run_monte_carlo, run_sensitivity
from styles import COLORS


ASSUMPTION_INPUTS = [
    ("start_year", "start-year"),
    ("forecast_years", "forecast-years"),
    ("currency", "currency"),
    ("units", "units"),
    ("initial_population", "initial-population"),
    ("population_growth", "population-growth"),
    ("target_patient_pct", "target-patient-pct"),
    ("diagnosis_rate", "diagnosis-rate"),
    ("treatment_rate", "treatment-rate"),
    ("peak_penetration", "peak-penetration"),
    ("price_per_unit", "price-per-unit"),
    ("launch_year", "launch-year"),
    ("cogs_pct", "cogs-pct"),
    ("ga_opex_pct", "ga-opex-pct"),
    ("phase_i_rd", "phase-i-rd"),
    ("phase_ii_rd", "phase-ii-rd"),
    ("phase_iii_rd", "phase-iii-rd"),
    ("approval_expense", "approval-expense"),
    ("pre_marketing", "pre-marketing"),
    ("tax_rate", "tax-rate"),
    ("wacc", "wacc"),
    ("licensee_discount_rate", "licensee-discount-rate"),
    ("phase_i_success", "phase-i-success"),
    ("phase_ii_success", "phase-ii-success"),
    ("phase_iii_success", "phase-iii-success"),
    ("approval_success", "approval-success"),
    ("upfront_payment", "upfront-payment"),
    ("development_milestones", "development-milestones"),
    ("regulatory_milestones", "regulatory-milestones"),
    ("commercial_milestones", "commercial-milestones"),
    ("royalty_rate", "royalty-rate"),
    ("royalty_tier_1_rate", "royalty-tier-1-rate"),
    ("royalty_tier_2_rate", "royalty-tier-2-rate"),
    ("royalty_tier_3_rate", "royalty-tier-3-rate"),
    ("royalty_start_year", "royalty-start-year"),
    ("royalty_end_year", "royalty-end-year"),
    ("licensor_discount_rate", "licensor-discount-rate"),
]


def _assumption_states():
    return [Input(component_id, "value") for _, component_id in ASSUMPTION_INPUTS]


def _assumption_state_objects():
    return [State(component_id, "value") for _, component_id in ASSUMPTION_INPUTS]


def _assumptions_from_values(values):
    return {name: value for (name, _), value in zip(ASSUMPTION_INPUTS, values)}


def _money(value, currency="USD"):
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, "")
    if value is None:
        return "—"
    value = float(value)
    if value < 0:
        return f"({symbol}{abs(value):,.1f}M)"
    return f"{symbol}{value:,.1f}M"


def _pct(value):
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f}%"


def _table_styles():
    styles = [
        {
            "if": {"column_id": "label"},
            "textAlign": "left",
            "fontWeight": "700",
            "backgroundColor": "#fbfcfd",
            "minWidth": "260px",
            "width": "260px",
            "maxWidth": "320px",
        },
        {
            "if": {"column_id": "edit"},
            "textAlign": "center",
            "color": COLORS["accent"],
            "fontWeight": "800",
            "minWidth": "42px",
            "width": "42px",
            "maxWidth": "42px",
        },
    ]

    for idx, (row_key, _label, fmt, _editable) in enumerate(ROW_DEFS):
        if row_key in SECTION_KEYS or fmt == "section":
            styles.append(
                {
                    "if": {"row_index": idx},
                    "backgroundColor": COLORS["section"],
                    "fontWeight": "900",
                    "textAlign": "left",
                    "color": COLORS["text"],
                }
            )
        elif row_key in SUBTOTAL_ROWS or row_key in {"licensee_enpv", "licensor_npv"}:
            styles.append({"if": {"row_index": idx}, "fontWeight": "900", "backgroundColor": "#f8fafc"})
    return styles


def _revenue_fig(frame, currency):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=frame["year"], y=frame["revenue"], name="Revenue", marker_color=COLORS["accent"]))
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=frame["free_cash_flow"],
            name="Project FCF",
            mode="lines+markers",
            line={"color": COLORS["green"], "width": 2.5},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=frame["licensee_risk_adjusted_cf"],
            name="Licensee Risk-Adjusted CF",
            mode="lines",
            line={"color": COLORS["amber"], "width": 2, "dash": "dot"},
        )
    )
    fig.add_hline(y=0, line_color="#111827", line_width=1)
    fig.update_layout(
        template="plotly_white",
        title="Revenue and Free Cash Flow Over Time",
        height=350,
        margin={"l": 46, "r": 18, "t": 52, "b": 36},
        legend={"orientation": "h", "y": 1.08},
        yaxis_title=f"{currency} M",
    )
    return fig


def _discounted_fig(frame, currency):
    fig = go.Figure()
    colors = [COLORS["green"] if v >= 0 else COLORS["red"] for v in frame["discounted_fcf"]]
    fig.add_trace(go.Bar(x=frame["year"], y=frame["discounted_fcf"], name="Project eNPV", marker_color=colors))
    fig.add_trace(
        go.Scatter(
            x=frame["year"],
            y=frame["licensee_discounted_cf"].cumsum(),
            name="Cumulative Licensee eNPV",
            mode="lines+markers",
            line={"color": COLORS["amber"], "width": 2.5},
        )
    )
    fig.add_hline(y=0, line_color="#111827", line_width=1)
    fig.update_layout(
        template="plotly_white",
        title="Risk-Adjusted Discounted Cash Flow",
        height=350,
        margin={"l": 46, "r": 18, "t": 52, "b": 36},
        legend={"orientation": "h", "y": 1.08},
        yaxis_title=f"{currency} M",
    )
    return fig


def _tornado_fig(rows, currency):
    fig = go.Figure()
    if not rows:
        return fig
    rows = list(reversed(rows[:10]))
    labels = [row["label"] for row in rows]
    base = [row["base"] for row in rows]
    lows = [row["low"] - row["base"] for row in rows]
    highs = [row["high"] - row["base"] for row in rows]
    fig.add_trace(go.Bar(y=labels, x=lows, orientation="h", name="Low case", marker_color=COLORS["red"]))
    fig.add_trace(go.Bar(y=labels, x=highs, orientation="h", name="High case", marker_color=COLORS["accent"]))
    fig.add_vline(x=0, line_color="#111827", line_width=1)
    fig.update_layout(
        template="plotly_white",
        title=f"Tornado Sensitivity vs Base Licensee eNPV ({_money(base[-1], currency)})",
        height=380,
        barmode="overlay",
        margin={"l": 160, "r": 18, "t": 56, "b": 36},
        xaxis_title=f"Change in eNPV ({currency} M)",
        legend={"orientation": "h", "y": 1.08},
    )
    return fig


def _licensor_figs(frame, summary, currency):
    milestone_pv = []
    royalty_pv = []
    for i, row in frame.iterrows():
        pos = 1.0 if i == 0 else row["cumulative_pos"]
        milestone_pv.append(row["milestone_payments"] * pos * row["licensor_discount_factor"])
        royalty_pv.append(row["royalty_paid"] * row["cumulative_pos"] * row["licensor_discount_factor"])

    upfront = milestone_pv[0] if milestone_pv else 0.0
    milestones = sum(milestone_pv[1:])
    royalties = sum(royalty_pv)

    bridge = go.Figure(
        go.Waterfall(
            x=["Upfront", "Milestones", "Royalties", "Licensor NPV"],
            y=[upfront, milestones, royalties, 0],
            measure=["relative", "relative", "relative", "total"],
            text=[_money(upfront, currency), _money(milestones, currency), _money(royalties, currency), _money(summary["licensor_npv"], currency)],
            textposition="inside",
            connector={"line": {"color": COLORS["border"]}},
        )
    )
    bridge.update_layout(
        template="plotly_white",
        title="Licensor NPV Bridge",
        height=330,
        margin={"l": 46, "r": 18, "t": 52, "b": 36},
        yaxis_title=f"{currency} M",
    )

    annual = go.Figure()
    annual.add_trace(go.Bar(x=frame["year"], y=frame["licensor_cash_flow"], name="Risk-Adjusted Cash Flow", marker_color=COLORS["accent"]))
    annual.add_trace(
        go.Scatter(
            x=frame["year"],
            y=frame["licensor_discounted_cf"].cumsum(),
            name="Cumulative PV",
            mode="lines+markers",
            line={"color": COLORS["amber"], "width": 2.5},
        )
    )
    annual.add_hline(y=0, line_color="#111827", line_width=1)
    annual.update_layout(
        template="plotly_white",
        title="Annual Licensor Cash Flow",
        height=330,
        margin={"l": 46, "r": 18, "t": 52, "b": 36},
        legend={"orientation": "h", "y": 1.08},
        yaxis_title=f"{currency} M",
    )
    return bridge, annual


def _mc_histogram(results, currency):
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=results["rnpv"], name="Asset rNPV", marker_color=COLORS["accent"], opacity=0.65, nbinsx=50))
    fig.add_trace(go.Histogram(x=results["licensee_enpv"], name="Licensee eNPV", marker_color=COLORS["green"], opacity=0.55, nbinsx=50))
    fig.add_trace(go.Histogram(x=results["licensor_npv"], name="Licensor NPV", marker_color=COLORS["amber"], opacity=0.50, nbinsx=50))
    fig.add_vline(x=0, line_color="#111827", line_width=1)
    fig.update_layout(
        template="plotly_white",
        title=f"Monte Carlo NPV Distribution ({currency} M)",
        height=360,
        barmode="overlay",
        margin={"l": 46, "r": 18, "t": 52, "b": 36},
        legend={"orientation": "h", "y": 1.08},
    )
    return fig


def register_callbacks(app):
    @app.callback(
        Output("active-page", "data"),
        Input("nav-dcf", "n_clicks"),
        Input("nav-licensor", "n_clicks"),
        Input("nav-monte-carlo", "n_clicks"),
    )
    def choose_page(_dcf, _licensor, _monte_carlo):
        trigger = ctx.triggered_id
        if trigger == "nav-licensor":
            return "licensor"
        if trigger == "nav-monte-carlo":
            return "monte_carlo"
        return "dcf"

    @app.callback(
        Output("nav-dcf", "active"),
        Output("nav-licensor", "active"),
        Output("nav-monte-carlo", "active"),
        Output("page-dcf", "style"),
        Output("page-licensor", "style"),
        Output("page-monte-carlo", "style"),
        Input("active-page", "data"),
    )
    def render_page(active):
        show = {}
        hide = {"display": "none"}
        return (
            active == "dcf",
            active == "licensor",
            active == "monte_carlo",
            show if active == "dcf" else hide,
            show if active == "licensor" else hide,
            show if active == "monte_carlo" else hide,
        )

    @app.callback(
        Output("manual-overrides", "data"),
        Input("dcf-table", "data_timestamp"),
        Input("reset-overrides", "n_clicks"),
        State("dcf-table", "data"),
        State("last-table-data", "data"),
        State("manual-overrides", "data"),
        prevent_initial_call=True,
    )
    def capture_manual_edits(_timestamp, _reset_clicks, current_data, previous_data, overrides):
        if ctx.triggered_id == "reset-overrides":
            return {}
        if not current_data or not previous_data:
            return no_update

        formats = row_format_map()
        updated = dict(overrides or {})
        previous_by_key = {row.get("row_key"): row for row in previous_data}

        for row in current_data:
            row_key = row.get("row_key")
            if row_key not in EDITABLE_ROWS:
                continue
            previous = previous_by_key.get(row_key, {})
            fmt = formats.get(row_key, "number")
            for column_id, value in row.items():
                if not column_id.startswith("y") or value == previous.get(column_id):
                    continue
                try:
                    year_index = int(column_id[1:])
                except ValueError:
                    continue
                parsed = parse_user_value(value, fmt)
                if parsed is None:
                    continue
                updated[f"{row_key}|{year_index}"] = parsed
        return updated

    @app.callback(
        Output("dcf-table", "columns"),
        Output("dcf-table", "data"),
        Output("dcf-table", "style_data_conditional"),
        Output("last-table-data", "data"),
        Output("model-summary-store", "data"),
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
        Output("override-status", "children"),
        Output("revenue-fcf-chart", "figure"),
        Output("discounted-fcf-chart", "figure"),
        Output("tornado-chart", "figure"),
        Output("licensor-npv", "children"),
        Output("licensor-total-milestones", "children"),
        Output("licensor-total-royalties", "children"),
        Output("licensor-total-deal-value", "children"),
        Output("licensor-bridge-chart", "figure"),
        Output("licensor-cashflow-chart", "figure"),
        Input("manual-overrides", "data"),
        *_assumption_states(),
    )
    def update_dcf(overrides, *assumption_values):
        assumptions = _assumptions_from_values(assumption_values)
        model = build_dcf_model(assumptions, overrides)
        data = table_data(model)
        columns = table_columns(model["years"])
        summary = model["summary"]
        currency = model["assumptions"]["currency"]
        frame = model["frame"]
        tornado_rows = run_sensitivity(assumptions, overrides)
        licensor_bridge, licensor_annual = _licensor_figs(frame, summary, currency)

        override_count = len(overrides or {})
        override_text = f"{override_count} manual override{'s' if override_count != 1 else ''} active"
        if override_count == 0:
            override_text = "No manual overrides active"

        model_summary = {
            "assumptions": model["assumptions"],
            "summary": summary,
            "years": model["years"],
        }

        return (
            columns,
            data,
            _table_styles(),
            data,
            model_summary,
            _money(summary["rnpv"], currency),
            _money(summary["licensee_enpv"], currency),
            _money(summary["licensor_npv"], currency),
            _money(summary["peak_revenue"], currency),
            f"{summary['peak_patients']:,.2f}M",
            _pct(summary["wacc"]),
            _pct(summary["licensee_discount_rate"]),
            _pct(summary["licensor_discount_rate"]),
            _pct(summary["approval_probability"]),
            str(summary["launch_year"]),
            _pct(summary["tax_rate"]),
            override_text,
            _revenue_fig(frame, currency),
            _discounted_fig(frame, currency),
            _tornado_fig(tornado_rows, currency),
            _money(summary["licensor_npv"], currency),
            _money(summary["total_milestones"], currency),
            _money(summary["total_royalties"], currency),
            _money(summary["total_deal_value"], currency),
            licensor_bridge,
            licensor_annual,
        )

    @app.callback(
        Output("mc-mean-rnpv", "children"),
        Output("mc-median-rnpv", "children"),
        Output("mc-p10-p90", "children"),
        Output("mc-prob-positive", "children"),
        Output("mc-histogram-chart", "figure"),
        Output("simulation-results-store", "data"),
        Input("active-page", "data"),
        Input("manual-overrides", "data"),
        Input("mc-sims", "value"),
        Input("mc-wacc", "value"),
        Input("mc-peak-pen", "value"),
        Input("mc-price", "value"),
        Input("mc-pos", "value"),
        Input("mc-cost", "value"),
        *_assumption_states(),
    )
    def update_monte_carlo(active_page, overrides, n_sims, mc_wacc, mc_peak_pen, mc_price, mc_pos, mc_cost, *assumption_values):
        if active_page != "monte_carlo":
            return no_update, no_update, no_update, no_update, no_update, no_update
        assumptions = _assumptions_from_values(assumption_values)
        currency = assumptions.get("currency", "USD")
        ranges = {
            "wacc": parse_low_base_high(mc_wacc, (10.0, 12.0, 15.0)),
            "peak_penetration": parse_low_base_high(mc_peak_pen, (6.0, 10.0, 14.0)),
            "price_per_unit": parse_low_base_high(mc_price, (750.0, 1000.0, 1250.0)),
            "probability_success": parse_low_base_high(mc_pos, (10.0, 18.0, 30.0)),
            "development_cost_multiplier": parse_low_base_high(mc_cost, (0.8, 1.0, 1.3)),
        }
        results = run_monte_carlo(assumptions, overrides, n_sims=n_sims, ranges=ranges)
        stats = results["rnpv_stats"]
        return (
            _money(stats["mean"], currency),
            _money(stats["p50"], currency),
            f"{_money(stats['p10'], currency)} / {_money(stats['p90'], currency)}",
            _pct(stats["prob_pos"]),
            _mc_histogram(results, currency),
            {
                "n_sims": results["n_sims"],
                "rnpv_stats": results["rnpv_stats"],
                "licensee_stats": results["licensee_stats"],
                "licensor_stats": results["licensor_stats"],
            },
        )

    @app.callback(
        Output("scenario-dropdown", "options"),
        Input("saved-scenarios", "data"),
    )
    def update_scenario_dropdown(scenarios):
        return scenario_options(scenarios)

    @app.callback(
        Output("saved-scenarios", "data"),
        Output("scenario-status", "children"),
        Input("save-scenario", "n_clicks"),
        Input("delete-scenario", "n_clicks"),
        State("scenario-name", "value"),
        State("scenario-dropdown", "value"),
        State("saved-scenarios", "data"),
        State("manual-overrides", "data"),
        State("model-summary-store", "data"),
        *_assumption_state_objects(),
        prevent_initial_call=True,
    )
    def save_or_delete_scenario(_save_clicks, _delete_clicks, scenario_name, selected_name, scenarios, overrides, model_summary, *assumption_values):
        scenarios = dict(scenarios or {})
        trigger = ctx.triggered_id
        if trigger == "delete-scenario":
            if not selected_name or selected_name not in scenarios:
                return scenarios, "Select a saved scenario to delete."
            scenarios.pop(selected_name, None)
            return scenarios, f"Deleted scenario: {selected_name}"

        assumptions = _assumptions_from_values(assumption_values)
        scenario = make_scenario(scenario_name, assumptions, overrides, (model_summary or {}).get("summary", {}))
        scenarios[scenario["name"]] = scenario
        return scenarios, f"Saved scenario: {scenario['name']}"

    @app.callback(
        [Output(component_id, "value") for _, component_id in ASSUMPTION_INPUTS]
        + [
            Output("manual-overrides", "data", allow_duplicate=True),
            Output("scenario-status", "children", allow_duplicate=True),
        ],
        Input("load-scenario", "n_clicks"),
        State("scenario-dropdown", "value"),
        State("saved-scenarios", "data"),
        prevent_initial_call=True,
    )
    def load_scenario(_clicks, selected_name, scenarios):
        if not selected_name or not scenarios or selected_name not in scenarios:
            return [no_update for _ in ASSUMPTION_INPUTS] + [no_update, "Select a saved scenario to load."]
        scenario = scenarios[selected_name]
        assumptions = scenario.get("assumptions", {})
        values = [assumptions.get(name, DEFAULT_ASSUMPTIONS.get(name)) for name, _ in ASSUMPTION_INPUTS]
        return values + [scenario.get("overrides", {}), f"Loaded scenario: {selected_name}"]

    @app.callback(
        Output("download-export", "data"),
        Input("export-scenario", "n_clicks"),
        State("scenario-name", "value"),
        State("manual-overrides", "data"),
        State("model-summary-store", "data"),
        State("simulation-results-store", "data"),
        *_assumption_state_objects(),
        prevent_initial_call=True,
    )
    def export_scenario(_clicks, scenario_name, overrides, model_summary, simulation_summary, *assumption_values):
        assumptions = _assumptions_from_values(assumption_values)
        payload = export_payload(
            scenario_name,
            assumptions,
            overrides,
            (model_summary or {}).get("summary", {}),
            simulation_summary,
        )
        filename = f"{payload['scenario_name'].replace(' ', '_')}_valuation_export.json"
        return dcc.send_string(json.dumps(payload, indent=2), filename)
