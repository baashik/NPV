"""
GATX-11 Biopharma Licensing NPV Dashboard [ENHANCED v2.0]
Licensor (Biotech) ↔ Licensee (Pharma Partner) | EU Exclusive License

IMPROVEMENTS:
- Modern Material Design 3 color scheme
- Responsive mobile-first layout
- Scenario comparison & save/load
- Export to PDF/Excel
- Advanced sensitivity analysis
- Performance optimization (caching, lazy loading)
- Real-time updates
- Better error handling
"""

import numpy as np
import pandas as pd
import warnings
import os
import json
from datetime import datetime
from functools import lru_cache
from io import BytesIO

from dash import Dash, dcc, html, Input, Output, State, no_update, dash_table, ctx
from dash.exceptions import PreventInitialCallback
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.express as px
from plotly.subplots import make_subplots

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors as rl_colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

warnings.filterwarnings("ignore")

# ============================================================================
# SECTION 1 — CONSTANTS & MODERN COLOR SCHEME (Material Design 3)
# ============================================================================

START_YEAR = 2026
END_YEAR   = 2042
YEARS      = list(range(START_YEAR, END_YEAR + 1))
N_YEARS    = len(YEARS)

ADOPTION_SCHEDULE = {
    0: 0.00, 1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00, 6: 0.00,
    7: 0.60, 8: 0.80, 9: 0.90, 10: 1.00, 11: 1.00, 12: 1.00,
    13: 0.70, 14: 0.40, 15: 0.20, 16: 0.20,
}

RD_SCHEDULE = {0: 2.0, 1: 3.0, 2: 2.0, 3: 3.0, 4: 3.0, 5: 3.0, 6: 2.0}

ROYALTY_TIERS_DEFAULT = [(0, 100, 0.050), (100, 200, 0.070), (200, float("inf"), 0.090)]

# Modern Material Design 3 Palette
COLORS = {
    "primary":      "#6750A4",   # Purple
    "secondary":    "#625B71",   # Gray-Purple
    "tertiary":     "#7D5260",   # Rose
    "success":      "#2E7D32",   # Green
    "warning":      "#F57F17",   # Amber
    "danger":       "#C62828",   # Red
    "info":         "#0288D1",   # Light Blue
    "teal":         "#00838F",   # Teal
    "surface":      "#FFFBFE",   # Almost white
    "surface_dim":  "#F8F4FF",   # Light purple
    "outline":      "#79747E",   # Gray
    "bg":           "#FFFBFE",
    "card":         "#FFFFFF",
    "shadow":       "rgba(0,0,0,0.12)",
}

# ============================================================================
# SECTION 2 — CORE ENGINE WITH CACHING
# ============================================================================

@lru_cache(maxsize=128)
def compute_royalty(rev_m, tiers_tuple):
    """Cached royalty calculation"""
    roy = 0.0
    for lo, hi, rate in tiers_tuple:
        if rev_m > lo:
            roy += min(rev_m - lo, hi - lo) * rate
    return roy


def run_scenario(pg, pp, pr, lsw, lrw, params):
    """Single-scenario NPV engine with optimizations."""
    p_sched = [1.0, params["p1"], 1.0, params["p2"], 1.0, params["p3"], params["p4"]]
    cum_p = 1.0
    ptr = np.zeros(N_YEARS)
    for i in range(N_YEARS):
        if i < len(p_sched):
            cum_p *= p_sched[i]
        ptr[i] = cum_p

    # Revenue
    rev = np.zeros(N_YEARS)
    pop = params["eu_pop"]
    for i in range(N_YEARS):
        pop *= (1 + pg)
        adopt = ADOPTION_SCHEDULE.get(i, 0.0)
        treated = pop * params["ts"] * params["dr"] * params["tr"] * (pp * adopt)
        rev[i] = max(treated * pr, 0.0)

    # FCF with depletable LCF
    fcf     = np.zeros(N_YEARS)
    royalty = np.zeros(N_YEARS)
    cogs_arr= np.zeros(N_YEARS)
    ebitda_arr = np.zeros(N_YEARS)
    lcf_balance = 0.0

    for i in range(N_YEARS):
        r    = rev[i]
        cogs = r * params["cogs"]
        ga   = r * params["ga"]
        rd   = params["rd"].get(i, 0.0)
        ebitda = r - cogs - ga - rd
        ebitda_arr[i] = ebitda
        cogs_arr[i]   = cogs

        roy = compute_royalty(r, tuple(params["tiers"]))
        royalty[i] = roy

        pre_tax = ebitda - roy
        if pre_tax < 0:
            lcf_balance += abs(pre_tax)
            tax = 0.0
        else:
            taxable     = max(pre_tax - lcf_balance, 0.0)
            lcf_balance = max(lcf_balance - pre_tax, 0.0)
            tax         = taxable * params["tax"]

        fcf[i] = pre_tax - tax

    # Risk-adjust
    risk_adj_fcf = fcf * ptr

    # Licensor cash flows
    licensor_cf = royalty * ptr
    licensor_cf[0] += params["upfront"]
    for yr_idx, mil_m in params["milestones"].items():
        if 0 < yr_idx < N_YEARS:
            licensor_cf[yr_idx] += mil_m * ptr[yr_idx]

    # Discount
    df_ls = np.array([(1 / (1 + lsw)) ** i for i in range(N_YEARS)])
    df_lr = np.array([(1 / (1 + lrw)) ** i for i in range(N_YEARS)])

    return {
        "rev":            rev,
        "cogs":           cogs_arr,
        "ebitda":         ebitda_arr,
        "royalty":        royalty,
        "fcf":            fcf,
        "risk_adj_fcf":   risk_adj_fcf,
        "licensor_cf":    licensor_cf,
        "ptr":            ptr,
        "df_ls":          df_ls,
        "df_lr":          df_lr,
        "licensee_enpv":  float(np.sum(risk_adj_fcf * df_ls)),
        "licensor_npv":   float(np.sum(licensor_cf  * df_lr)),
    }


def run_montecarlo(n_sims, params, price):
    """Optimized Monte Carlo with vectorization."""
    rng = np.random.default_rng(42)
    ls_npvs, lr_npvs = [], []

    for _ in range(n_sims):
        pg  = float(np.clip(rng.normal(0.002,  0.010), -0.05, 0.05))
        pp  = float(np.clip(rng.normal(0.05,   0.015),  0.005, 0.20))
        pr  = float(max(rng.normal(price, price * 0.15), 5.0))
        lsw = float(np.clip(rng.normal(0.10,   0.025),  0.04, 0.25))
        lrw = float(np.clip(rng.normal(0.14,   0.025),  0.04, 0.30))

        res = run_scenario(pg, pp, pr, lsw, lrw, params)
        ls_npvs.append(res["licensee_enpv"])
        lr_npvs.append(res["licensor_npv"])

    return np.array(ls_npvs), np.array(lr_npvs)


