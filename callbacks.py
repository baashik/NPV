"""Dash callbacks for the modular valuation dashboard."""

from __future__ import annotations

from dash import Input, Output, State, ctx, no_update
import plotly.graph_objs as go

from model_engine import (
    EDITABLE_ROWS,
    SECTION_KEYS,
    SUBTOTAL_ROWS,
    build_dcf_model,
    parse_user_value,
    row_format_map,
    table_columns,
    table_data,
)
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
    ("phase_i_success", "phase-i-success"),
    ("phase_ii_success", "phase-ii-success"),
    ("phase_iii_success", "phase-iii-success"),
    ("approval_success", "approval-success"),
]


def _assumption_states():
    return [Input(component_id, "value") for _, component_id in ASSUMPTION_INPUTS]


def _assumptions_from_values(values):
    return {name: value for (name, _), value in zip(ASSUMPTION_INPUTS, values)}


def _money(value, currency="USD"):
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, "")
    if value < 0:
        return f"({symbol}{abs(value):,.1f}M)"
    return f"{symbol}{value:,.1f}M"


def _pct(value):
    return f"{value * 100:.1f}%"


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

    for idx in [0, 9, 24, 30]:
        styles.append(
            {
                "if": {"row_index": idx},
                "backgroundColor": COLORS["section"],
                "fontWeight": "900",
                "textAlign": "left",
                "color": COLORS["text"],
            }
        )

    for idx in [10, 12, 19, 23, 31]:
        styles.append({"if": {"row_index": idx}, "fontWeight": "900", "backgroundColor": "#f8fafc"})

    return styles


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
        Output("summary-rnpv", "children"),
        Output("summary-fcf", "children"),
        Output("summary-peak-revenue", "children"),
        Output("summary-peak-patients", "children"),
        Output("summary-wacc", "children"),
        Output("summary-approval-prob", "children"),
        Output("summary-launch-year", "children"),
        Output("summary-tax-rate", "children"),
        Output("override-status", "children"),
        Output("revenue-fcf-chart", "figure"),
        Output("discounted-fcf-chart", "figure"),
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

        revenue_fig = go.Figure()
        revenue_fig.add_trace(go.Bar(x=frame["year"], y=frame["revenue"], name="Revenue", marker_color=COLORS["accent"]))
        revenue_fig.add_trace(
            go.Scatter(
                x=frame["year"],
                y=frame["free_cash_flow"],
                name="Free Cash Flow",
                mode="lines+markers",
                line={"color": COLORS["green"], "width": 2.5},
            )
        )
        revenue_fig.add_hline(y=0, line_color="#111827", line_width=1)
        revenue_fig.update_layout(
            template="plotly_white",
            title="Revenue and Free Cash Flow Over Time",
            height=350,
            margin={"l": 46, "r": 18, "t": 52, "b": 36},
            legend={"orientation": "h", "y": 1.08},
            yaxis_title=f"{currency} M",
        )

        discounted_fig = go.Figure()
        colors = [COLORS["green"] if v >= 0 else COLORS["red"] for v in frame["discounted_fcf"]]
        discounted_fig.add_trace(
            go.Bar(
                x=frame["year"],
                y=frame["discounted_fcf"],
                name="Discounted eNPV",
                marker_color=colors,
            )
        )
        discounted_fig.add_trace(
            go.Scatter(
                x=frame["year"],
                y=frame["discounted_fcf"].cumsum(),
                name="Cumulative rNPV",
                mode="lines+markers",
                line={"color": COLORS["amber"], "width": 2.5},
            )
        )
        discounted_fig.add_hline(y=0, line_color="#111827", line_width=1)
        discounted_fig.update_layout(
            template="plotly_white",
            title="Risk-Adjusted Discounted FCF",
            height=350,
            margin={"l": 46, "r": 18, "t": 52, "b": 36},
            legend={"orientation": "h", "y": 1.08},
            yaxis_title=f"{currency} M",
        )

        override_count = len(overrides or {})
        override_text = f"{override_count} manual override{'s' if override_count != 1 else ''} active"
        if override_count == 0:
            override_text = "No manual overrides active"

        return (
            columns,
            data,
            _table_styles(),
            data,
            _money(summary["rnpv"], currency),
            _money(summary["undiscounted_fcf"], currency),
            _money(summary["peak_revenue"], currency),
            f"{summary['peak_patients']:,.2f}M",
            _pct(summary["wacc"]),
            _pct(summary["approval_probability"]),
            str(summary["launch_year"]),
            _pct(summary["tax_rate"]),
            override_text,
            revenue_fig,
            discounted_fig,
        )
