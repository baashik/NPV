"""Dash layout for the modular valuation dashboard."""

from __future__ import annotations

from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc

from model_engine import DEFAULT_ASSUMPTIONS
from styles import CARD, COLORS, CONTENT, PAGE, SIDEBAR, SMALL_LABEL, TABLE_CELL, TABLE_HEADER, TABLE_STYLE


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
                        "Inputs update the DCF automatically. Table edits override individual forecast cells.",
                        style={"color": COLORS["muted"], "fontSize": "0.88rem"},
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
                            field(
                                "Currency",
                                dcc.Dropdown(
                                    id="currency",
                                    value=a["currency"],
                                    options=[{"label": c, "value": c} for c in ["USD", "EUR", "GBP"]],
                                    clearable=False,
                                    style={"fontSize": "0.86rem"},
                                ),
                            ),
                            field(
                                "Units",
                                dcc.Dropdown(
                                    id="units",
                                    value=a["units"],
                                    options=[{"label": "Millions", "value": "Millions"}],
                                    clearable=False,
                                    style={"fontSize": "0.86rem"},
                                ),
                            ),
                        ],
                        lg=3,
                        md=6,
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
                        lg=3,
                        md=6,
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
                        lg=3,
                        md=6,
                    ),
                    dbc.Col(
                        [
                            section_title("Tax / Discount"),
                            field("Tax Rate (%)", number_input("tax-rate", a["tax_rate"], 0.5)),
                            field("Asset Discount Rate (%)", number_input("asset-discount-rate", a["asset_discount_rate"], 0.5)),
                            field("Licensee WACC (%)", number_input("licensee-wacc", a["licensee_wacc"], 0.5)),
                            field("Licensor Discount Rate (%)", number_input("licensor-discount-rate", a["licensor_discount_rate"], 0.5)),
                            section_title("Phase Success Rates"),
                            field("Ph1 → Ph2 (%)", number_input("phase-i-success", a["phase_i_success"], 0.5)),
                            field("Ph2 → Ph3 (%)", number_input("phase-ii-success", a["phase_i_success"], 0.5)),
                            field("Ph3 → NDA (%)", number_input("phase-iii-success", a["phase_iii_success"], 0.5)),
                            field("NDA → Approval (%)", number_input("approval-success", a["approval_success"], 0.5)),
                        ],
                        lg=3,
                        md=6,
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
                        lg=3,
                        md=6,
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
                lg=3,
                md=4,
                sm=6,
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
                fixed_columns={"headers": True, "data": 2},
                page_action="none",
                style_table=TABLE_STYLE,
                style_cell=TABLE_CELL,
                style_header=TABLE_HEADER,
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


def sensitivity_panel():
    return html.Div(
        [
            html.H5("Sensitivity / Tornado", style={"fontWeight": "800", "marginBottom": "8px"}),
            dcc.Graph(id="tornado-chart", config={"displayModeBar": False}),
        ],
        style={**CARD, "padding": "12px", "marginTop": "18px"},
    )


def dcf_page():
    return html.Div([assumption_panel(), summary_cards(), dcf_table(), charts_panel(), sensitivity_panel()])


def licensor_page():
    a = DEFAULT_ASSUMPTIONS
    return html.Div(
        [
            html.Div(
                [
                    html.H4("Licensor Model", style={"fontWeight": "800"}),
                    html.Div("Deal economics connected to the DCF forecast: upfronts, milestones, tiered royalties, and licensor NPV.", style={"color": COLORS["muted"]}),
                ],
                style={"marginBottom": "16px"},
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                section_title("Inputs"),
                                field("Upfront Payment (M)", number_input("upfront-payment", a["upfront_payment"], 1)),
                                field("Development Milestones (M)", number_input("development-milestones", a["development_milestones"], 1)),
                                field("Regulatory Milestones (M)", number_input("regulatory-milestones", a["regulatory_milestones"], 1)),
                                field("Commercial Milestones (M)", number_input("commercial-milestones", a["commercial_milestones"], 1)),
                                field("Royalty Rate", number_input("royalty-rate", a["royalty_rate"], 0.5)),
                                field("Tier 1 Royalty: first $100M", number_input("royalty-tier-1-rate", a["royalty_tier_1_rate"], 0.5)),
                                field("Tier 2 Royalty: $100M-$200M", number_input("royalty-tier-2-rate", a["royalty_tier_2_rate"], 0.5)),
                                field("Tier 3 Royalty: above $200M", number_input("royalty-tier-3-rate", a["royalty_tier_3_rate"], 0.5)),
                                field("Royalty Start Year", number_input("royalty-start-year", a["royalty_start_year"], 1)),
                                field("Royalty End Year", number_input("royalty-end-year", a["royalty_end_year"], 1)),
                                field("Licensor Discount Rate", number_input("licensor-discount-rate", a["licensor_discount_rate"], 0.5)),
                            ],
                            style={**CARD, "padding": "18px"},
                        ),
                        lg=4,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(html.Div([html.Div("Licensor NPV", style=SMALL_LABEL), html.H4(id="licensor-npv")], style={**CARD, "padding": "18px"}), md=6),
                                        dbc.Col(html.Div([html.Div("Total Milestones", style=SMALL_LABEL), html.H4(id="licensor-total-milestones")], style={**CARD, "padding": "18px"}), md=6),
                                        dbc.Col(html.Div([html.Div("Total Royalties", style=SMALL_LABEL), html.H4(id="licensor-total-royalties")], style={**CARD, "padding": "18px"}), md=6),
                                        dbc.Col(html.Div([html.Div("Total Deal Value", style=SMALL_LABEL), html.H4(id="licensor-total-deal-value")], style={**CARD, "padding": "18px"}), md=6),
                                    ],
                                    className="g-3",
                                ),
                                html.Div(dcc.Graph(id="licensor-bridge-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px", "marginTop": "16px"}),
                                html.Div(dcc.Graph(id="licensor-cashflow-chart", config={"displayModeBar": False}), style={**CARD, "padding": "10px", "marginTop": "16px"}),
                            ]
                        ),
                        lg=8,
                    ),
                ],
                className="g-3",
            ),
        ]
    )


