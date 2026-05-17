"""Dash layout for the modular valuation dashboard."""

from __future__ import annotations

from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc

from model_engine import DEFAULT_ASSUMPTIONS
from styles import CARD, COLORS, CONTENT, PAGE, SIDEBAR, SMALL_LABEL


def field(label, component):
    return html.Div([dbc.Label(label, style=SMALL_LABEL), component], style={"marginBottom": "10px"})


def number_input(component_id, value, step=1, min_value=None):
    return dbc.Input(id=component_id, type="number", value=value, step=step, min=min_value, size="sm")


def section_title(title):
    return html.Div(
        title,
        style={
            "fontSize": "0.75rem",
            "fontWeight": "800",
            "letterSpacing": "0.08em",
            "color": COLORS["muted"],
            "margin": "6px 0 10px",
            "textTransform": "uppercase",
        },
    )


def assumption_panel():
    a = DEFAULT_ASSUMPTIONS
    return html.Div(
        [
            html.Div(
                [
                    html.H5("Assumptions", style={"fontWeight": "800", "marginBottom": "4px"}),
                    html.Div(
                        "Inputs update the DCF, sensitivity, and Monte Carlo outputs automatically. Table edits override individual forecast cells.",
                        style={"color": COLORS["muted"], "fontSize": "0.88rem"},
                    ),
                    html.Div(
                        "Unit note: patient counts are in millions. Revenue is shown in $M, so Patients Treated (M) × Price Per Unit = Revenue ($M).",
                        style={"color": COLORS["muted"], "fontSize": "0.82rem", "marginTop": "6px"},
                    ),
                ],
                style={"marginBottom": "14px"},
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            section_title("General"),
                            field("Start Year", number_input("start-year", a["start_year"], 1)),
                            field("Forecast Years", number_input("forecast-years", a["forecast_years"], 1, 1)),
                            field("Currency", dcc.Dropdown(id="currency", value=a["currency"],
                                                           options=[{"label": c, "value": c} for c in ["USD", "EUR", "GBP"]],
                                                           clearable=False, style={"fontSize": "0.86rem"})),
                            field("Units", dcc.Dropdown(id="units", value=a["units"],
                                                        options=[{"label": "Millions", "value": "Millions"}],
                                                        clearable=False, style={"fontSize": "0.86rem"})),
                        ],
                        lg=3, md=6,
                    ),
                    dbc.Col(
                        [
                            section_title("Population / Market"),
                            field("Initial Total Population EU (M)", number_input("initial-population", a["initial_population"], 1)),
                            field("Population Growth Rate", number_input("population-growth", a["population_growth"], 0.01)),
                            field("Target Patient Population %", number_input("target-patient-pct", a["target_patient_pct"], 0.1)),
                            field("Diagnosis Rate", number_input("diagnosis-rate", a["diagnosis_rate"], 0.5)),
                            field("Treatment Rate", number_input("treatment-rate", a["treatment_rate"], 0.5)),
                            field("Peak Market Penetration %", number_input("peak-penetration", a["peak_penetration"], 0.5)),
                            field("Price Per Unit", number_input("price-per-unit", a["price_per_unit"], 50)),
                        ],
                        lg=3, md=6,
                    ),
                    dbc.Col(
                        [
                            section_title("Revenue Ramp / Costs"),
                            field("Launch Year", number_input("launch-year", a["launch_year"], 1)),
                            field("COGS %", number_input("cogs-pct", a["cogs_pct"], 0.5)),
                            field("G&A / OpEx %", number_input("ga-opex-pct", a["ga_opex_pct"], 0.5)),
                            field("Phase I R&D Expense (M)", number_input("phase-i-rd", a["phase_i_rd"], 1)),
                            field("Phase II R&D Expense (M)", number_input("phase-ii-rd", a["phase_ii_rd"], 1)),
                            field("Phase III R&D Expense (M)", number_input("phase-iii-rd", a["phase_iii_rd"], 1)),
                            field("Approval Expense (M)", number_input("approval-expense", a["approval_expense"], 1)),
                            field("Pre-marketing Expense (M)", number_input("pre-marketing", a["pre_marketing"], 1)),
                        ],
                        lg=3, md=6,
                    ),
                    dbc.Col(
                        [
                            section_title("Tax / Discount"),
                            field("Tax Rate (%)", number_input("tax-rate", a["tax_rate"], 0.5)),
                            field("Asset Discount Rate (%)", number_input("asset-discount-rate", a["asset_discount_rate"], 0.5)),
                            field("Licensee WACC (%)", number_input("licensee-wacc", a["licensee_wacc"], 0.5)),
                            field("Licensor Discount Rate (%)", number_input("licensor-discount-rate", a["licensor_discount_rate"], 0.5)),
                            section_title("Phase Success Rates"),
                            field("Ph1 to Ph2 (%)", number_input("phase-i-success", a["phase_i_success"], 0.5)),
                            field("Ph2 to Ph3 (%)", number_input("phase-ii-success", a["phase_ii_success"], 0.5)),
                            field("Ph3 to NDA (%)", number_input("phase-iii-success", a["phase_iii_success"], 0.5)),
                            field("NDA to Approval (%)", number_input("approval-success", a["approval_success"], 0.5)),
                        ],
                        lg=3, md=6,
                    ),
                    dbc.Col(
                        [
                            section_title("License Terms"),
                            field("Upfront Payment (M)", number_input("upfront-payment", a["upfront_payment"], 0.5)),
                            field("Development Milestone (M)", number_input("development-milestone", a["development_milestone"], 0.5)),
                            field("Regulatory Milestone (M)", number_input("regulatory-milestone", a["regulatory_milestone"], 0.5)),
                            field("Commercial Milestone (M)", number_input("commercial-milestone", a["commercial_milestone"], 0.5)),
                            section_title("Royalty Tiers"),
                            field("Royalty Tier 1 Rate %", number_input("royalty-tier-1-rate", a["royalty_tier_1_rate"], 0.5)),
                            field("Royalty Tier 2 Rate %", number_input("royalty-tier-2-rate", a["royalty_tier_2_rate"], 0.5)),
                            field("Royalty Tier 3 Rate %", number_input("royalty-tier-3-rate", a["royalty_tier_3_rate"], 0.5)),
                            field("Tier 1 Threshold (M)", number_input("royalty-tier-1-threshold", a["royalty_tier_1_threshold"], 10)),
                            field("Tier 2 Threshold (M)", number_input("royalty-tier-2-threshold", a["royalty_tier_2_threshold"], 10)),
                            section_title("Royalty Period"),
                            field("Royalty Start Year", number_input("royalty-start-year", a["royalty_start_year"], 1)),
                            field("Royalty End Year", number_input("royalty-end-year", a["royalty_end_year"], 1)),
                        ],
                        lg=3, md=6,
                    ),
                ],
                className="g-3",
            ),
        ],
        style={**CARD, "padding": "18px", "marginBottom": "18px"},
    )


