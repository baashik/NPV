import os

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html

from model_engine import DEFAULT_ASSUMPTIONS, build_dcf_model, format_value
from monte_carlo import run_biotech_monte_carlo, validate_simulation_assumptions

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True, title="Biotech Licensing NPV Model")
server = app.server

SIDEBAR_STYLE = {"width": "260px", "position": "fixed", "left": 0, "top": 0, "bottom": 0, "padding": "22px 16px", "background": "#0f172a", "color": "white", "overflowY": "auto"}
CONTENT_STYLE = {"marginLeft": "280px", "padding": "24px", "background": "#f8fafc", "minHeight": "100vh"}
CARD = "shadow-sm border-0 mb-4"


def money(v):
    return f"${float(v):,.1f}M"


def pct(v):
    return f"{float(v) * 100:.1f}%"


def clean_float(value, fallback=0.0):
    if value is None or value == "":
        return float(fallback)
    return float(value)


def clean_int(value, fallback=0, minimum=None, maximum=None):
    result = int(round(clean_float(value, fallback)))
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


A = DEFAULT_ASSUMPTIONS
RD_TOTAL = A["phase_i_rd"] + A["phase_ii_rd"] + A["phase_iii_rd"]

INPUTS = [
    ("start-year", "Start year", A["start_year"], 1),
    ("forecast-years", "Forecast years", A["forecast_years"], 1),
    ("initial-population", "Initial population (M)", A["initial_population"], 1),
    ("population-growth", "Population growth (%)", A["population_growth"], 0.01),
    ("target-patient-pct", "Target patient %", A["target_patient_pct"], 0.5),
    ("diagnosis-rate", "Diagnosis rate %", A["diagnosis_rate"], 0.5),
    ("treatment-rate", "Treatment rate %", A["treatment_rate"], 0.5),
    ("peak-penetration", "Peak penetration %", A["peak_penetration"], 0.5),
    ("price-per-unit", "Price per unit", A["price_per_unit"], 100),
    ("launch-year", "Launch year", A["launch_year"], 1),
    ("rd-total", "R&D cost total (M)", RD_TOTAL, 1),
    ("cogs-pct", "COGS %", A["cogs_pct"], 0.5),
    ("ga-opex-pct", "G&A / OpEx %", A["ga_opex_pct"], 0.5),
    ("tax-rate", "Tax rate %", A["tax_rate"], 0.5),
    ("phase-i-success", "Phase I success %", A["phase_i_success"], 0.5),
    ("phase-ii-success", "Phase II success %", A["phase_ii_success"], 0.5),
    ("phase-iii-success", "Phase III success %", A["phase_iii_success"], 0.5),
    ("approval-success", "Approval success %", A["approval_success"], 0.5),
    ("upfront", "Upfront (M)", A["upfront_payment"], 0.5),
    ("dev-ms", "Development milestone (M)", A["development_milestone"], 0.5),
    ("reg-ms", "Regulatory milestone (M)", A["regulatory_milestone"], 0.5),
    ("comm-ms", "Commercial milestone (M)", A["commercial_milestone"], 0.5),
    ("royalty-1", "Royalty tier 1 %", A["royalty_tier_1_rate"], 0.5),
    ("royalty-2", "Royalty tier 2 %", A["royalty_tier_2_rate"], 0.5),
    ("royalty-3", "Royalty tier 3 %", A["royalty_tier_3_rate"], 0.5),
    ("asset-rate", "Asset discount rate %", A["asset_discount_rate"], 0.5),
    ("licensee-wacc", "Licensee WACC %", A["licensee_wacc"], 0.5),
    ("licensor-rate", "Licensor discount rate %", A["licensor_discount_rate"], 0.5),
    ("n-sims", "Monte Carlo runs", 1000, 100),
]
INPUT_IDS = [x[0] for x in INPUTS]


def input_col(component_id, label, value, step):
    return dbc.Col([
        dbc.Label(label, className="small fw-bold text-muted"),
        dbc.Input(id=component_id, type="number", value=value, step=step, debounce=False, size="sm"),
    ], lg=3, md=4, sm=6, className="mb-2")


def nav_link(label, target, active=False):
    return dbc.NavLink(label, id=f"nav-{target}", active=active, n_clicks=0, style={"color": "white", "borderRadius": "10px", "marginBottom": "6px"})


