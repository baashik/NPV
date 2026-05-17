import os

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html

from model_engine import DEFAULT_ASSUMPTIONS, build_dcf_model
from monte_carlo import run_biotech_monte_carlo, validate_simulation_assumptions


app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Simple Biotech NPV Model",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server


def money(value):
    return f"${float(value):,.1f}M"


def pct(value):
    return f"{float(value) * 100:.1f}%"


def number_input(label, component_id, value, step=1, min_value=None):
    return dbc.Col(
        [
            dbc.Label(label, className="small fw-bold text-muted"),
            dbc.Input(
                id=component_id,
                type="number",
                value=value,
                step=step,
                min=min_value,
                debounce=True,
                size="sm",
            ),
        ],
        lg=3,
        md=4,
        sm=6,
        className="mb-2",
    )


def kpi_card(title, component_id, subtitle):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                [
                    html.Div(title, className="small text-muted fw-bold"),
                    html.H3(id=component_id, className="mb-1 fw-bold"),
                    html.Div(subtitle, className="small text-muted"),
                ]
            ),
            className="shadow-sm border-0 h-100",
        ),
        lg=4,
        md=4,
        sm=12,
        className="mb-3",
    )


app.layout = dbc.Container(
    [
        html.Div(
            [
                html.H2("Simple Biotech Licensing NPV Model", className="fw-bold mb-1"),
                html.Div(
                    "One DCF engine. Three linked outputs: Asset rNPV, Licensee eNPV, and Licensor NPV. Monte Carlo simulates the same business assumptions and calculates all three together.",
                    className="text-muted",
                ),
            ],
            className="my-4",
        ),
        dbc.Alert(
            "Use percentages as normal percentages: 12 means 12%, 0.20 means 0.20%. Patient counts are in millions; revenue is shown in $M.",
            color="light",
            className="border",
        ),
        dbc.Card(
            dbc.CardBody(
                [
                    html.H5("Core assumptions", className="fw-bold"),
                    dbc.Row(
                        [
                            number_input("Price per unit", "price-per-unit", DEFAULT_ASSUMPTIONS["price_per_unit"], 100),
                            number_input("Peak penetration (%)", "peak-penetration", DEFAULT_ASSUMPTIONS["peak_penetration"], 0.5),
                            number_input("Launch year", "launch-year", DEFAULT_ASSUMPTIONS["launch_year"], 1),
                            number_input("R&D cost total (M)", "rd-total", DEFAULT_ASSUMPTIONS["phase_i_rd"] + DEFAULT_ASSUMPTIONS["phase_ii_rd"] + DEFAULT_ASSUMPTIONS["phase_iii_rd"], 1),
                        ]
                    ),
                    html.H6("Deal terms", className="fw-bold mt-3"),
                    dbc.Row(
                        [
                            number_input("Upfront (M)", "upfront", DEFAULT_ASSUMPTIONS["upfront_payment"], 0.5),
                            number_input("Development milestone (M)", "dev-ms", DEFAULT_ASSUMPTIONS["development_milestone"], 0.5),
                            number_input("Regulatory milestone (M)", "reg-ms", DEFAULT_ASSUMPTIONS["regulatory_milestone"], 0.5),
                            number_input("Commercial milestone (M)", "comm-ms", DEFAULT_ASSUMPTIONS["commercial_milestone"], 0.5),
                            number_input("Royalty tier 1 (%)", "royalty-1", DEFAULT_ASSUMPTIONS["royalty_tier_1_rate"], 0.5),
                            number_input("Royalty tier 2 (%)", "royalty-2", DEFAULT_ASSUMPTIONS["royalty_tier_2_rate"], 0.5),
                            number_input("Royalty tier 3 (%)", "royalty-3", DEFAULT_ASSUMPTIONS["royalty_tier_3_rate"], 0.5),
                        ]
                    ),
                    html.H6("Discount rates", className="fw-bold mt-3"),
                    dbc.Row(
                        [
                            number_input("Asset discount rate (%)", "asset-rate", DEFAULT_ASSUMPTIONS["asset_discount_rate"], 0.5),
                            number_input("Licensee WACC (%)", "licensee-wacc", DEFAULT_ASSUMPTIONS["licensee_wacc"], 0.5),
                            number_input("Licensor discount rate (%)", "licensor-rate", DEFAULT_ASSUMPTIONS["licensor_discount_rate"], 0.5),
                            number_input("Monte Carlo runs", "n-sims", 1000, 100, 10),
                        ]
                    ),
                ]
            ),
            className="shadow-sm border-0 mb-4",
        ),
        dbc.Row(
            [
                kpi_card("Asset rNPV", "asset-rnpv", "Project value before deal split"),
                kpi_card("Licensee eNPV", "licensee-enpv", "Value to the company commercialising the asset"),
                kpi_card("Licensor NPV", "licensor-npv", "Value of upfront, milestones, and royalties"),
            ]
        ),
        dbc.Card(
            dbc.CardBody(
                [
                    html.H5("Simple Monte Carlo simulation", className="fw-bold"),
                    html.Div(
                        "Each run changes the business assumptions once, then calculates Asset rNPV, Licensee eNPV, and Licensor NPV from the same run.",
                        className="text-muted mb-3",
                    ),
                    dash_table.DataTable(
                        id="mc-summary-table",
                        columns=[
                            {"name": "Metric", "id": "metric"},
                            {"name": "Mean", "id": "mean"},
                            {"name": "Median", "id": "median"},
                            {"name": "P10", "id": "p10"},
                            {"name": "P90", "id": "p90"},
                            {"name": "Probability > 0", "id": "prob_positive"},
                        ],
                        data=[],
                        style_cell={"fontFamily": "Arial", "fontSize": "14px", "padding": "8px"},
                        style_header={"fontWeight": "bold", "backgroundColor": "#f8f9fa"},
                    ),
                    dcc.Graph(id="mc-chart", config={"displayModeBar": False}),
                ]
            ),
            className="shadow-sm border-0 mb-4",
        ),
    ],
    fluid=True,
    style={"maxWidth": "1200px"},
)


