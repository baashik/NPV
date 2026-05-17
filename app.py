import os

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html

from model_engine import DEFAULT_ASSUMPTIONS, build_dcf_model, table_columns, table_data
from monte_carlo import run_biotech_monte_carlo, validate_simulation_assumptions


app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Biotech Licensing NPV Model",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server

SIDEBAR_STYLE = {
    "width": "260px",
    "position": "fixed",
    "left": 0,
    "top": 0,
    "bottom": 0,
    "padding": "22px 16px",
    "background": "#0f172a",
    "color": "white",
    "overflowY": "auto",
}
CONTENT_STYLE = {
    "marginLeft": "280px",
    "padding": "24px",
    "background": "#f8fafc",
    "minHeight": "100vh",
}
CARD = "shadow-sm border-0 mb-4"


def money(value):
    return f"${float(value):,.1f}M"


def pct(value):
    return f"{float(value) * 100:.1f}%"


def input_col(label, component_id, value, step=1, min_value=None, width=3):
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
        lg=width,
        md=4,
        sm=6,
        className="mb-2",
    )


def metric_card(title, component_id, subtitle=""):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div(title, className="small text-muted fw-bold"),
                html.H3(id=component_id, className="fw-bold mb-1"),
                html.Div(subtitle, className="small text-muted"),
            ]),
            className="shadow-sm border-0 h-100",
        ),
        lg=4,
        md=4,
        sm=12,
        className="mb-3",
    )


def nav_link(label, target, active=False):
    return dbc.NavLink(
        label,
        id=f"nav-{target}",
        active=active,
        n_clicks=0,
        style={"color": "white", "borderRadius": "10px", "marginBottom": "6px"},
    )


def assumptions_card():
    a = DEFAULT_ASSUMPTIONS
    rd_total = a["phase_i_rd"] + a["phase_ii_rd"] + a["phase_iii_rd"]
    return dbc.Card(
        dbc.CardBody([
            html.H5("1. Assumptions", className="fw-bold"),
            html.Div(
                "Enter or change the assumptions, then click Run / Calculate Model at the bottom. The DCF table and Monte Carlo outputs update only when you click the button.",
                className="text-muted mb-3",
            ),
            html.H6("Market and costs", className="fw-bold"),
            dbc.Row([
                input_col("Initial population (M)", "initial-population", a["initial_population"], 1),
                input_col("Population growth (%)", "population-growth", a["population_growth"], 0.01),
                input_col("Target patient %", "target-patient-pct", a["target_patient_pct"], 0.5),
                input_col("Diagnosis rate %", "diagnosis-rate", a["diagnosis_rate"], 0.5),
                input_col("Treatment rate %", "treatment-rate", a["treatment_rate"], 0.5),
                input_col("Peak penetration %", "peak-penetration", a["peak_penetration"], 0.5),
                input_col("Price per unit", "price-per-unit", a["price_per_unit"], 100),
                input_col("Launch year", "launch-year", a["launch_year"], 1),
                input_col("R&D cost total (M)", "rd-total", rd_total, 1),
                input_col("COGS %", "cogs-pct", a["cogs_pct"], 0.5),
                input_col("G&A / OpEx %", "ga-opex-pct", a["ga_opex_pct"], 0.5),
                input_col("Tax rate %", "tax-rate", a["tax_rate"], 0.5),
            ]),
            html.H6("Clinical success", className="fw-bold mt-3"),
            dbc.Row([
                input_col("Phase I success %", "phase-i-success", a["phase_i_success"], 0.5),
                input_col("Phase II success %", "phase-ii-success", a["phase_ii_success"], 0.5),
                input_col("Phase III success %", "phase-iii-success", a["phase_iii_success"], 0.5),
                input_col("Approval success %", "approval-success", a["approval_success"], 0.5),
            ]),
            html.H6("Deal terms", className="fw-bold mt-3"),
            dbc.Row([
                input_col("Upfront (M)", "upfront", a["upfront_payment"], 0.5),
                input_col("Development milestone (M)", "dev-ms", a["development_milestone"], 0.5),
                input_col("Regulatory milestone (M)", "reg-ms", a["regulatory_milestone"], 0.5),
                input_col("Commercial milestone (M)", "comm-ms", a["commercial_milestone"], 0.5),
                input_col("Royalty tier 1 %", "royalty-1", a["royalty_tier_1_rate"], 0.5),
                input_col("Royalty tier 2 %", "royalty-2", a["royalty_tier_2_rate"], 0.5),
                input_col("Royalty tier 3 %", "royalty-3", a["royalty_tier_3_rate"], 0.5),
            ]),
            html.H6("Discount rates", className="fw-bold mt-3"),
            dbc.Row([
                input_col("Asset discount rate %", "asset-rate", a["asset_discount_rate"], 0.5),
                input_col("Licensee WACC %", "licensee-wacc", a["licensee_wacc"], 0.5),
                input_col("Licensor discount rate %", "licensor-rate", a["licensor_discount_rate"], 0.5),
                input_col("Monte Carlo runs", "n-sims", 1000, 100, 10),
            ]),
            html.Hr(),
            dbc.Row([
                dbc.Col(
                    dbc.Button(
                        "Run / Calculate Model",
                        id="run-model",
                        color="primary",
                        size="lg",
                        n_clicks=0,
                        className="w-100 fw-bold",
                    ),
                    lg=4,
                    md=5,
                    sm=12,
                ),
                dbc.Col(
                    html.Div(
                        id="run-status",
                        className="text-muted small pt-2",
                        children="Showing default model. Change inputs and click Run / Calculate Model.",
                    ),
                    lg=8,
                    md=7,
                    sm=12,
                ),
            ], className="align-items-center"),
        ]),
        className=CARD,
    )