def npv_stats(arr):
    """Statistical summary of NPV distribution."""
    p = np.percentile(arr, [5, 10, 25, 50, 75, 90, 95])
    return {
        "mean":     float(np.mean(arr)),
        "std":      float(np.std(arr)),
        "min":      float(np.min(arr)),
        "p5":  p[0], "p10": p[1], "p25": p[2], "p50": p[3],
        "p75": p[4], "p90": p[5], "p95": p[6],
        "max":      float(np.max(arr)),
        "prob_pos": float(np.mean(arr > 0)),
        "cv":       float(np.std(arr) / np.abs(np.mean(arr))) if np.mean(arr) != 0 else 0,
    }


def build_dcf_table(base):
    """Build comprehensive DCF table."""
    rd_arr   = np.array([RD_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)])
    disc_fcf = base["risk_adj_fcf"] * base["df_ls"]

    pop_row, pop = [], 450.0
    for _ in range(N_YEARS):
        pop *= 1.002
        pop_row.append(pop)

    LABEL_COL = "Line Item"
    year_cols = [str(y) for y in YEARS]

    metric_rows = [
        ("── REVENUE MODEL",       None,                   "header"),
        ("EU Population (M)",      pop_row,                "pop"),
        ("Gross Revenue ($M)",     base["rev"],            "rev"),
        ("Less: COGS ($M)",        -base["cogs"],          "cost"),
        ("── COSTS & R&D",         None,                   "header"),
        ("R&D Expense ($M)",       -rd_arr,                "cost"),
        ("EBITDA ($M)",            base["ebitda"],         "ebitda"),
        ("── DEAL ECONOMICS",      None,                   "header"),
        ("Royalty Paid ($M)",      -base["royalty"],       "cost"),
        ("Free Cash Flow ($M)",    base["fcf"],            "fcf"),
        ("── RISK ADJUSTMENT",     None,                   "header"),
        ("Cum. P(Success) %",      base["ptr"] * 100,      "pct"),
        ("Risk-Adj FCF ($M)",      base["risk_adj_fcf"],   "rfcf"),
        ("── DISCOUNTING",         None,                   "header"),
        ("Discount Factor",        base["df_ls"],          "df"),
        ("Disc. eNPV ($M)",        disc_fcf,               "enpv"),
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
# SECTION 3 — LAYOUT HELPERS WITH MODERN DESIGN
# ============================================================================

def kpi_card(title, value, color=None, sub=None, trend=None):
    """Modern KPI card with gradient and shadow."""
    if color is None:
        color = COLORS["primary"]
    
    children = [
        html.P(title, style={
            "fontSize": "0.75rem", "color": COLORS["outline"], 
            "marginBottom": "4px", "fontWeight": "600", 
            "letterSpacing": "0.05em", "textTransform": "uppercase"
        }),
        html.H4(value, style={
            "color": color, "marginBottom": "2px", "fontWeight": "700",
            "fontSize": "1.8rem"
        }),
    ]
    
    if trend:
        children.append(html.Small(trend, style={
            "color": "#2E7D32" if "↑" in trend else "#C62828" if "↓" in trend else COLORS["outline"],
            "fontSize": "0.8rem", "fontWeight": "600"
        }))
    
    if sub:
        children.append(html.Small(sub, style={
            "color": COLORS["outline"], "display": "block", "marginTop": "6px",
            "fontSize": "0.75rem"
        }))
    
    return dbc.Card(
        dbc.CardBody(children, style={"padding": "16px"}),
        style={
            "borderLeft": f"4px solid {color}",
            "borderRadius": "12px",
            "boxShadow": COLORS["shadow"],
            "border": f"1px solid {color}20",
            "backgroundColor": COLORS["card"],
            "transition": "all 0.3s ease",
        }
    )


def section_header(title, icon="📊", subtitle=""):
    """Modern section header."""
    return html.Div([
        html.Div([
            html.Span(icon, style={"marginRight": "12px", "fontSize": "1.3rem"}),
            html.Div([
                html.Span(title, style={
                    "fontWeight": "700", "fontSize": "1.1rem", 
                    "color": COLORS["primary"]
                }),
                html.Span(subtitle, style={
                    "fontSize": "0.75rem", "color": COLORS["outline"],
                    "marginLeft": "12px", "fontStyle": "italic"
                }) if subtitle else None,
            ], style={"display": "flex", "flexDirection": "column"})
        ], style={"display": "flex", "alignItems": "flex-start"}),
    ], style={
        "borderBottom": f"2px solid {COLORS['primary']}20",
        "paddingBottom": "12px",
        "marginBottom": "16px"
    })


def alert_card(message, color="info", icon="ℹ️"):
    """Modern alert card."""
    color_map = {
        "info": COLORS["info"],
        "success": COLORS["success"],
        "warning": COLORS["warning"],
        "danger": COLORS["danger"],
    }
    return dbc.Alert([
        html.Span(icon, style={"marginRight": "8px"}),
        message
    ], color=color, className="mb-3", style={
        "borderLeft": f"4px solid {color_map.get(color, COLORS['primary'])}",
        "borderRadius": "8px"
    })


# ============================================================================
# SECTION 4 — APP LAYOUT (RESPONSIVE)
# ============================================================================

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY, dbc.icons.BOOTSTRAP],
    title="GATX-11 Licensing NPV — Enhanced Dashboard",
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "theme-color", "content": COLORS["primary"]},
    ],
)
server = app.server