def monte_carlo_page():
    return html.Div(
        [
            html.Div(
                [
                    html.H4("Monte Carlo", style={"fontWeight": "800"}),
                    html.Div("Live simulation using WACC, penetration, price, probability, and development cost distributions.", style={"color": COLORS["muted"]}),
                ],
                style={"marginBottom": "16px"},
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                section_title("Inputs"),
                                field("Number of simulations", number_input("mc-sims", 5000, 500)),
                                field("WACC low/base/high", dbc.Input(id="mc-wacc", value="10 / 12 / 15", size="sm")),
                                field("Peak penetration low/base/high", dbc.Input(id="mc-peak-pen", value="6 / 10 / 14", size="sm")),
                                field("Price low/base/high", dbc.Input(id="mc-price", value="750 / 1000 / 1250", size="sm")),
                                field("Probability of success low/base/high", dbc.Input(id="mc-pos", value="15 / 22 / 30", size="sm")),
                                field("Development cost multiplier low/base/high", dbc.Input(id="mc-cost", value="0.8 / 1.0 / 1.3", size="sm")),
                            ],
                            style={**CARD, "padding": "18px"},
                        ),
                        lg=4,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(html.Div([html.Div("Mean rNPV", style=SMALL_LABEL), html.H4(id="mc-mean-rnpv")], style={**CARD, "padding": "18px"}), md=6),
                                        dbc.Col(html.Div([html.Div("Median rNPV", style=SMALL_LABEL), html.H4(id="mc-median-rnpv")], style={**CARD, "padding": "18px"}), md=6),
                                        dbc.Col(html.Div([html.Div("P10 / P90", style=SMALL_LABEL), html.H4(id="mc-p10-p90")], style={**CARD, "padding": "18px"}), md=6),
                                        dbc.Col(html.Div([html.Div("Probability rNPV > 0", style=SMALL_LABEL), html.H4(id="mc-prob-positive")], style={**CARD, "padding": "18px"}), md=6),
                                    ],
                                    className="g-3",
                                ),
                                html.Div(
                                    dcc.Graph(id="mc-histogram-chart", config={"displayModeBar": False}),
                                    style={**CARD, "padding": "10px", "marginTop": "16px"},
                                ),
                            ]
                        ),
                        lg=8,
                    ),
                ],
                className="g-3",
            ),
        ]
    )