def metric_card(title, component_id, subtitle):
    return dbc.Col(dbc.Card(dbc.CardBody([
        html.Div(title, className="small text-muted fw-bold"),
        html.H3(id=component_id, className="fw-bold mb-1"),
        html.Div(subtitle, className="small text-muted"),
    ]), className="shadow-sm border-0 h-100"), lg=4, md=4, sm=12, className="mb-3")


def assumptions_card():
    groups = [
        ("Model period", INPUTS[:2]),
        ("Market and costs", INPUTS[2:14]),
        ("Clinical success", INPUTS[14:18]),
        ("Deal terms", INPUTS[18:25]),
        ("Discount rates", INPUTS[25:]),
    ]
    children = [
        html.H5("1. Assumptions", className="fw-bold"),
        html.Div("Edit inputs, then click Run / Calculate Model. Forecast years controls how many columns the DCF table shows, so the model can be reused for different companies or projects.", className="text-muted mb-3"),
    ]
    for title, items in groups:
        children += [html.H6(title, className="fw-bold mt-3"), dbc.Row([input_col(*item) for item in items])]
    children += [
        html.Hr(),
        dbc.Row([
            dbc.Col(dbc.Button("Run / Calculate Model", id="run-model", color="primary", size="lg", n_clicks=0, className="w-100 fw-bold"), lg=4, md=5, sm=12),
            dbc.Col(html.Div(id="run-status", className="text-muted small pt-2", children="Showing default model. Change inputs and click Run / Calculate Model."), lg=8, md=7, sm=12),
        ], className="align-items-center"),
    ]
    return dbc.Card(dbc.CardBody(children), className=CARD)


def dcf_table_card():
    return dbc.Card(dbc.CardBody([
        html.H5("2. Excel-style DCF table", className="fw-bold"),
        html.Div("The table expands or shrinks based on Forecast Years after you click Run / Calculate Model.", className="text-muted mb-3"),
        dash_table.DataTable(
            id="dcf-table", columns=[], data=[], merge_duplicate_headers=True, page_action="none",
            style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "650px", "width": "100%", "border": "1px solid #cbd5e1"},
            style_cell={"fontFamily": "Menlo, Consolas, monospace", "fontSize": "12px", "padding": "7px 9px", "textAlign": "right", "minWidth": "92px", "width": "92px", "maxWidth": "115px", "whiteSpace": "nowrap", "border": "1px solid #cbd5e1"},
            style_header={"fontWeight": "800", "backgroundColor": "#e2e8f0", "textAlign": "center", "border": "1px solid #cbd5e1"},
            style_cell_conditional=[{"if": {"column_id": "label"}, "textAlign": "left", "fontWeight": "800", "minWidth": "270px", "width": "270px", "maxWidth": "320px", "backgroundColor": "#f8fafc"}],
            style_data_conditional=[],
        ),
    ]), className=CARD)


def output_page(title, det_id, prob_id, chart_id, table_id, subtitle):
    return html.Div([
        html.H3(title, className="fw-bold mb-1"),
        html.Div(subtitle, className="text-muted mb-4"),
        dbc.Row([
            metric_card("Deterministic value", det_id, "Current calculated case"),
            metric_card("Probability > 0", prob_id, "From last Monte Carlo run"),
        ]),
        dbc.Card(dbc.CardBody([
            html.H5("Monte Carlo output", className="fw-bold"),
            dash_table.DataTable(id=table_id, columns=[{"name": "Metric", "id": "metric"}, {"name": "Value", "id": "value"}], data=[], style_cell={"fontSize": "14px", "padding": "8px"}, style_header={"fontWeight": "bold", "backgroundColor": "#f8f9fa"}),
            dcc.Graph(id=chart_id, config={"displayModeBar": False}),
        ]), className=CARD),
    ])