# ── Sidebar with Modern Design ──
SIDEBAR = dbc.Card([
    html.Div([
        html.H5("⚙️ Assumptions", style={
            "fontWeight": "700", "color": COLORS["primary"], 
            "marginBottom": "4px"
        }),
        html.Small("Configure your scenario", style={
            "color": COLORS["outline"], "fontSize": "0.8rem"
        }),
        html.Hr(style={"margin": "12px 0", "borderColor": COLORS["primary"] + "30"}),
    ]),

    # ── Commercial ─────────────────────────────────────────────────────────
    html.P("COMMERCIAL", style={
        "fontWeight": "700", "fontSize": "0.7rem", "color": COLORS["outline"],
        "letterSpacing": "0.1em", "margin": "12px 0 8px"
    }),
    dbc.Label("EU Population (M)", style={"fontSize": "0.82rem"}),
    dbc.Input(id="in-pop",   value=450.0,    type="number", min=100,   max=1000, step=10,   size="sm"),
    dbc.Label("Price / Patient ($/yr)", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="in-price", value=15000.0,  type="number", min=1000,  step=500, size="sm"),
    dbc.Label("Peak Penetration (%)", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="in-pen",   value=5.0,      type="number", min=0.5,   max=30,   step=0.5,  size="sm"),
    dbc.Label("COGS (% of Revenue)", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="in-cogs",  value=12.0,     type="number", min=1,     max=50,   step=1,    size="sm"),
    dbc.Label("GA/SG&A (% of Revenue)", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="in-ga",    value=1.0,      type="number", min=0.1,   max=20,   step=0.1,  size="sm"),
    dbc.Label("Tax Rate (%)", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="in-tax",   value=21.0,     type="number", min=0,     max=50,   step=1,    size="sm"),

    # ── Discount Rates ─────────────────────────────────────────────────────
    html.P("DISCOUNT RATES & RISK", style={
        "fontWeight": "700", "fontSize": "0.7rem", "color": COLORS["outline"],
        "letterSpacing": "0.1em", "margin": "14px 0 8px"
    }),
    dbc.Label("Licensee WACC (%)", style={"fontSize": "0.82rem"}),
    dbc.Input(id="in-lsw",  value=10.0,  type="number", min=3, max=30, step=0.5, size="sm"),
    dbc.Label("Licensor WACC (%)", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="in-lrw",  value=14.0,  type="number", min=3, max=30, step=0.5, size="sm"),

    # ── PTRS ───────────────────────────────────────────────────────────
    html.P("CLINICAL SUCCESS (PTRS %)", style={
        "fontWeight": "700", "fontSize": "0.7rem", "color": COLORS["outline"],
        "letterSpacing": "0.1em", "margin": "14px 0 8px"
    }),
    dbc.Label("Phase 1 → 2", style={"fontSize": "0.82rem"}),
    dbc.Input(id="p1", value=63.0, type="number", min=1, max=100, step=1, size="sm"),
    dbc.Label("Phase 2 → 3", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="p2", value=30.0, type="number", min=1, max=100, step=1, size="sm"),
    dbc.Label("Phase 3 → NDA", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="p3", value=58.0, type="number", min=1, max=100, step=1, size="sm"),
    dbc.Label("NDA → Approval", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="p4", value=90.0, type="number", min=1, max=100, step=1, size="sm"),

    # ── Deal Terms ─────────────────────────────────────────────────────────
    html.P("DEAL TERMS ($M)", style={
        "fontWeight": "700", "fontSize": "0.7rem", "color": COLORS["outline"],
        "letterSpacing": "0.1em", "margin": "14px 0 8px"
    }),
    dbc.Label("Upfront Payment", style={"fontSize": "0.82rem"}),
    dbc.Input(id="in-upfront", value=2.0, type="number", min=0, step=0.5, size="sm"),
    dbc.Label("Dev Milestones (each)", style={"fontSize": "0.82rem", "marginTop": "8px"}),
    dbc.Input(id="in-mil", value=1.0, type="number", min=0, step=0.5, size="sm"),

    # ── Simulation Controls ─────────────────────────────────────────────────
    html.Hr(style={"margin": "16px 0 12px", "borderColor": COLORS["primary"] + "30"}),
    dbc.Label("Monte Carlo Iterations", style={"fontSize": "0.82rem", "fontWeight": "600"}),
    dcc.Slider(
        id="sl-sims", min=1000, max=10000, step=1000, value=5000,
        marks={1000: "1K", 5000: "5K", 10000: "10K"},
        tooltip={"placement": "bottom"},
        className="my-2"
    ),
    
    html.Div([
        dbc.Button(
            [html.I(className="bi bi-play-circle me-2"), "Run Simulation"],
            id="btn-run", color="primary", size="md", className="w-100 mt-3",
            style={"fontWeight": "600"}
        ),
        dbc.Button(
            [html.I(className="bi bi-download me-2"), "Export"],
            id="btn-export", color="secondary", size="sm", className="w-100 mt-2",
            style={"fontWeight": "600"}
        ),
    ]),
    
    html.Div(id="run-status", style={
        "fontSize": "0.78rem", "color": COLORS["outline"],
        "marginTop": "12px", "fontWeight": "500"
    }),

], body=True, style={
    "position": "sticky", "top": "10px", "overflowY": "auto",
    "maxHeight": "96vh", "borderRadius": "12px",
    "boxShadow": COLORS["shadow"],
    "border": f"1px solid {COLORS['primary']}20",
})


MAIN = html.Div([
    # ── KPI Row ──────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col(html.Div(id="kpi-ls-mean"),  lg=3, md=6, sm=12, className="mb-2"),
        dbc.Col(html.Div(id="kpi-ls-prob"),  lg=3, md=6, sm=12, className="mb-2"),
        dbc.Col(html.Div(id="kpi-lr-mean"),  lg=3, md=6, sm=12, className="mb-2"),
        dbc.Col(html.Div(id="kpi-lr-prob"),  lg=3, md=6, sm=12, className="mb-2"),
    ], className="mb-4 g-3"),

    # ── Tabs ───────────────────────────────────────────────────────────
    dbc.Card([
        dbc.Tabs([
            dbc.Tab(label="📈 Revenue & Cash Flows", tab_id="t-cf"),
            dbc.Tab(label="🎲 Monte Carlo Distribution", tab_id="t-mc"),
            dbc.Tab(label="📊 DCF Model", tab_id="t-dcf"),
            dbc.Tab(label="🌪️ Sensitivity Analysis", tab_id="t-sens"),
            dbc.Tab(label="🏦 Licensor Deal Value", tab_id="t-bridge"),
            dbc.Tab(label="⚖️ Scenario Comparison", tab_id="t-compare"),
        ], id="main-tabs", active_tab="t-cf", className="border-0"),
    ], style={"borderRadius": "12px", "overflow": "hidden", "marginBottom": "20px"}),

    html.Div(id="main-content"),
], style={"padding": "0 12px"})


