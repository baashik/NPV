"""NPV Model — UI components (layout, cards, charts, pages)."""

import numpy as np
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from config import COLORS as C, N_YEARS, YEARS, RD_SCHEDULE
from styles import COLORS, CARD, PAGE, SIDEBAR, CONTENT, SMALL_LABEL


# ============================================================================
# Reusable
# ============================================================================
def kpi_card(title, value, color="#1f6feb", sub=None):
    children = [
        html.P(title, style={"fontSize": "0.72rem", "color": COLORS["muted"], "marginBottom": "2px",
                             "fontWeight": "700", "letterSpacing": "0.03em"}),
        html.H4(value, style={"color": color, "marginBottom": "0", "fontWeight": "800"}),
    ]
    if sub:
        children.append(html.Small(sub, style={"color": COLORS["muted"]}))
    return dbc.Card(dbc.CardBody(children, style={"padding": "12px 16px"}),
                    style={**CARD, "borderLeft": f"4px solid {color}", "borderRadius": "8px"})


def field(label, component):
    return html.Div([dbc.Label(label, style=SMALL_LABEL), component], style={"marginBottom": "8px"})


def section_label(text):
    return html.P(text, style={"fontSize": "0.7rem", "fontWeight": "800", "letterSpacing": "0.08em",
                               "color": COLORS["muted"], "margin": "8px 0 10px", "textTransform": "uppercase"})


# ============================================================================
# Sidebar
# ============================================================================
def sidebar():
    return html.Div([
        html.Div("NPV", style={"fontSize": "1.3rem", "fontWeight": "900", "marginBottom": "2px"}),
        html.Div("Licensing Model", style={"fontSize": "0.78rem", "color": COLORS["muted"], "marginBottom": "20px"}),
        html.Hr(style={"margin": "0 0 12px"}),
        dbc.Nav([
            dbc.NavLink("Assumptions + DCF", id="nav-dcf", active=True, n_clicks=0),
            dbc.NavLink("Monte Carlo", id="nav-mc", active=False, n_clicks=0),
            dbc.NavLink("Licensor Bridge", id="nav-bridge", active=False, n_clicks=0),
            dbc.NavLink("Tornado", id="nav-sens", active=False, n_clicks=0),
        ], vertical=True, pills=True, className="mb-3"),
        html.Hr(),
        html.Div("DCF Table", style={"fontWeight": "700", "fontSize": "0.78rem", "color": COLORS["muted"], "margin": "8px 0"}),
        html.Div(id="sidebar-dcf-mini",
                 children=html.Span("Run simulation", style={"fontSize": "0.75rem", "color": COLORS["muted"]})),
    ], style=SIDEBAR)


# ============================================================================
# Summary cards row
# ============================================================================
def summary_cards():
    ids = ["summary-lic-mean", "summary-lic-prob", "summary-lr-mean", "summary-lr-prob"]
    return dbc.Row([
        dbc.Col(html.Div(id=ids[0], style={**CARD, "padding": "12px 14px", "height": "70px"}), lg=3, md=6)
        for i in range(4)
    ], className="g-2 mb-3")


# ============================================================================
# Action bar (scenario controls)
# ============================================================================
def action_bar():
    return dbc.Card([
        dbc.Row([
            dbc.Col(field("Scenario", dbc.Input(id="scenario-name", value="Base Case", type="text", size="sm")), md=2),
            dbc.Col(field("Simulations", dcc.Slider(id="sl-sims", min=1000, max=10000, step=1000, value=5000,
                                                     marks={1000: "1K", 5000: "5K", 10000: "10K"},
                                                     tooltip={"placement": "bottom"})), md=4),
            dbc.Col(field("Load", dcc.Dropdown(id="load-scenario-dropdown", options=[], placeholder="Select...",
                                                style={"fontSize": "0.84rem"})), md=2),
            dbc.Col(html.Div([
                dbc.ButtonGroup([
                    dbc.Button("Run", id="btn-run", color="primary", size="sm"),
                    dbc.Button("Save", id="btn-save", color="success", size="sm"),
                    dbc.Button("Export", id="btn-export", color="secondary", size="sm"),
                    dbc.Button("Delete", id="btn-delete", color="danger", size="sm"),
                ], size="sm"),
            ], style={"display": "flex", "alignItems": "end", "height": "100%"}), md=4),
        ], className="g-2 align-items-end"),
        dbc.Row([
            dbc.Col(html.Div(id="run-status", style={"fontSize": "0.78rem", "color": COLORS["muted"]}), md=6),
            dbc.Col(html.Div(id="save-status", style={"fontSize": "0.75rem", "color": COLORS["muted"]}), md=6, style={"textAlign": "right"}),
        ], className="mt-1"),
    ], body=True, style={**CARD, "borderRadius": "8px", "marginBottom": "14px"})