def dcf_table_card():
    return dbc.Card(
        dbc.CardBody([
            html.H5("2. Excel-style DCF table", className="fw-bold"),
            html.Div("This table updates after you click Run / Calculate Model.", className="text-muted mb-3"),
            dash_table.DataTable(
                id="dcf-table",
                columns=[],
                data=[],
                merge_duplicate_headers=True,
                page_action="none",
                fixed_rows={"headers": True},
                fixed_columns={"headers": True, "data": 1},
                style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "620px"},
                style_cell={"fontFamily": "Menlo, monospace", "fontSize": "12px", "padding": "7px", "textAlign": "right", "minWidth": "95px", "width": "95px", "maxWidth": "130px", "whiteSpace": "nowrap"},
                style_header={"fontWeight": "bold", "backgroundColor": "#e2e8f0", "textAlign": "center"},
                style_cell_conditional=[{"if": {"column_id": "label"}, "textAlign": "left", "fontWeight": "bold", "minWidth": "260px", "width": "260px", "backgroundColor": "#f8fafc"}],
                style_data_conditional=[],
            ),
        ]),
        className=CARD,
    )


def output_page(title, deterministic_id, prob_id, chart_id, table_id, subtitle):
    return html.Div([
        html.H3(title, className="fw-bold mb-1"),
        html.Div(subtitle, className="text-muted mb-4"),
        dbc.Row([
            metric_card("Deterministic value", deterministic_id, "Current calculated case"),
            metric_card("Probability > 0", prob_id, "From last Monte Carlo run"),
        ]),
        dbc.Card(dbc.CardBody([
            html.H5("Monte Carlo output", className="fw-bold"),
            dash_table.DataTable(
                id=table_id,
                columns=[
                    {"name": "Metric", "id": "metric"},
                    {"name": "Value", "id": "value"},
                ],
                data=[],
                style_cell={"fontFamily": "Arial", "fontSize": "14px", "padding": "8px"},
                style_header={"fontWeight": "bold", "backgroundColor": "#f8f9fa"},
            ),
            dcc.Graph(id=chart_id, config={"displayModeBar": False}),
        ]), className=CARD),
    ])