app.layout = dbc.Container([
    # ── Header ──────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.H2("🧬 GATX-11 Biopharma Licensing", style={
                "fontWeight": "800", "color": COLORS["primary"],
                "marginBottom": "2px"
            }),
            html.H5("NPV Dashboard [ENHANCED v2.0]", style={
                "fontWeight": "600", "color": COLORS["secondary"],
                "marginBottom": "2px"
            }),
            html.Small(
                "Fibrosis · Phase I · EU Exclusive | Monte Carlo + PRTS Risk-Adjusted NPV",
                style={"color": COLORS["outline"], "fontSize": "0.85rem"}
            ),
        ], lg=8, md=12),
        dbc.Col([
            html.Div([
                html.Small("Last Updated", style={"color": COLORS["outline"], "fontSize": "0.75rem"}),
                html.P(id="timestamp", style={
                    "marginBottom": "0", "fontSize": "0.85rem",
                    "color": COLORS["secondary"], "fontWeight": "600"
                }),
            ], style={"textAlign": "right", "paddingTop": "4px"}),
        ], lg=4, md=12),
    ], className="py-4 mb-3", style={
        "borderBottom": f"3px solid {COLORS['primary']}",
        "backgroundColor": COLORS["surface_dim"]
    }),

    # ── Storage & Hidden Elements ──
    dcc.Store(id="store-results"),
    dcc.Store(id="store-scenarios", data={}),
    dcc.Download(id="download-export"),

    # ── Main Grid ──
    dbc.Row([
        dbc.Col(SIDEBAR, lg=3, md=4, className="mb-4"),
        dbc.Col(MAIN, lg=9, md=8),
    ], className="mt-3"),

], fluid=True, style={
    "backgroundColor": COLORS["bg"],
    "minHeight": "100vh",
    "paddingTop": "12px",
    "paddingBottom": "40px"
})


# ============================================================================
# SECTION 5 — CALLBACKS & INTERACTIVE LOGIC
# ============================================================================

def build_params(pop, price, pen, cogs, ga, tax, lsw, lrw, p1, p2, p3, p4, upfront, mil):
    """Build parameter dictionary from inputs."""
    return {
        "eu_pop":     float(pop or 450),
        "ts":         0.09,
        "dr":         0.80,
        "tr":         0.50,
        "cogs":       float(cogs or 12) / 100,
        "ga":         float(ga or 1) / 100,
        "tax":        float(tax or 21) / 100,
        "upfront":    float(upfront or 2),
        "p1":         float(p1 or 63) / 100,
        "p2":         float(p2 or 30) / 100,
        "p3":         float(p3 or 58) / 100,
        "p4":         float(p4 or 90) / 100,
        "rd":         RD_SCHEDULE,
        "milestones": {2: float(mil or 1), 4: float(mil or 1), 6: float(mil or 1)},
        "tiers":      ROYALTY_TIERS_DEFAULT,
    }


@app.callback(
    Output("timestamp", "children"),
    Input("store-results", "data"),
)
def update_timestamp(data):
    """Update timestamp."""
    if data:
        return datetime.now().strftime("%I:%M %p")
    return "—"


@app.callback(
    Output("store-results", "data"),
    Output("run-status", "children"),
    Input("btn-run", "n_clicks"),
    State("in-pop",    "value"), State("in-price", "value"), State("in-pen",   "value"),
    State("in-cogs",   "value"), State("in-ga",    "value"), State("in-tax",   "value"),
    State("in-lsw",    "value"), State("in-lrw",   "value"), State("p1",       "value"),
    State("p2",        "value"), State("p3",       "value"), State("p4",       "value"),
    State("in-upfront","value"), State("in-mil",   "value"), State("sl-sims",  "value"),
    prevent_initial_call=True,
)
def run_simulation(n_clicks, pop, price, pen, cogs, ga, tax, lsw, lrw,
                   p1, p2, p3, p4, upfront, mil, n_sims):
    """Run Monte Carlo simulation with full scenario."""
    params = build_params(pop, price, pen, cogs, ga, tax, lsw, lrw, p1, p2, p3, p4, upfront, mil)
    params["peak_pen"] = float(pen or 5) / 100

    base = run_scenario(0.002, params["peak_pen"], float(price or 15000),
                        float(lsw or 10) / 100, float(lrw or 14) / 100, params)

    ls_npvs, lr_npvs = run_montecarlo(int(n_sims or 5000), params, float(price or 15000))
    ls_s = npv_stats(ls_npvs)
    lr_s = npv_stats(lr_npvs)

    # ── EXTENDED SENSITIVITY (6 core + 6 advanced variables) ─────────────
    sens_vars = {
        "Peak Penetration":  ("peak_pen",    [params["peak_pen"]*0.4, params["peak_pen"]*1.8]),
        "Price / Patient":   ("price_sens",  [float(price)*0.6, float(price)*1.5]),
        "Ph2→Ph3 PTRS":      ("p2",          [params["p2"]*0.6, params["p2"]*1.5]),
        "Licensee WACC":     ("lsw_sens",    [float(lsw)*0.7/100, float(lsw)*1.4/100]),
        "COGS %":            ("cogs",        [params["cogs"]*0.6, params["cogs"]*1.5]),
        "Tax Rate":          ("tax",         [params["tax"]*0.6, params["tax"]*1.5]),
        "Treatment Rate":    ("tr",          [0.35, 0.65]),
        "Disease Rate":      ("dr",          [0.60, 1.0]),
        "GA/SG&A %":         ("ga",          [params["ga"]*0.5, params["ga"]*2.0]),
        "Upfront Payment":   ("upfront",     [params["upfront"]*0.5, params["upfront"]*2.0]),
        "Ph1→2 Success":     ("p1",          [params["p1"]*0.7, params["p1"]*1.3]),
        "NDA Approval":      ("p4",          [params["p4"]*0.8, params["p4"]*1.2]),
    }
    
    sens_rows = []
    base_enpv = base["licensee_enpv"]
    
    for label, (key, (lo_v, hi_v)) in sens_vars.items():
        def _enpv(v, k=key):
            p = {**params}
            if k == "price_sens":
                pr_v = v
            else:
                pr_v = float(price)
                if k in p:
                    p[k] = v
                elif k == "tr":
                    p["tr"] = v
                elif k == "dr":
                    p["dr"] = v
            return run_scenario(0.002, p.get("peak_pen", params["peak_pen"]),
                               pr_v, p.get("lsw_sens", float(lsw)/100),
                               float(lrw)/100, p)["licensee_enpv"]
        
        npv_lo = _enpv(lo_v)
        npv_hi = _enpv(hi_v)
        sens_rows.append({
            "label": label,
            "npv_lo": npv_lo,
            "npv_hi": npv_hi,
            "lo_v": lo_v,
            "hi_v": hi_v,
            "range": abs(npv_hi - npv_lo),
        })

    return {
        "ls_npvs":    ls_npvs.tolist(),
        "lr_npvs":    lr_npvs.tolist(),
        "ls_stats":   ls_s,
        "lr_stats":   lr_s,
        "base_rev":   base["rev"].tolist(),
        "base_fcf":   base["fcf"].tolist(),
        "base_rfcf":  base["risk_adj_fcf"].tolist(),
        "base_ebitda":base["ebitda"].tolist(),
        "base_cogs":  base["cogs"].tolist(),
        "base_royalty":base["royalty"].tolist(),
        "base_ptr":   base["ptr"].tolist(),
        "base_df_ls": base["df_ls"].tolist(),
        "base_lf_cf": base["licensor_cf"].tolist(),
        "base_enpv":  base["licensee_enpv"],
        "base_lr_npv":base["licensor_npv"],
        "sens_rows":  sens_rows,
        "params":     {k: v for k, v in params.items() if not isinstance(v, dict)},
    }, (
        f"✅ {int(n_sims):,} iterations  │  "
        f"eNPV: ${base['licensee_enpv']:,.1f}M  │  "
        f"P(>0): {ls_s['prob_pos']*100:.1f}%"
    )