app.layout = html.Div([
    dcc.Store(id="page-store", data="assumptions"),
    html.Div([
        html.H4("NPV Model", className="fw-bold mb-0"),
        html.Div("Flexible licensing model", className="text-white-50 mb-4"),
        dbc.Nav([
            nav_link("1. Assumptions + DCF", "assumptions", True),
            nav_link("2. Asset rNPV", "asset"),
            nav_link("3. Licensee eNPV", "licensee"),
            nav_link("4. Licensor NPV", "licensor"),
        ], vertical=True, pills=True),
    ], style=SIDEBAR_STYLE),
    html.Main([
        html.Div(id="page-assumptions", children=[assumptions_card(), dcf_table_card()]),
        html.Div(id="page-asset", style={"display": "none"}, children=output_page("Asset rNPV", "asset-deterministic", "asset-prob", "asset-chart", "asset-table", "Project value before the licensing economics are split.")),
        html.Div(id="page-licensee", style={"display": "none"}, children=output_page("Licensee eNPV", "licensee-deterministic", "licensee-prob", "licensee-chart", "licensee-table", "Value to the company commercialising the asset.")),
        html.Div(id="page-licensor", style={"display": "none"}, children=output_page("Licensor NPV", "licensor-deterministic", "licensor-prob", "licensor-chart", "licensor-table", "Value to the asset owner from upfront, milestones, and royalties.")),
    ], style=CONTENT_STYLE),
])


@app.callback(
    Output("page-store", "data"),
    Input("nav-assumptions", "n_clicks"), Input("nav-asset", "n_clicks"), Input("nav-licensee", "n_clicks"), Input("nav-licensor", "n_clicks"),
)
def set_page(*_):
    from dash import ctx
    return "assumptions" if not ctx.triggered else ctx.triggered_id.replace("nav-", "")


@app.callback(
    Output("page-assumptions", "style"), Output("page-asset", "style"), Output("page-licensee", "style"), Output("page-licensor", "style"),
    Output("nav-assumptions", "active"), Output("nav-asset", "active"), Output("nav-licensee", "active"), Output("nav-licensor", "active"),
    Input("page-store", "data"),
)
def show_page(page):
    pages = ["assumptions", "asset", "licensee", "licensor"]
    return [{"display": "block" if page == p else "none"} for p in pages] + [page == p for p in pages]


def collect_assumptions(values):
    vals = dict(zip(INPUT_IDS, values))
    a = dict(DEFAULT_ASSUMPTIONS)
    rd_total = clean_float(vals.get("rd-total"), RD_TOTAL)
    forecast_years = clean_int(vals.get("forecast-years"), a["forecast_years"], minimum=1, maximum=40)
    a.update({
        "start_year": clean_int(vals.get("start-year"), a["start_year"], minimum=1900, maximum=2200),
        "forecast_years": forecast_years,
        "initial_population": clean_float(vals.get("initial-population"), a["initial_population"]),
        "population_growth": clean_float(vals.get("population-growth"), a["population_growth"]),
        "target_patient_pct": clean_float(vals.get("target-patient-pct"), a["target_patient_pct"]),
        "diagnosis_rate": clean_float(vals.get("diagnosis-rate"), a["diagnosis_rate"]),
        "treatment_rate": clean_float(vals.get("treatment-rate"), a["treatment_rate"]),
        "peak_penetration": clean_float(vals.get("peak-penetration"), a["peak_penetration"]),
        "price_per_unit": clean_float(vals.get("price-per-unit"), a["price_per_unit"]),
        "launch_year": clean_int(vals.get("launch-year"), a["launch_year"], minimum=1900, maximum=2200),
        "phase_i_rd": rd_total * 0.25,
        "phase_ii_rd": rd_total * 0.30,
        "phase_iii_rd": rd_total * 0.45,
        "cogs_pct": clean_float(vals.get("cogs-pct"), a["cogs_pct"]),
        "ga_opex_pct": clean_float(vals.get("ga-opex-pct"), a["ga_opex_pct"]),
        "tax_rate": clean_float(vals.get("tax-rate"), a["tax_rate"]),
        "phase_i_success": clean_float(vals.get("phase-i-success"), a["phase_i_success"]),
        "phase_ii_success": clean_float(vals.get("phase-ii-success"), a["phase_ii_success"]),
        "phase_iii_success": clean_float(vals.get("phase-iii-success"), a["phase_iii_success"]),
        "approval_success": clean_float(vals.get("approval-success"), a["approval_success"]),
        "upfront_payment": clean_float(vals.get("upfront"), a["upfront_payment"]),
        "development_milestone": clean_float(vals.get("dev-ms"), a["development_milestone"]),
        "regulatory_milestone": clean_float(vals.get("reg-ms"), a["regulatory_milestone"]),
        "commercial_milestone": clean_float(vals.get("comm-ms"), a["commercial_milestone"]),
        "royalty_tier_1_rate": clean_float(vals.get("royalty-1"), a["royalty_tier_1_rate"]),
        "royalty_tier_2_rate": clean_float(vals.get("royalty-2"), a["royalty_tier_2_rate"]),
        "royalty_tier_3_rate": clean_float(vals.get("royalty-3"), a["royalty_tier_3_rate"]),
        "asset_discount_rate": clean_float(vals.get("asset-rate"), a["asset_discount_rate"]),
        "licensee_wacc": clean_float(vals.get("licensee-wacc"), a["licensee_wacc"]),
        "licensor_discount_rate": clean_float(vals.get("licensor-rate"), a["licensor_discount_rate"]),
    })
    n_sims = max(10, min(int(clean_float(vals.get("n-sims"), 1000)), 10000))
    return validate_simulation_assumptions(a), n_sims, forecast_years