# ============================================================================
# Assumptions panel
# ============================================================================
def assumptions_panel():
    return html.Div([
        html.H5("Assumptions", style={"fontWeight": "800", "marginBottom": "12px"}),
        dbc.Row([
            dbc.Col([
                section_label("Commercial"),
                field("EU Population (M)", dbc.Input(id="in-pop", value=450.0, type="number", step=10, size="sm")),
                field("Price / Patient ($)", dbc.Input(id="in-price", value=15000.0, type="number", step=500, size="sm")),
                field("Peak Penetration (%)", dbc.Input(id="in-pen", value=5.0, type="number", step=0.5, size="sm")),
                field("COGS (% of Rev)", dbc.Input(id="in-cogs", value=12.0, type="number", step=1, size="sm")),
                field("Tax Rate (%)", dbc.Input(id="in-tax", value=21.0, type="number", step=1, size="sm")),
            ], lg=3, md=6),
            dbc.Col([
                section_label("Discount Rates"),
                field("Asset Discount Rate (%)", dbc.Input(id="in-asset-dr", value=12.0, type="number", step=0.5, size="sm")),
                field("Licensee WACC (%)", dbc.Input(id="in-lsw", value=10.0, type="number", step=0.5, size="sm")),
                field("Licensor Discount Rate (%)", dbc.Input(id="in-lrw", value=14.0, type="number", step=0.5, size="sm")),
                html.Div(style={"height": "8px"}),
                section_label("PTRS"),
                field("Ph1 → Ph2 (%)", dbc.Input(id="p1", value=63.0, type="number", step=1, size="sm")),
                field("Ph2 → Ph3 (%)", dbc.Input(id="p2", value=30.0, type="number", step=1, size="sm")),
                field("Ph3 → NDA (%)", dbc.Input(id="p3", value=58.0, type="number", step=1, size="sm")),
                field("NDA → Approval (%)", dbc.Input(id="p4", value=90.0, type="number", step=1, size="sm")),
            ], lg=3, md=6),
            dbc.Col([
                section_label("Deal Terms"),
                field("Upfront ($M)", dbc.Input(id="in-upfront", value=2.0, type="number", step=0.5, size="sm")),
                field("Milestone each ($M)", dbc.Input(id="in-mil", value=1.0, type="number", step=0.5, size="sm")),
                html.Div(style={"height": "8px"}),
                html.P("Royalty Tiers", style={"fontWeight": "700", "fontSize": "0.72rem", "color": COLORS["muted"]}),
                html.Div([
                    html.Span("• 5% on first $100M", style={"fontSize": "0.8rem"}),
                    html.Br(),
                    html.Span("• 7% on $100–200M", style={"fontSize": "0.8rem"}),
                    html.Br(),
                    html.Span("• 9% on $200M+", style={"fontSize": "0.8rem"}),
                ]),
            ], lg=3, md=6),
            dbc.Col([
                section_label("Epidemiology"),
                html.Div([
                    html.Span("• Target Population: 9% of EU", style={"fontSize": "0.8rem"}),
                    html.Br(),
                    html.Span("• Diagnosis Rate: 80%", style={"fontSize": "0.8rem"}),
                    html.Br(),
                    html.Span("• Treatment Rate: 50%", style={"fontSize": "0.8rem"}),
                ]),
            ], lg=3, md=6),
        ], className="g-3"),
    ], style={**CARD, "padding": "16px", "marginBottom": "14px"})


# ============================================================================
# Pages
# ============================================================================
def dcf_page():
    return html.Div([
        summary_cards(),
        assumptions_panel(),
        html.Div([
            html.H5("Revenue & Cash Flow", style={"fontWeight": "800", "marginBottom": "8px"}),
            dbc.Card(dbc.CardBody(dcc.Graph(id="cf-chart", config={"displayModeBar": False})),
                     style={**CARD, "padding": "8px"}),
        ]),
    ])