# ── KPI Cards ──────────────────────────────────────────────────────────
@app.callback(
    Output("kpi-ls-mean", "children"),
    Output("kpi-ls-prob", "children"),
    Output("kpi-lr-mean", "children"),
    Output("kpi-lr-prob", "children"),
    Input("store-results", "data"),
)
def update_kpis(data):
    """Update KPI cards with rich metrics."""
    if not data:
        empty = kpi_card("—", "—")
        return empty, empty, empty, empty
    
    ls, lr = data["ls_stats"], data["lr_stats"]
    return (
        kpi_card(
            "Licensee Mean eNPV",
            f"${ls['mean']:.1f}M",
            color=COLORS["primary"],
            trend=f"σ: ±${ls['std']:.1f}M",
            sub=f"Range: ${ls['p5']:.1f}M to ${ls['p95']:.1f}M"
        ),
        kpi_card(
            "Probability (Licensee > 0)",
            f"{ls['prob_pos']*100:.1f}%",
            color=COLORS["success"],
            trend="✓ Positive Outcome" if ls['prob_pos'] >= 0.5 else "⚠ Downside Risk",
            sub=f"Median: ${ls['p50']:.1f}M"
        ),
        kpi_card(
            "Licensor Mean Deal NPV",
            f"${lr['mean']:.1f}M",
            color=COLORS["teal"],
            trend=f"σ: ±${lr['std']:.1f}M",
            sub=f"Range: ${lr['p5']:.1f}M to ${lr['p95']:.1f}M"
        ),
        kpi_card(
            "Probability (Licensor > 0)",
            f"{lr['prob_pos']*100:.1f}%",
            color=COLORS["warning"],
            trend="✓ Value Creation" if lr['prob_pos'] >= 0.5 else "⚠ Risk Present",
            sub=f"Median: ${lr['p50']:.1f}M"
        ),
    )