def summary_cards():
    cards = [
        ("Asset rNPV", "summary-rnpv"),
        ("Licensee eNPV", "summary-licensee-enpv"),
        ("Licensor NPV", "summary-licensor-npv"),
        ("Peak Revenue", "summary-peak-revenue"),
        ("Peak Patients", "summary-peak-patients"),
        ("Asset WACC", "summary-wacc"),
        ("Licensee Rate", "summary-licensee-rate"),
        ("Licensor Rate", "summary-licensor-rate"),
        ("Probability to Approval", "summary-approval-prob"),
        ("Launch Year", "summary-launch-year"),
        ("Tax Rate", "summary-tax-rate"),
    ]
    return dbc.Row(
        [
            dbc.Col(
                html.Div(
                    [
                        html.Div(title, style={"fontSize": "0.72rem", "fontWeight": "800", "color": COLORS["muted"]}),
                        html.Div(id=component_id, style={"fontSize": "1.15rem", "fontWeight": "800", "marginTop": "2px"}),
                    ],
                    style={**CARD, "padding": "12px 14px", "height": "76px"},
                ),
                lg=3, md=4, sm=6,
            )
            for title, component_id in cards
        ],
        className="g-2",
        style={"marginBottom": "18px"},
    )


def dcf_table():
    return html.Div(
        [
            html.Div(
                [
                    html.H5("DCF Forecast", style={"fontWeight": "800", "marginBottom": "0"}),
                    dbc.Button("Reset manual overrides", id="reset-overrides", color="secondary", outline=True, size="sm"),
                ],
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginBottom": "10px"},
            ),
            dash_table.DataTable(
                id="dcf-table",
                data=[],
                columns=[],
                editable=True,
                merge_duplicate_headers=True,
                page_action="none",
                style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "620px", "width": "100%", "minWidth": "100%", "border": f"1px solid {COLORS['border']}", "borderRadius": "8px"},
                style_cell={"fontFamily": "Menlo, Consolas, 'SFMono-Regular', monospace", "fontSize": "12px", "padding": "7px 9px", "border": f"1px solid {COLORS['border']}", "whiteSpace": "nowrap", "textAlign": "right", "minWidth": "95px", "width": "95px", "maxWidth": "120px"},
                style_header={"backgroundColor": COLORS["header"], "color": COLORS["text"], "fontWeight": "800", "textAlign": "center", "border": f"1px solid {COLORS['border']}", "fontSize": "12px", "whiteSpace": "normal", "height": "36px"},
                style_cell_conditional=[
                    {"if": {"column_id": "label"}, "textAlign": "left", "fontWeight": "700", "minWidth": "270px", "width": "270px", "maxWidth": "360px", "backgroundColor": "#fbfcfd"},
                    {"if": {"column_id": "edit"}, "textAlign": "center", "minWidth": "44px", "width": "44px", "maxWidth": "44px", "color": COLORS["accent"], "fontWeight": "800"},
                ],
                css=[
                    {"selector": ".dash-spreadsheet td div", "rule": "line-height: 18px;"},
                    {"selector": ".dash-spreadsheet-container .dash-spreadsheet-inner table", "rule": "border-collapse: collapse;"},
                ],
            ),
        ],
        style={**CARD, "padding": "16px", "marginBottom": "18px"},
    )