def mc_page():
    return html.Div([
        summary_cards(),
        html.Div(dbc.Card(dbc.CardBody(dcc.Graph(id="mc-chart", config={"displayModeBar": False})),
                           style={**CARD, "padding": "8px"})),
    ])


def bridge_page():
    return html.Div([
        summary_cards(),
        html.Div([
            dbc.Card(dbc.CardBody(dcc.Graph(id="bridge-chart", config={"displayModeBar": False})),
                     style={**CARD, "padding": "8px", "marginBottom": "14px"}),
            dbc.Card(dbc.CardBody(dcc.Graph(id="bridge-annual-chart", config={"displayModeBar": False})),
                     style={**CARD, "padding": "8px"}),
        ]),
    ])


def sens_page():
    return html.Div([
        summary_cards(),
        html.Div([
            dbc.Card(dbc.CardBody(dcc.Graph(id="tornado-chart", config={"displayModeBar": False})),
                     style={**CARD, "padding": "8px", "marginBottom": "14px"}),
            dbc.Card(dbc.CardBody(dcc.Graph(id="price-sens-chart", config={"displayModeBar": False})),
                     style={**CARD, "padding": "8px"}),
        ]),
    ])


# ============================================================================
# DCF Table builder
# ============================================================================
def build_dcf_table(base):
    """
    Returns (columns, rows, metric_rows) for a TRANSPOSED DCF table:
      - First column  = metric label (Line Item)
      - Remaining 17 columns = one per year (2026 to 2042)
    """
    rd_arr = np.array([RD_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)])
    disc_fcf = base["risk_adj_fcf"] * base.get("df_asset", base.get("df_ls", np.ones(N_YEARS)))

    pop_row, pop = [], 450.0
    for _ in range(N_YEARS):
        pop *= 1.002
        pop_row.append(pop)

    LABEL_COL = "Line Item"
    year_cols = [str(y) for y in YEARS]

    metric_rows = [
        ("── REVENUE MODEL", None, "header"),
        ("EU Population (M)", pop_row, "pop"),
        ("Gross Revenue ($M)", base["rev"], "rev"),
        ("Less: COGS ($M)", -base["cogs"], "cost"),
        ("── COSTS & R&D", None, "header"),
        ("R&D Expense ($M)", -rd_arr, "cost"),
        ("EBITDA ($M)", base["ebitda"], "ebitda"),
        ("── DEAL ECONOMICS", None, "header"),
        ("Royalty Paid ($M)", -base.get("royalty", np.zeros(N_YEARS)), "cost"),
        ("Free Cash Flow ($M)", base["fcf"], "fcf"),
        ("── RISK ADJUSTMENT", None, "header"),
        ("Cum. P(Success) %", base["ptr"] * 100, "pct"),
        ("Risk-Adj FCF ($M)", base["risk_adj_fcf"], "rfcf"),
        ("── DISCOUNTING", None, "header"),
        ("Discount Factor", base.get("df_ls", np.ones(N_YEARS)), "df"),
        ("Disc. eNPV ($M)", disc_fcf, "enpv"),
    ]

    columns = [{"name": LABEL_COL, "id": LABEL_COL}] + \
              [{"name": y, "id": y} for y in year_cols]

    rows = []
    for label, vals, fmt in metric_rows:
        row = {LABEL_COL: label}
        if vals is None:
            for y in year_cols:
                row[y] = ""
        else:
            for i, y in enumerate(year_cols):
                v = float(vals[i])
                if fmt == "pop":
                    row[y] = f"{v:,.1f}"
                elif fmt == "pct":
                    row[y] = f"{v:.1f}%"
                elif fmt == "df":
                    row[y] = f"{v:.4f}"
                else:
                    row[y] = f"{v:,.2f}"
        rows.append(row)

    return columns, rows, metric_rows


# ============================================================================
# Main layout
# ============================================================================
def build_app_layout():
    return html.Div([
        dcc.Store(id="store-results"),
        dcc.Store(id="store-scenarios", data={}),
        dcc.Download(id="download-export"),
        html.Div([
            sidebar(),
            html.Main([
                action_bar(),
                html.Div(id="page-dcf", children=dcf_page()),
                html.Div(id="page-mc", children=mc_page(), style={"display": "none"}),
                html.Div(id="page-bridge", children=bridge_page(), style={"display": "none"}),
                html.Div(id="page-sens", children=sens_page(), style={"display": "none"}),
            ], style=CONTENT),
        ], style={"display": "flex", "alignItems": "stretch"}),
    ], style=PAGE)