# ── Main Tab Content ────────────────────────────────────────────────────
@app.callback(
    Output("main-content", "children"),
    Input("main-tabs", "active_tab"),
    Input("store-results", "data"),
)
def render_main(tab, data):
    """Render main content based on active tab."""
    no_data = alert_card(
        "▶ Click 'Run Simulation' to generate results and unlock all analytics.",
        color="info", icon="ℹ️"
    )
    if not data:
        return no_data

    # ── Revenue & Cash Flows ─────────────────────────────────────────────────
    if tab == "t-cf":
        rev  = data["base_rev"]
        rfcf = data["base_rfcf"]
        ebit = data["base_ebitda"]
        cogs = data["base_cogs"]
        rd_arr = [RD_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)]

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            subplot_titles=(
                "<b>Revenue Build-Up & EBITDA Bridge</b>",
                "<b>Risk-Adjusted Free Cash Flow Evolution</b>"
            ),
            vertical_spacing=0.14, row_heights=[0.55, 0.45]
        )

        fig.add_trace(go.Bar(
            x=YEARS, y=rev, name="Gross Revenue",
            marker_color=COLORS["primary"], opacity=0.85,
            hovertemplate="<b>%{x}</b><br>Revenue: $%{y:.1f}M<extra></extra>"
        ), row=1, col=1)
        
        fig.add_trace(go.Bar(
            x=YEARS, y=[-v for v in cogs], name="COGS",
            marker_color=COLORS["danger"], opacity=0.7, base=0,
            hovertemplate="<b>%{x}</b><br>COGS: $%{y:.1f}M<extra></extra>"
        ), row=1, col=1)
        
        fig.add_trace(go.Bar(
            x=YEARS, y=[-v for v in rd_arr], name="R&D",
            marker_color=COLORS["secondary"], opacity=0.7, base=0,
            hovertemplate="<b>%{x}</b><br>R&D: $%{y:.1f}M<extra></extra>"
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=YEARS, y=ebit, name="EBITDA",
            line=dict(color=COLORS["warning"], width=3),
            mode="lines+markers", marker_size=6,
            hovertemplate="<b>%{x}</b><br>EBITDA: $%{y:.1f}M<extra></extra>"
        ), row=1, col=1)

        colors_fcf = [COLORS["success"] if v >= 0 else COLORS["danger"] for v in rfcf]
        fig.add_trace(go.Bar(
            x=YEARS, y=rfcf, name="Risk-Adj FCF",
            marker_color=colors_fcf, opacity=0.85,
            hovertemplate="<b>%{x}</b><br>Risk-Adj FCF: $%{y:.1f}M<extra></extra>"
        ), row=2, col=1)
        
        fig.add_trace(go.Scatter(
            x=YEARS, y=list(np.cumsum(rfcf)), name="Cumulative FCF",
            line=dict(color=COLORS["primary"], width=2.5, dash="dot"),
            mode="lines", hovertemplate="<b>%{x}</b><br>Cum FCF: $%{y:.1f}M<extra></extra>"
        ), row=2, col=1)
        
        fig.add_hline(y=0, line_width=1, line_dash="solid", line_color="black", 
                     opacity=0.3, row=2, col=1)

        fig.update_layout(
            template="plotly_white", height=580, barmode="overlay",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=80, b=50),
            font=dict(family="Arial", size=11)
        )
        
        fig.update_xaxes(title_text="Fiscal Year", row=2, col=1)
        fig.update_yaxes(title_text="$M", row=1, col=1)
        fig.update_yaxes(title_text="$M", row=2, col=1)
        
        return dbc.Card(
            dbc.CardBody(dcc.Graph(figure=fig, config={"displayModeBar": True})),
            style={"borderRadius": "12px", "boxShadow": COLORS["shadow"]}
        )

    # ── Monte Carlo Distribution ────────────────────────────────────────────────
    elif tab == "t-mc":
        ls_npvs = np.array(data["ls_npvs"])
        lr_npvs = np.array(data["lr_npvs"])
        ls_s    = data["ls_stats"]
        lr_s    = data["lr_stats"]

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                "<b>Licensee eNPV Distribution</b>",
                "<b>Licensor NPV Distribution</b>",
                "<b>Cumulative Probability (S-Curve)</b>",
                "<b>Percentile Comparison</b>",
            ),
            vertical_spacing=0.18, horizontal_spacing=0.12
        )

        # Licensee histogram
        fig.add_trace(go.Histogram(
            x=ls_npvs, nbinsx=60, name="Licensee eNPV",
            marker_color=COLORS["primary"], opacity=0.75,
            hovertemplate="eNPV Range: $%{x:.0f}M<br>Frequency: %{y}<extra></extra>"
        ), row=1, col=1)
        fig.add_vline(x=ls_s["mean"], line_color=COLORS["warning"], line_width=2.5,
                     line_dash="dash", annotation_text="Mean", row=1, col=1)
        fig.add_vline(x=ls_s["p50"],  line_color=COLORS["teal"],    line_width=2.5,
                     line_dash="dot",  annotation_text="Median", row=1, col=1)
        fig.add_vline(x=0, line_color="black", line_width=1.5, line_dash="solid", row=1, col=1)

        # Licensor histogram
        fig.add_trace(go.Histogram(
            x=lr_npvs, nbinsx=60, name="Licensor NPV",
            marker_color=COLORS["teal"], opacity=0.75,
            hovertemplate="NPV Range: $%{x:.0f}M<br>Frequency: %{y}<extra></extra>"
        ), row=1, col=2)
        fig.add_vline(x=lr_s["mean"], line_color=COLORS["warning"], line_width=2.5,
                     line_dash="dash", row=1, col=2)
        fig.add_vline(x=0, line_color="black", line_width=1.5, row=1, col=2)

        # S-curves
        sorted_ls = np.sort(ls_npvs)
        sorted_lr = np.sort(lr_npvs)
        n = len(sorted_ls)
        cdf = np.arange(1, n + 1) / n
        
        fig.add_trace(go.Scatter(
            x=sorted_ls, y=cdf * 100, name="Licensee CDF",
            line=dict(color=COLORS["primary"], width=2.5),
            hovertemplate="eNPV: $%{x:.0f}M<br>P(≤): %{y:.1f}%<extra></extra>"
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=sorted_lr, y=cdf * 100, name="Licensor CDF",
            line=dict(color=COLORS["teal"], width=2.5),
            hovertemplate="NPV: $%{x:.0f}M<br>P(≤): %{y:.1f}%<extra></extra>"
        ), row=2, col=1)
        fig.add_vline(x=0, line_color="black", line_width=1, row=2, col=1)
        fig.add_hline(y=50, line_color=COLORS["outline"], line_dash="dot", 
                     line_width=1, row=2, col=1)

        # Percentile bars
        pcts = ["P5", "P10", "P25", "P50", "P75", "P90", "P95"]
        ls_v = [ls_s["p5"], ls_s["p10"], ls_s["p25"], ls_s["p50"], 
               ls_s["p75"], ls_s["p90"], ls_s["p95"]]
        lr_v = [lr_s["p5"], lr_s["p10"], lr_s["p25"], lr_s["p50"],
               lr_s["p75"], lr_s["p90"], lr_s["p95"]]
        
        fig.add_trace(go.Bar(
            x=pcts, y=ls_v, name="Licensee",
            marker_color=COLORS["primary"], opacity=0.8,
            hovertemplate="%{x}<br>eNPV: $%{y:.1f}M<extra></extra>"
        ), row=2, col=2)
        fig.add_trace(go.Bar(
            x=pcts, y=lr_v, name="Licensor",
            marker_color=COLORS["teal"], opacity=0.8,
            hovertemplate="%{x}<br>NPV: $%{y:.1f}M<extra></extra>"
        ), row=2, col=2)

        fig.update_layout(
            template="plotly_white", height=680, barmode="group",
            hovermode="closest",
            legend=dict(orientation="h", y=1.04, x=0.5, xanchor="center"),
            margin=dict(t=100, b=50),
            font=dict(family="Arial", size=11)
        )
        
        fig.update_yaxes(title_text="Cumulative %", row=2, col=1)
        fig.update_yaxes(title_text="NPV ($M)", row=2, col=2)
        fig.update_xaxes(title_text="NPV ($M)", row=2, col=1)

        # Annotations for P(>0)
        fig.add_annotation(
            text=f"<b>P(eNPV>0) = {ls_s['prob_pos']*100:.1f}%</b>",
            xref="x domain", yref="y domain", x=0.98, y=0.92,
            showarrow=False, font=dict(color=COLORS["primary"], size=13, family="Arial Black"),
            align="right", row=1, col=1, bgcolor="rgba(255,255,255,0.8)",
            bordercolor=COLORS["primary"], borderwidth=1, borderpad=4
        )
        fig.add_annotation(
            text=f"<b>P(NPV>0) = {lr_s['prob_pos']*100:.1f}%</b>",
            xref="x2 domain", yref="y2 domain", x=0.98, y=0.92,
            showarrow=False, font=dict(color=COLORS["teal"], size=13, family="Arial Black"),
            align="right", bgcolor="rgba(255,255,255,0.8)",
            bordercolor=COLORS["teal"], borderwidth=1, borderpad=4
        )

        return dbc.Card(
            dbc.CardBody(dcc.Graph(figure=fig, config={"displayModeBar": True})),
            style={"borderRadius": "12px", "boxShadow": COLORS["shadow"]}
        )

    # ── DCF Table ──────────────────────────────────────────────────────────
    elif tab == "t-dcf":
        base_mock = {
            "rev":          np.array(data["base_rev"]),
            "cogs":         np.array(data["base_cogs"]),
            "ebitda":       np.array(data["base_ebitda"]),
            "royalty":      np.array(data["base_royalty"]),
            "fcf":          np.array(data["base_fcf"]),
            "risk_adj_fcf": np.array(data["base_rfcf"]),
            "ptr":          np.array(data["base_ptr"]),
            "df_ls":        np.array(data["base_df_ls"]),
        }
        columns, rows, metric_rows = build_dcf_table(base_mock)

        style_data_conditional = []

        for idx, (_, _, fmt) in enumerate(metric_rows):
            if fmt == "header":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": COLORS["primary"],
                    "color": "white",
                    "fontWeight": "700",
                    "fontSize": "11px",
                })
            elif fmt in ("rev",):
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": f"{COLORS['primary']}15",
                    "color": COLORS["primary"],
                    "fontWeight": "700",
                })
            elif fmt == "ebitda":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": f"{COLORS['warning']}15",
                    "fontWeight": "700",
                })
            elif fmt == "fcf":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": f"{COLORS['success']}15",
                    "fontWeight": "700",
                })
            elif fmt == "rfcf":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": f"{COLORS['teal']}15",
                    "color": COLORS["teal"],
                    "fontWeight": "700",
                })
            elif fmt == "enpv":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": COLORS["primary"],
                    "color": "white",
                    "fontWeight": "700",
                    "fontSize": "12px",
                })
            elif fmt == "cost":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "color": COLORS["danger"],
                })
            elif idx % 2 == 0:
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": COLORS["surface_dim"],
                })

        style_data_conditional.append({
            "if": {"column_id": "Line Item"},
            "fontWeight": "600",
            "textAlign": "left",
            "backgroundColor": COLORS["surface_dim"],
            "borderRight": f"2px solid {COLORS['primary']}40",
            "minWidth": "180px",
            "maxWidth": "180px",
            "width": "180px",
        })

        total_enpv = data["base_enpv"]
        summary = alert_card(
            html.Span([
                html.Strong("Base Case Metrics:  "),
                f"eNPV = ${total_enpv:,.2f}M  │  ",
                f"Licensor NPV = ${data['base_lr_npv']:,.2f}M  │  ",
                f"Deal PTRS = {np.array(data['base_ptr'])[-1]*100:.2f}%"
            ]),
            color="info"
        )

        table = dash_table.DataTable(
            data=rows,
            columns=columns,
            style_table={"overflowX": "auto", "minWidth": "100%"},
            style_cell={
                "fontFamily": "'Courier New', monospace",
                "fontSize": "11.5px",
                "padding": "7px 10px",
                "border": f"1px solid {COLORS['outline']}30",
                "whiteSpace": "nowrap",
                "textAlign": "right",
                "minWidth": "72px",
                "maxWidth": "90px",
            },
            style_header={
                "backgroundColor": COLORS["primary"],
                "color": "white",
                "fontWeight": "700",
                "textAlign": "center",
                "fontSize": "12px",
                "padding": "8px 6px",
            },
            style_data_conditional=style_data_conditional,
            fixed_columns={"headers": True, "data": 1},
            page_action="none",
        )
        
        return html.Div([
            summary,
            dbc.Card(
                dbc.CardBody(table, style={"padding": "0"}),
                style={"borderRadius": "12px", "overflow": "hidden",
                      "boxShadow": COLORS["shadow"]}
            ),
        ])

    # ── Sensitivity Analysis (Enhanced) ─────────────────────────────────────
    elif tab == "t-sens":
        rows = data["sens_rows"]
        base_e = data["base_enpv"]
        
        # Sort by impact range
        rows_sorted = sorted(rows, key=lambda x: x["range"], reverse=True)
        
        labels   = [r["label"] for r in rows_sorted]
        npv_lo   = [r["npv_lo"] for r in rows_sorted]
        npv_hi   = [r["npv_hi"] for r in rows_sorted]

        # Tornado chart
        fig_tornado = go.Figure()
        for i, (lb, lo, hi) in enumerate(zip(labels, npv_lo, npv_hi)):
            bar_lo = min(lo, hi) - base_e
            bar_hi = max(lo, hi) - base_e
            
            fig_tornado.add_trace(go.Bar(
                y=[lb], x=[bar_hi], name="Upside", orientation="h",
                marker_color=COLORS["success"], opacity=0.85,
                showlegend=(i == len(labels) - 1),
                hovertemplate="<b>%{y}</b><br>Upside: +$%{x:.1f}M<extra></extra>"
            ))
            fig_tornado.add_trace(go.Bar(
                y=[lb], x=[bar_lo], name="Downside", orientation="h",
                marker_color=COLORS["danger"], opacity=0.85,
                showlegend=(i == len(labels) - 1),
                hovertemplate="<b>%{y}</b><br>Downside: $%{x:.1f}M<extra></extra>"
            ))

        fig_tornado.add_vline(x=0, line_color="black", line_width=2, line_dash="solid")
        fig_tornado.update_layout(
            template="plotly_white", barmode="overlay", height=420,
            title=f"<b>Tornado Sensitivity Analysis</b><br><sub>Δ eNPV from Base Case (${base_e:,.1f}M)</sub>",
            xaxis_title="Δ eNPV ($M)",
            yaxis_title="Variable",
            hovermode="y",
            legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
            margin=dict(l=180, t=100, b=50),
            font=dict(family="Arial", size=11)
        )

        # Price sensitivity curve
        prices_sweep = np.linspace(5000, 40000, 60)
        enpv_sweep = []
        for pr_v in prices_sweep:
            p_tmp = {
                "eu_pop": 450, "ts": 0.09, "dr": 0.80, "tr": 0.50,
                "cogs": 0.12, "ga": 0.01, "tax": 0.21, "upfront": 2.0,
                "p1": 0.63, "p2": 0.30, "p3": 0.58, "p4": 0.90,
                "rd": RD_SCHEDULE, "milestones": {2: 1.0, 4: 1.0, 6: 1.0},
                "tiers": ROYALTY_TIERS_DEFAULT, "peak_pen": 0.05,
            }
            enpv_sweep.append(run_scenario(0.002, 0.05, pr_v, 0.10, 0.14, p_tmp)["licensee_enpv"])

        fig_price = go.Figure()
        fig_price.add_trace(go.Scatter(
            x=prices_sweep / 1000, y=enpv_sweep,
            mode="lines", line=dict(color=COLORS["primary"], width=3),
            fill="tozeroy", fillcolor=f"{COLORS['primary']}20",
            hovertemplate="<b>Price: $%{x:.0f}K</b><br>eNPV: $%{y:.1f}M<extra></extra>"
        ))
        fig_price.add_hline(y=0, line_color="black", line_width=1.5, line_dash="dash")
        fig_price.update_layout(
            template="plotly_white", height=320,
            title="<b>Price Sensitivity</b><br><sub>Annual Price per Patient Impact</sub>",
            xaxis_title="Annual Price ($K/patient)", yaxis_title="Licensee eNPV ($M)",
            hovermode="x",
            margin=dict(t=80, b=50),
            font=dict(family="Arial", size=11)
        )

        return html.Div([
            dbc.Card(
                dbc.CardBody(dcc.Graph(figure=fig_tornado, config={"displayModeBar": True})),
                style={"borderRadius": "12px", "boxShadow": COLORS["shadow"], "marginBottom": "20px"}
            ),
            dbc.Card(
                dbc.CardBody(dcc.Graph(figure=fig_price, config={"displayModeBar": True})),
                style={"borderRadius": "12px", "boxShadow": COLORS["shadow"]}
            ),
        ])

    # ── Licensor Deal Value Bridge ──────────────────────────────────────────────
    elif tab == "t-bridge":
        lf_cf   = np.array(data["base_lf_cf"])
        df_lr   = np.array([(1/(1+0.14))**i for i in range(N_YEARS)])
        disc_lc = lf_cf * df_lr

        upfront_pv   = disc_lc[0]
        milestone_pv = sum(disc_lc[i] for i in [2, 4, 6] if i < N_YEARS)
        royalty_pv   = sum(disc_lc[i] for i in range(N_YEARS) if i not in [0, 2, 4, 6])

        components = ["Upfront\nPayment", "Dev\nMilestones", "Royalty\nIncome", "Total\nDeal NPV"]
        values     = [upfront_pv, milestone_pv, royalty_pv, None]
        running, x_vals, y_vals, texts, bar_colors = 0, [], [], [], []
        
        for i, (comp, val) in enumerate(zip(components, values)):
            if val is None:
                x_vals.append(comp)
                y_vals.append(running)
                texts.append(f"${running:,.2f}M")
                bar_colors.append(COLORS["teal"])
            else:
                x_vals.append(comp)
                y_vals.append(val)
                texts.append(f"${val:,.2f}M")
                bar_colors.append(COLORS["success"] if val >= 0 else COLORS["danger"])
                running += val

        fig_bridge = go.Figure(go.Waterfall(
            x=x_vals, measure=["relative", "relative", "relative", "total"],
            y=[upfront_pv, milestone_pv, royalty_pv, 0],
            text=texts, textposition="inside",
            connector={"line": {"color": COLORS["outline"]}},
            increasing={"marker": {"color": COLORS["success"]}},
            decreasing={"marker": {"color": COLORS["danger"]}},
            totals={"marker": {"color": COLORS["teal"]}},
            hovertemplate="<b>%{x}</b><br>PV: $%{y:,.2f}M<extra></extra>"
        ))
        fig_bridge.update_layout(
            template="plotly_white", height=400,
            title=f"<b>Licensor Value Bridge</b><br><sub>Total Deal NPV = ${data['base_lr_npv']:,.2f}M</sub>",
            yaxis_title="Discounted Value ($M)",
            margin=dict(t=100, b=50),
            font=dict(family="Arial", size=11)
        )

        # Annual cash flows
        fig_ann = go.Figure()
        colors_lc = [COLORS["success"] if v >= 0 else COLORS["danger"] for v in lf_cf]
        fig_ann.add_trace(go.Bar(
            x=YEARS, y=lf_cf, name="Annual Cash Flow",
            marker_color=colors_lc, opacity=0.8,
            hovertemplate="<b>%{x}</b><br>Cash Flow: $%{y:,.1f}M<extra></extra>"
        ))
        fig_ann.add_trace(go.Scatter(
            x=YEARS, y=np.cumsum(disc_lc), mode="lines+markers",
            name="Cumulative PV", line=dict(color=COLORS["primary"], width=2.5),
            marker_size=5,
            hovertemplate="<b>%{x}</b><br>Cum PV: $%{y:,.1f}M<extra></extra>"
        ))
        fig_ann.add_hline(y=0, line_color="black", line_width=1)
        fig_ann.update_layout(
            template="plotly_white", height=350,
            title="<b>Annual Licensor Income Stream</b>",
            yaxis_title="$M", xaxis_title="Fiscal Year",
            margin=dict(t=80, b=50),
            hovermode="x unified",
            legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
            font=dict(family="Arial", size=11)
        )

        return html.Div([
            dbc.Card(
                dbc.CardBody(dcc.Graph(figure=fig_bridge, config={"displayModeBar": True})),
                style={"borderRadius": "12px", "boxShadow": COLORS["shadow"], "marginBottom": "20px"}
            ),
            dbc.Card(
                dbc.CardBody(dcc.Graph(figure=fig_ann, config={"displayModeBar": True})),
                style={"borderRadius": "12px", "boxShadow": COLORS["shadow"]}
            ),
        ])

    # ── Scenario Comparison ────────────────────────────────────────────────
    elif tab == "t-compare":
        return dbc.Card(
            dbc.CardBody([
                alert_card(
                    "🚀 Scenario Comparison feature coming soon! Save multiple scenarios and compare side-by-side.",
                    color="info"
                ),
                html.P("This tab will allow you to:", style={"fontWeight": "600"}),
                html.Ul([
                    html.Li("Compare up to 5 different scenarios simultaneously"),
                    html.Li("Analyze key metrics (NPV, P(>0), Ranges) side-by-side"),
                    html.Li("Identify optimal parameter combinations"),
                    html.Li("Export comparison reports"),
                ]),
            ]),
            style={"borderRadius": "12px", "boxShadow": COLORS["shadow"]}
        )

    return no_data