@app.callback(
    Output("asset-rnpv", "children"),
    Output("licensee-enpv", "children"),
    Output("licensor-npv", "children"),
    Output("mc-summary-table", "data"),
    Output("mc-chart", "figure"),
    Input("price-per-unit", "value"),
    Input("peak-penetration", "value"),
    Input("launch-year", "value"),
    Input("rd-total", "value"),
    Input("upfront", "value"),
    Input("dev-ms", "value"),
    Input("reg-ms", "value"),
    Input("comm-ms", "value"),
    Input("royalty-1", "value"),
    Input("royalty-2", "value"),
    Input("royalty-3", "value"),
    Input("asset-rate", "value"),
    Input("licensee-wacc", "value"),
    Input("licensor-rate", "value"),
    Input("n-sims", "value"),
)
def update_model(
    price_per_unit,
    peak_penetration,
    launch_year,
    rd_total,
    upfront,
    dev_ms,
    reg_ms,
    comm_ms,
    royalty_1,
    royalty_2,
    royalty_3,
    asset_rate,
    licensee_wacc,
    licensor_rate,
    n_sims,
):
    assumptions = dict(DEFAULT_ASSUMPTIONS)

    rd_total = float(rd_total or 0)
    assumptions.update(
        {
            "price_per_unit": float(price_per_unit or DEFAULT_ASSUMPTIONS["price_per_unit"]),
            "peak_penetration": float(peak_penetration or DEFAULT_ASSUMPTIONS["peak_penetration"]),
            "launch_year": int(launch_year or DEFAULT_ASSUMPTIONS["launch_year"]),
            "phase_i_rd": rd_total * 0.25,
            "phase_ii_rd": rd_total * 0.30,
            "phase_iii_rd": rd_total * 0.45,
            "upfront_payment": float(upfront or 0),
            "development_milestone": float(dev_ms or 0),
            "regulatory_milestone": float(reg_ms or 0),
            "commercial_milestone": float(comm_ms or 0),
            "royalty_tier_1_rate": float(royalty_1 or 0),
            "royalty_tier_2_rate": float(royalty_2 or 0),
            "royalty_tier_3_rate": float(royalty_3 or 0),
            "asset_discount_rate": float(asset_rate or DEFAULT_ASSUMPTIONS["asset_discount_rate"]),
            "licensee_wacc": float(licensee_wacc or DEFAULT_ASSUMPTIONS["licensee_wacc"]),
            "licensor_discount_rate": float(licensor_rate or DEFAULT_ASSUMPTIONS["licensor_discount_rate"]),
        }
    )

    assumptions = validate_simulation_assumptions(assumptions)
    model = build_dcf_model(assumptions, {})
    summary = model["summary"]

    n_sims = int(n_sims or 1000)
    n_sims = max(10, min(n_sims, 10000))
    mc = run_biotech_monte_carlo(assumptions, n_sims=n_sims, seed=42)

    metrics = [
        ("Asset rNPV", "rnpv"),
        ("Licensee eNPV", "licensee_npv"),
        ("Licensor NPV", "licensor_npv"),
    ]
    table = []
    for label, col in metrics:
        series = mc[col]
        table.append(
            {
                "metric": label,
                "mean": money(series.mean()),
                "median": money(series.median()),
                "p10": money(series.quantile(0.10)),
                "p90": money(series.quantile(0.90)),
                "prob_positive": pct(series.gt(0).mean()),
            }
        )

    fig = go.Figure()
    fig.add_trace(go.Histogram(x=mc["rnpv"], name="Asset rNPV", opacity=0.65, nbinsx=35))
    fig.add_trace(go.Histogram(x=mc["licensee_npv"], name="Licensee eNPV", opacity=0.65, nbinsx=35))
    fig.add_trace(go.Histogram(x=mc["licensor_npv"], name="Licensor NPV", opacity=0.65, nbinsx=35))
    fig.add_vline(x=0, line_width=1, line_color="black", annotation_text="Break-even")
    fig.update_layout(
        template="plotly_white",
        barmode="overlay",
        height=420,
        title="Monte Carlo NPV Distributions",
        xaxis_title="NPV ($M)",
        yaxis_title="Simulation count",
        legend=dict(orientation="h", y=1.10),
        margin=dict(t=60, b=40, l=40, r=20),
    )

    return (
        money(summary["rnpv"]),
        money(summary["licensee_npv"]),
        money(summary["licensor_npv"]),
        table,
        fig,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