def sidebar():
    return html.Div(
        [
            html.Div("NPV", style={"fontSize": "1.4rem", "fontWeight": "900", "marginBottom": "2px"}),
            html.Div("Modular DCF Dashboard", style={"fontSize": "0.8rem", "color": COLORS["muted"], "marginBottom": "22px"}),
            dbc.Nav(
                [
                    dbc.NavLink("Assumptions + DCF", id="nav-dcf", active=True, n_clicks=0),
                    dbc.NavLink("Licensor Model", id="nav-licensor", active=False, n_clicks=0),
                    dbc.NavLink("Monte Carlo", id="nav-monte-carlo", active=False, n_clicks=0),
                ],
                vertical=True,
                pills=True,
            ),
            html.Hr(),
            html.Div("Model type", style=SMALL_LABEL),
            dcc.Dropdown(
                id="model-type",
                value="DCF Only",
                clearable=False,
                options=[{"label": item, "value": item} for item in ["DCF Only", "DCF + Licensor", "DCF + Licensee", "Full Licensing Model", "Monte Carlo"]],
                style={"fontSize": "0.84rem"},
            ),
        ],
        style=SIDEBAR,
    )


def scenario_bar():
    return html.Div(
        dbc.Row(
            [
                dbc.Col(field("Scenario", dbc.Input(id="scenario-name", value="Base Case", size="sm")), lg=3, md=6),
                dbc.Col(
                    field(
                        "Load Saved",
                        dcc.Dropdown(id="scenario-dropdown", options=[], placeholder="Select saved scenario", style={"fontSize": "0.86rem"}),
                    ),
                    lg=3,
                    md=6,
                ),
                dbc.Col(
                    html.Div(
                        [
                            dbc.Button("Save", id="save-scenario", color="primary", size="sm"),
                            dbc.Button("Load", id="load-scenario", color="secondary", outline=True, size="sm"),
                            dbc.Button("Delete", id="delete-scenario", color="danger", outline=True, size="sm"),
                            dbc.Button("Export", id="export-scenario", color="success", outline=True, size="sm"),
                        ],
                        style={"display": "flex", "gap": "8px", "alignItems": "end", "height": "100%"},
                    ),
                    lg=4,
                    md=8,
                ),
                dbc.Col(html.Div(id="scenario-status", style={"fontSize": "0.82rem", "color": COLORS["muted"], "paddingTop": "24px"}), lg=2, md=4),
            ],
            className="g-2 align-items-end",
        ),
        style={**CARD, "padding": "14px 16px", "marginBottom": "18px"},
    )


def build_layout():
    return html.Div(
        [
            dcc.Store(id="active-page", data="dcf"),
            dcc.Store(id="manual-overrides", data={}),
            dcc.Store(id="last-table-data", data=[]),
            dcc.Store(id="saved-scenarios", data={}),
            dcc.Store(id="model-summary-store", data={}),
            dcc.Store(id="simulation-results-store", data={}),
            dcc.Download(id="download-export"),
            html.Div(
                [
                    sidebar(),
                    html.Main(
                        [
                            scenario_bar(),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Biopharma Licensing Monte Carlo NPV Dashboard", style={"fontWeight": "900", "marginBottom": "4px"}),
                                            html.Div("Bottom-up EU patient forecast, deterministic DCF, PTRS risk adjustment, and modular licensing tabs.", style={"color": COLORS["muted"]}),
                                        ]
                                    ),
                                    html.Div(id="override-status", style={"color": COLORS["muted"], "fontSize": "0.82rem"}),
                                ],
                                style={"display": "flex", "alignItems": "flex-start", "justifyContent": "space-between", "gap": "18px", "marginBottom": "18px"},
                            ),
                            html.Div(id="page-dcf", children=dcf_page()),
                            html.Div(id="page-licensor", children=licensor_page(), style={"display": "none"}),
                            html.Div(id="page-monte-carlo", children=monte_carlo_page(), style={"display": "none"}),
                        ],
                        style=CONTENT,
                    ),
                ],
                style={"display": "flex", "alignItems": "stretch"},
            ),
        ],
        style=PAGE,
    )