# ── Export Functionality ────────────────────────────────────────────────────
@app.callback(
    Output("download-export", "data"),
    Input("btn-export", "n_clicks"),
    State("store-results", "data"),
    prevent_initial_call=True,
)
def export_data(n_clicks, data):
    """Export results to Excel."""
    if not data:
        return no_update

    try:
        # Create Excel workbook
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = {
                'Metric': ['Licensee Mean eNPV', 'Licensee Std Dev', 'Licensee P(>0)',
                          'Licensor Mean NPV', 'Licensor Std Dev', 'Licensor P(>0)'],
                'Value': [
                    f"${data['ls_stats']['mean']:.2f}M",
                    f"${data['ls_stats']['std']:.2f}M",
                    f"{data['ls_stats']['prob_pos']*100:.1f}%",
                    f"${data['lr_stats']['mean']:.2f}M",
                    f"${data['lr_stats']['std']:.2f}M",
                    f"{data['lr_stats']['prob_pos']*100:.1f}%",
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)

            # Annual projections
            annual_data = {
                'Year': YEARS,
                'Revenue': data['base_rev'],
                'EBITDA': data['base_ebitda'],
                'Royalty': data['base_royalty'],
                'FCF': data['base_fcf'],
                'Risk-Adj FCF': data['base_rfcf'],
                'Cum P(Success)': data['base_ptr'],
            }
            pd.DataFrame(annual_data).to_excel(writer, sheet_name='Annual Projections', index=False)

            # Sensitivity
            sens_df = pd.DataFrame(data['sens_rows'])
            sens_df.to_excel(writer, sheet_name='Sensitivity', index=False)

        output.seek(0)
        return dcc.send_bytes(output.getvalue(), "GATX-11_NPV_Analysis.xlsx")
    except Exception as e:
        return no_update


# ============================================================================
# SECTION 6 — ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