def dcf_columns(years):
    return [{"name": "Row Label", "id": "label"}] + [{"name": [f"Year {i + 1}", str(y)], "id": f"y{i}"} for i, y in enumerate(years)]


def dcf_data(model):
    rows = []
    for row in model["table_rows"]:
        item = {"row_key": row.row_key, "label": row.label}
        for i, value in enumerate(row.values):
            item[f"y{i}"] = format_value(value, row.fmt)
        rows.append(item)
    return rows


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


@app.callback(
    Output("run-status", "children"),
    Output("dcf-table", "columns"), Output("dcf-table", "data"), Output("dcf-table", "style_data_conditional"),
    Output("asset-deterministic", "children"), Output("asset-prob", "children"), Output("asset-table", "data"), Output("asset-chart", "figure"),
    Output("licensee-deterministic", "children"), Output("licensee-prob", "children"), Output("licensee-table", "data"), Output("licensee-chart", "figure"),
    Output("licensor-deterministic", "children"), Output("licensor-prob", "children"), Output("licensor-table", "data"), Output("licensor-chart", "figure"),
    Input("run-model", "n_clicks"),
    *[State(component_id, "value") for component_id in INPUT_IDS],
)
def update_outputs(n_clicks, *values):
    assumptions, n_sims, forecast_years = collect_assumptions(values)
    model = build_dcf_model(assumptions, {})
    summary = model["summary"]
    seed = 42 + int(n_clicks or 0)
    mc = run_biotech_monte_carlo(assumptions, n_sims=n_sims, seed=seed)

    dcf_styles = []
    for row_key in ["revenue", "gross_profit", "ebitda", "free_cash_flow", "rnpv", "licensee_enpv", "licensor_npv"]:
        dcf_styles.append({"if": {"filter_query": f"{{row_key}} = '{row_key}'"}, "backgroundColor": "#f1f5f9", "fontWeight": "800"})
    for row_key in ["section_market", "section_pl", "section_ptrs", "section_licensing", "section_valuation"]:
        dcf_styles.append({"if": {"filter_query": f"{{row_key}} = '{row_key}'"}, "backgroundColor": "#dbeafe", "fontWeight": "900", "color": "#111827"})

    asset_table, asset_fig = mc_table_and_chart(mc, "rnpv", "Asset rNPV")
    licensee_table, licensee_fig = mc_table_and_chart(mc, "licensee_npv", "Licensee eNPV")
    licensor_table, licensor_fig = mc_table_and_chart(mc, "licensor_npv", "Licensor NPV")

    status = f"Calculated {forecast_years} forecast years with {n_sims:,} Monte Carlo runs using the latest inputs. Seed #{seed}."
    return (
        status,
        dcf_columns(model["years"]), dcf_data(model), dcf_styles,
        money(summary["rnpv"]), pct(mc["rnpv"].gt(0).mean()), asset_table, asset_fig,
        money(summary["licensee_npv"]), pct(mc["licensee_npv"].gt(0).mean()), licensee_table, licensee_fig,
        money(summary["licensor_npv"]), pct(mc["licensor_npv"].gt(0).mean()), licensor_table, licensor_fig,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