app.layout = html.Div([
    dcc.Store(id="page-store", data="assumptions"),
    html.Div([
        html.H4("NPV Model", className="fw-bold mb-0"),
        html.Div("Biotech licensing", className="text-white-50 mb-4"),
        dbc.Nav([
            nav_link("1. Assumptions + DCF", "assumptions", True),
            nav_link("2. Asset rNPV", "asset"),
            nav_link("3. Licensee eNPV", "licensee"),
            nav_link("4. Licensor NPV", "licensor"),
        ], vertical=True, pills=True),
    ], style=SIDEBAR_STYLE),
    html.Main([
        html.Div(id="page-assumptions", children=[assumptions_card(), dcf_table_card()]),
        html.Div(id="page-asset", style={"display": "none"}, children=output_page(
            "Asset rNPV", "asset-deterministic", "asset-prob", "asset-chart", "asset-table",
            "Project value before the licensing economics are split between licensee and licensor.",
        )),
        html.Div(id="page-licensee", style={"display": "none"}, children=output_page(
            "Licensee eNPV", "licensee-deterministic", "licensee-prob", "licensee-chart", "licensee-table",
            "Value to the company commercialising the asset after upfront, milestone, and royalty payments.",
        )),
        html.Div(id="page-licensor", style={"display": "none"}, children=output_page(
            "Licensor NPV", "licensor-deterministic", "licensor-prob", "licensor-chart", "licensor-table",
            "Value to the asset owner from upfront, milestones, and royalties.",
        )),
    ], style=CONTENT_STYLE),
])


@app.callback(
    Output("page-store", "data"),
    Input("nav-assumptions", "n_clicks"),
    Input("nav-asset", "n_clicks"),
    Input("nav-licensee", "n_clicks"),
    Input("nav-licensor", "n_clicks"),
)
def set_page(*_):
    from dash import ctx
    if not ctx.triggered:
        return "assumptions"
    return ctx.triggered_id.replace("nav-", "")


@app.callback(
    Output("page-assumptions", "style"),
    Output("page-asset", "style"),
    Output("page-licensee", "style"),
    Output("page-licensor", "style"),
    Output("nav-assumptions", "active"),
    Output("nav-asset", "active"),
    Output("nav-licensee", "active"),
    Output("nav-licensor", "active"),
    Input("page-store", "data"),
)
def show_page(page):
    pages = ["assumptions", "asset", "licensee", "licensor"]
    styles = [{"display": "block" if page == p else "none"} for p in pages]
    actives = [page == p for p in pages]
    return styles + actives


def collect_assumptions(values):
    (
        initial_population, population_growth, target_patient_pct, diagnosis_rate, treatment_rate,
        peak_penetration, price_per_unit, launch_year, rd_total, cogs_pct, ga_opex_pct, tax_rate,
        phase_i_success, phase_ii_success, phase_iii_success, approval_success,
        upfront, dev_ms, reg_ms, comm_ms, royalty_1, royalty_2, royalty_3,
        asset_rate, licensee_wacc, licensor_rate, n_sims,
    ) = values
    a = dict(DEFAULT_ASSUMPTIONS)
    rd_total = float(rd_total or 0)
    a.update({
        "initial_population": float(initial_population or a["initial_population"]),
        "population_growth": float(population_growth or 0),
        "target_patient_pct": float(target_patient_pct or 0),
        "diagnosis_rate": float(diagnosis_rate or 0),
        "treatment_rate": float(treatment_rate or 0),
        "peak_penetration": float(peak_penetration or 0),
        "price_per_unit": float(price_per_unit or 0),
        "launch_year": int(launch_year or a["launch_year"]),
        "phase_i_rd": rd_total * 0.25,
        "phase_ii_rd": rd_total * 0.30,
        "phase_iii_rd": rd_total * 0.45,
        "cogs_pct": float(cogs_pct or 0),
        "ga_opex_pct": float(ga_opex_pct or 0),
        "tax_rate": float(tax_rate or 0),
        "phase_i_success": float(phase_i_success or 0),
        "phase_ii_success": float(phase_ii_success or 0),
        "phase_iii_success": float(phase_iii_success or 0),
        "approval_success": float(approval_success or 0),
        "upfront_payment": float(upfront or 0),
        "development_milestone": float(dev_ms or 0),
        "regulatory_milestone": float(reg_ms or 0),
        "commercial_milestone": float(comm_ms or 0),
        "royalty_tier_1_rate": float(royalty_1 or 0),
        "royalty_tier_2_rate": float(royalty_2 or 0),
        "royalty_tier_3_rate": float(royalty_3 or 0),
        "asset_discount_rate": float(asset_rate or a["asset_discount_rate"]),
        "licensee_wacc": float(licensee_wacc or a["licensee_wacc"]),
        "licensor_discount_rate": float(licensor_rate or a["licensor_discount_rate"]),
    })
    return validate_simulation_assumptions(a), max(10, min(int(n_sims or 1000), 10000))