def charts_panel():
    return dbc.Row(
        [
            dbc.Col(html.Div(dcc.Graph(id="revenue-fcf-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px"}), lg=7),
            dbc.Col(html.Div(dcc.Graph(id="discounted-fcf-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px"}), lg=5),
        ],
        className="g-3",
    )


def dcf_page():
    return html.Div([assumption_panel(), summary_cards(), dcf_table(), charts_panel()])


def licensor_page():
    return html.Div(
        [
            html.Div([html.H4("Licensor Model", style={"fontWeight": "800"}), html.Div("Deal economics connected to the DCF forecast: upfronts, milestones, tiered royalties, and licensor NPV.", style={"color": COLORS["muted"]})], style={"marginBottom": "16px"}),
            dbc.Row([
                dbc.Col(html.Div([html.Div("Licensor NPV", style=SMALL_LABEL), html.H4(id="licensor-npv", style={"color": COLORS["teal"]})], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("Total Milestones", style=SMALL_LABEL), html.H4(id="licensor-total-milestones")], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("Total Royalties", style=SMALL_LABEL), html.H4(id="licensor-total-royalties")], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("Total Deal Value", style=SMALL_LABEL), html.H4(id="licensor-total-deal-value")], style={**CARD, "padding": "18px"}), md=3),
            ], className="g-3 mb-3"),
            html.Div(dcc.Graph(id="licensor-bridge-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px", "marginBottom": "14px"}),
            html.Div(dcc.Graph(id="licensor-annual-cf-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px"}),
        ],
        style={**CARD, "padding": "20px"},
    )


def licensee_page():
    return html.Div(
        [
            html.Div([html.H4("Licensee Model", style={"fontWeight": "800"}), html.Div("Licensee cash flows after royalty and milestone payments to licensor.", style={"color": COLORS["muted"]})], style={"marginBottom": "16px"}),
            dbc.Row([
                dbc.Col(html.Div([html.Div("Licensee NPV", style=SMALL_LABEL), html.H4(id="licensee-npv", style={"color": COLORS["blue"]})], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("Total Payments to Licensor", style=SMALL_LABEL), html.H4(id="licensee-total-payments")], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("Peak Revenue", style=SMALL_LABEL), html.H4(id="licensee-peak-revenue")], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("Licensee WACC", style=SMALL_LABEL), html.H4(id="licensee-wacc-output")], style={**CARD, "padding": "18px"}), md=3),
            ], className="g-3 mb-3"),
            html.Div(dcc.Graph(id="licensee-annual-cf-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px", "marginBottom": "14px"}),
            html.Div(dcc.Graph(id="licensee-cumulative-pv-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px"}),
        ],
        style={**CARD, "padding": "20px"},
    )