def mc_table_and_chart(mc, col, title):
    s = mc[col]
    data = [
        {"metric": "Mean", "value": money(s.mean())},
        {"metric": "Median", "value": money(s.median())},
        {"metric": "P10", "value": money(s.quantile(0.10))},
        {"metric": "P90", "value": money(s.quantile(0.90))},
        {"metric": "Probability > 0", "value": pct(s.gt(0).mean())},
    ]
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=s, nbinsx=40, name=title, opacity=0.85))
    fig.add_vline(x=0, line_width=1, line_color="black", annotation_text="Break-even")
    fig.update_layout(template="plotly_white", height=390, title=f"{title} distribution", xaxis_title="NPV ($M)", yaxis_title="Simulation count", margin=dict(t=50, b=40, l=40, r=20))
    return data, fig


states = [
    State("initial-population", "value"), State("population-growth", "value"),
    State("target-patient-pct", "value"), State("diagnosis-rate", "value"),
    State("treatment-rate", "value"), State("peak-penetration", "value"),
    State("price-per-unit", "value"), State("launch-year", "value"),
    State("rd-total", "value"), State("cogs-pct", "value"),
    State("ga-opex-pct", "value"), State("tax-rate", "value"),
    State("phase-i-success", "value"), State("phase-ii-success", "value"),
    State("phase-iii-success", "value"), State("approval-success", "value"),
    State("upfront", "value"), State("dev-ms", "value"), State("reg-ms", "value"),
    State("comm-ms", "value"), State("royalty-1", "value"), State("royalty-2", "value"),
    State("royalty-3", "value"), State("asset-rate", "value"),
    State("licensee-wacc", "value"), State("licensor-rate", "value"), State("n-sims", "value"),
]


@app.callback(
    Output("run-status", "children"),
    Output("dcf-table", "columns"), Output("dcf-table", "data"), Output("dcf-table", "style_data_conditional"),
    Output("asset-deterministic", "children"), Output("asset-prob", "children"), Output("asset-table", "data"), Output("asset-chart", "figure"),
    Output("licensee-deterministic", "children"), Output("licensee-prob", "children"), Output("licensee-table", "data"), Output("licensee-chart", "figure"),
    Output("licensor-deterministic", "children"), Output("licensor-prob", "children"), Output("licensor-table", "data"), Output("licensor-chart", "figure"),
    Input("run-model", "n_clicks"),
    *states,
)
def update_outputs(n_clicks, *values):
    assumptions, n_sims = collect_assumptions(values)
    model = build_dcf_model(assumptions, {})
    summary = model["summary"]
    mc = run_biotech_monte_carlo(assumptions, n_sims=n_sims, seed=42)

    dcf_styles = []
    for row_key in ["revenue", "gross_profit", "ebitda", "free_cash_flow", "rnpv", "licensee_enpv", "licensor_npv"]:
        dcf_styles.append({"if": {"filter_query": f"{{row_key}} = '{row_key}'"}, "backgroundColor": "#f1f5f9", "fontWeight": "bold"})
    for row_key in ["section_market", "section_pl", "section_ptrs", "section_licensing", "section_valuation"]:
        dcf_styles.append({"if": {"filter_query": f"{{row_key}} = '{row_key}'"}, "backgroundColor": "#dbeafe", "fontWeight": "bold"})

    asset_table, asset_fig = mc_table_and_chart(mc, "rnpv", "Asset rNPV")
    licensee_table, licensee_fig = mc_table_and_chart(mc, "licensee_npv", "Licensee eNPV")
    licensor_table, licensor_fig = mc_table_and_chart(mc, "licensor_npv", "Licensor NPV")

    if n_clicks:
        status = f"Calculated with {n_sims:,} Monte Carlo runs. You can now review Asset, Licensee, and Licensor pages."
    else:
        status = f"Showing default model with {n_sims:,} Monte Carlo runs. Change inputs and click Run / Calculate Model."

    return (
        status,
        table_columns(model["years"]), table_data(model), dcf_styles,
        money(summary["rnpv"]), pct(mc["rnpv"].gt(0).mean()), asset_table, asset_fig,
        money(summary["licensee_npv"]), pct(mc["licensee_npv"].gt(0).mean()), licensee_table, licensee_fig,
        money(summary["licensor_npv"]), pct(mc["licensor_npv"].gt(0).mean()), licensor_table, licensor_fig,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