def sensitivity_page():
    return html.Div(
        [
            html.Div([html.H4("Sensitivity / Tornado", style={"fontWeight": "800"}), html.Div("One-way sensitivity analysis based on the current dashboard assumptions.", style={"color": COLORS["muted"]})], style={"marginBottom": "16px"}),
            dbc.Row([
                dbc.Col([field("Metric", dcc.Dropdown(id="sens-metric", value="core_dcf_npv", options=[{"label": "Core DCF NPV", "value": "core_dcf_npv"}, {"label": "Licensee eNPV", "value": "licensee_npv"}, {"label": "Licensor NPV", "value": "licensor_npv"}], clearable=False, style={"fontSize": "0.86rem"}))], lg=3, md=4),
                dbc.Col(html.Div(id="sens-base-npv", style={"fontSize": "1rem", "fontWeight": "800", "paddingTop": "22px", "color": COLORS["blue"]}), lg=2, md=3),
            ], className="g-2 mb-3"),
            html.Div(dcc.Graph(id="sensitivity-tornado-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px", "marginBottom": "14px"}),
            dash_table.DataTable(id="sensitivity-table", columns=[], data=[], editable=False, merge_duplicate_headers=True, page_action="none", style_table={"fontSize": "0.8rem"}, style_cell={"fontFamily": "monospace", "fontSize": "0.78rem", "padding": "3px 6px", "textAlign": "right", "border": "1px solid #e9ecef"}, style_header={"backgroundColor": "#1f6feb", "color": "white", "fontWeight": "700", "fontSize": "0.78rem"}),
        ],
        style={**CARD, "padding": "20px"},
    )


def monte_carlo_page():
    return html.Div(
        [
            html.Div([html.H4("Monte Carlo", style={"fontWeight": "800"}), html.Div("Lightweight simulation using the current dashboard assumptions. Key drivers are varied around price, penetration, patient pool, COGS, discount rate, launch timing, and phase-success rates.", style={"color": COLORS["muted"]})], style={"marginBottom": "16px"}),
            dbc.Row([
                dbc.Col(html.Div([html.Div("Mean rNPV", style=SMALL_LABEL), html.H4(id="mc-mean-rnpv")], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("Median rNPV", style=SMALL_LABEL), html.H4(id="mc-median-rnpv")], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("P10 / P90", style=SMALL_LABEL), html.H4(id="mc-p10-p90")], style={**CARD, "padding": "18px"}), md=3),
                dbc.Col(html.Div([html.Div("Probability rNPV > 0", style=SMALL_LABEL), html.H4(id="mc-prob-positive")], style={**CARD, "padding": "18px"}), md=3),
            ], className="g-3 mb-3"),
            html.Div(dcc.Graph(id="mc-histogram-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px"}),
        ],
        style={**CARD, "padding": "20px"},
    )


def sidebar():
    return html.Div(
        [
            html.Div("NPV", style={"fontSize": "1.4rem", "fontWeight": "900", "marginBottom": "2px"}),
            html.Div("Biopharma DCF Dashboard", style={"fontSize": "0.8rem", "color": COLORS["muted"], "marginBottom": "22px"}),
            dbc.Nav([
                dbc.NavLink("Assumptions + DCF", id="nav-dcf", active=True, n_clicks=0),
                dbc.NavLink("Licensee Model", id="nav-licensee", active=False, n_clicks=0),
                dbc.NavLink("Licensor Bridge", id="nav-licensor", active=False, n_clicks=0),
                dbc.NavLink("Monte Carlo", id="nav-monte-carlo", active=False, n_clicks=0),
                dbc.NavLink("Sensitivity", id="nav-sensitivity", active=False, n_clicks=0),
            ], vertical=True, pills=True),
            html.Hr(),
            html.Div(id="override-status", style={"fontSize": "0.75rem", "color": COLORS["muted"]}),
        ],
        style=SIDEBAR,
    )


def model_note_bar():
    return html.Div(
        dbc.Row([
            dbc.Col(html.Div("Model note", style={"fontSize": "0.72rem", "fontWeight": "800", "color": COLORS["muted"]}), lg=2, md=3),
            dbc.Col(html.Div("This dashboard is a deterministic DCF with live sensitivity and a lightweight Monte Carlo simulation. Scenario save/load is not enabled yet.", style={"fontSize": "0.86rem", "color": COLORS["text"]}), lg=10, md=9),
        ], className="g-2 align-items-center"),
        style={**CARD, "padding": "14px 16px", "marginBottom": "18px"},
    )


def build_layout():
    return html.Div(
        [
            dcc.Store(id="manual-overrides", data={}),
            dcc.Store(id="last-table-data", data=[]),
            html.Div([
                sidebar(),
                html.Main([
                    model_note_bar(),
                    html.Div(id="page-dcf", children=dcf_page()),
                    html.Div(id="page-licensee", children=licensee_page(), style={"display": "none"}),
                    html.Div(id="page-licensor", children=licensor_page(), style={"display": "none"}),
                    html.Div(id="page-monte-carlo", children=monte_carlo_page(), style={"display": "none"}),
                    html.Div(id="page-sensitivity", children=sensitivity_page(), style={"display": "none"}),
                ], style=CONTENT),
            ], style={"display": "flex", "alignItems": "stretch"}),
        ],
        style=PAGE,
    )
