"""
GATX-11 Biopharma Licensing NPV Dashboard
Licensor (Biotech) ↔ Licensee (Pharma Partner) | EU Exclusive License
"""

import numpy as np
import pandas as pd
import warnings
import os
import json
from datetime import datetime

from dash import Dash, dcc, html, Input, Output, State, no_update, dash_table, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.express as px
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

# ============================================================================
# SECTION 1 — CONSTANTS & DEFAULTS
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
    "primary":      "#6750A4",
    "secondary":    "#625B71",
    "success":      "#2E7D32",
    "warning":      "#F57F17",
    "danger":       "#C62828",
    "info":         "#0288D1",
    "teal":         "#00838F",
    "bg":           "#FFFBFE",
    "card":         "#FFFFFF",
    "blue":         "#1565C0",
    "red":          "#C62828",
    "green":        "#2E7D32",
    "grey":         "#546E7A",
    "amber":        "#F57F17",
}

# ============================================================================
# SECTION 2 — CORE ENGINE
# ============================================================================

def compute_royalty(rev_m, tiers):
    roy = 0.0
    for lo, hi, rate in tiers:
        if rev_m > lo:
            roy += min(rev_m - lo, hi - lo) * rate
    return roy


def run_scenario(pg, pp, pr, lsw, lrw, params):
    """
    Single-scenario NPV engine.
    Returns full annual arrays + scalar NPV metrics.
    """
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

        roy = compute_royalty(r, params["tiers"])
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
        "licensee_enpv":  float(np.sum(risk_adj_fcf * df_ls)),
        "licensor_npv":   float(np.sum(licensor_cf  * df_lr)),
    }


def run_montecarlo(n_sims, params, price):
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
    p = np.percentile(arr, [5, 10, 25, 50, 75, 90, 95])
    return {
        "mean":     float(np.mean(arr)),
        "std":      float(np.std(arr)),
        "min":      float(np.min(arr)),
        "p5":  p[0], "p10": p[1], "p25": p[2], "p50": p[3],
        "p75": p[4], "p90": p[5], "p95": p[6],
        "max":      float(np.max(arr)),
        "prob_pos": float(np.mean(arr > 0)),
    }


def build_dcf_table(base):
    """
    Returns (columns, rows, metric_rows) for a TRANSPOSED DCF table:
      - First column  = metric label (Line Item)
      - Remaining 17 columns = one per year (2026 to 2042)
    Each row is one financial line item; years run left to right.
    """
    rd_arr   = np.array([RD_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)])
    disc_fcf = base["risk_adj_fcf"] * base["df_ls"]

    # Reconstruct approximate population row for display
    pop_row, pop = [], 450.0
    for _ in range(N_YEARS):
        pop *= 1.002
        pop_row.append(pop)

    LABEL_COL = "Line Item"
    year_cols = [str(y) for y in YEARS]

    # (label, values_array_or_None, fmt_key)
    # fmt_key drives number formatting; None values = section header row
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
# SECTION 3 — LAYOUT HELPERS
# ============================================================================

def kpi_card(title, value, color="#1565C0", sub=None):
    children = [
        html.P(title, style={"fontSize": "0.75rem", "color": "#888", "marginBottom": "2px", "fontWeight": "600", "letterSpacing": "0.05em"}),
        html.H4(value, style={"color": color, "marginBottom": "0", "fontWeight": "700"}),
    ]
    if sub:
        children.append(html.Small(sub, style={"color": "#666"}))
    return dbc.Card(dbc.CardBody(children, style={"padding": "12px 16px"}),
                    style={"borderLeft": f"4px solid {color}", "borderRadius": "8px"})


def section_header(title, icon="📊"):
    return html.Div([
        html.Span(icon, style={"marginRight": "8px", "fontSize": "1.1rem"}),
        html.Span(title, style={"fontWeight": "700", "fontSize": "1.05rem", "color": "#1a1a2e"}),
    ], style={"borderBottom": "2px solid #e9ecef", "paddingBottom": "8px", "marginBottom": "16px"})


# ============================================================================
# SECTION 4 — APP LAYOUT
# ============================================================================

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY, dbc.icons.BOOTSTRAP],
    title="GATX-11 Licensing NPV",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server

ACTION_BAR = dbc.Card([
    dbc.Row([
        dbc.Col([
            dbc.Label("Scenario", style={"fontSize": "0.7rem", "fontWeight": "700", "marginBottom": "2px"}),
            dbc.Input(id="scenario-name", value="GATX-11", type="text", size="sm", placeholder="Scenario name"),
        ], md=2),
        dbc.Col([
            dbc.Label("Load Saved", style={"fontSize": "0.7rem", "fontWeight": "700", "marginBottom": "2px"}),
            dbc.Row([
                dbc.Col(dcc.Dropdown(id="load-scenario-dropdown", options=[], placeholder="Select...", style={"fontSize": "0.8rem"}), md=8),
                dbc.Col(dbc.Button("Load", id="btn-load", color="info", size="sm", className="w-100"), md=4),
            ], className="g-1"),
        ], md=3),
        dbc.Col([
            dbc.Label("Simulations", style={"fontSize": "0.7rem", "fontWeight": "700", "marginBottom": "2px"}),
            dcc.Slider(id="sl-sims", min=1000, max=10000, step=1000, value=5000,
                       marks={1000: "1K", 5000: "5K", 10000: "10K"},
                       tooltip={"placement": "bottom"}),
        ], md=4),
        dbc.Col([
            dbc.Label("Actions", style={"fontSize": "0.7rem", "fontWeight": "700", "marginBottom": "2px"}),
            dbc.ButtonGroup([
                dbc.Button([html.I(className="bi bi-play-circle me-1"), "Run"], id="btn-run", color="primary", size="sm"),
                dbc.Button([html.I(className="bi bi-download me-1"), "Save"], id="btn-save", color="success", size="sm"),
                dbc.Button([html.I(className="bi bi-file-earmark-arrow-down me-1"), "Export"], id="btn-export", color="secondary", size="sm"),
                dbc.Button([html.I(className="bi bi-trash me-1"), "Delete"], id="btn-delete", color="danger", size="sm"),
            ], size="sm"),
        ], md=3),
    ], className="g-2 align-items-end"),
    dbc.Row([
        dbc.Col(html.Div(id="run-status", style={"fontSize": "0.78rem", "color": "#555", "minHeight": "20px"}), md=6),
        dbc.Col(html.Div(id="save-status", style={"fontSize": "0.75rem", "color": "#555", "minHeight": "20px"}), md=6, style={"textAlign": "right"}),
    ], className="mt-1"),
], body=True, style={"borderRadius": "10px", "marginBottom": "12px"})


def assumptions_tab_content():
    return dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.P("COMMERCIAL", style={"fontWeight": "700", "fontSize": "0.7rem", "color": "#888", "letterSpacing": "0.1em", "margin": "0 0 8px"}),
                    dbc.Label("EU Population (M)", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="in-pop", value=450.0, type="number", min=100, max=1000, step=10, size="sm"),
                    dbc.Label("Price / Patient ($)", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="in-price", value=15000.0, type="number", min=1000, step=500, size="sm"),
                    dbc.Label("Peak Penetration (%)", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="in-pen", value=5.0, type="number", min=0.5, max=30, step=0.5, size="sm"),
                    dbc.Label("COGS (% of Rev)", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="in-cogs", value=12.0, type="number", min=1, max=50, step=1, size="sm"),
                    dbc.Label("Tax Rate (%)", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="in-tax", value=21.0, type="number", min=0, max=50, step=1, size="sm"),
                ], md=4),
                dbc.Col([
                    html.P("DISCOUNT RATES", style={"fontWeight": "700", "fontSize": "0.7rem", "color": "#888", "letterSpacing": "0.1em", "margin": "0 0 8px"}),
                    dbc.Label("Licensee WACC (%)", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="in-lsw", value=10.0, type="number", min=3, max=30, step=0.5, size="sm"),
                    dbc.Label("Licensor WACC (%)", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="in-lrw", value=14.0, type="number", min=3, max=30, step=0.5, size="sm"),
                    html.Div(style={"height": "16px"}),
                    html.P("CLINICAL SUCCESS (PTRS %)", style={"fontWeight": "700", "fontSize": "0.7rem", "color": "#888", "letterSpacing": "0.1em", "margin": "0 0 8px"}),
                    dbc.Label("Ph1 → Ph2", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="p1", value=63.0, type="number", min=1, max=100, step=1, size="sm"),
                    dbc.Label("Ph2 → Ph3", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="p2", value=30.0, type="number", min=1, max=100, step=1, size="sm"),
                    dbc.Label("Ph3 → NDA", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="p3", value=58.0, type="number", min=1, max=100, step=1, size="sm"),
                    dbc.Label("NDA → Approval", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="p4", value=90.0, type="number", min=1, max=100, step=1, size="sm"),
                ], md=4),
                dbc.Col([
                    html.P("DEAL TERMS ($M)", style={"fontWeight": "700", "fontSize": "0.7rem", "color": "#888", "letterSpacing": "0.1em", "margin": "0 0 8px"}),
                    dbc.Label("Upfront Payment ($M)", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="in-upfront", value=2.0, type="number", min=0, step=0.5, size="sm"),
                    dbc.Label("Ph1/Ph2/Ph3 Milestone ($M each)", style={"fontSize": "0.82rem", "marginTop": "6px"}),
                    dbc.Input(id="in-mil", value=1.0, type="number", min=0, step=0.5, size="sm"),
                    html.Div(style={"height": "16px"}),
                    html.P("ROYALTY TIERS", style={"fontWeight": "700", "fontSize": "0.7rem", "color": "#888", "letterSpacing": "0.1em", "margin": "0 0 8px"}),
                    html.Div([
                        html.P(html.Span("• 5% on first $100M"), style={"fontSize": "0.82rem", "margin": "2px 0"}),
                        html.P(html.Span("• 7% on $100–200M"), style={"fontSize": "0.82rem", "margin": "2px 0"}),
                        html.P(html.Span("• 9% on $200M+"), style={"fontSize": "0.82rem", "margin": "2px 0"}),
                    ]),
                    html.Div(style={"height": "16px"}),
                    html.P("EPIDEMIOLOGY (fixed)", style={"fontWeight": "700", "fontSize": "0.7rem", "color": "#888", "letterSpacing": "0.1em", "margin": "0 0 8px"}),
                    html.Div([
                        html.P(html.Span("• Target Population: 9% of EU"), style={"fontSize": "0.82rem", "margin": "2px 0"}),
                        html.P(html.Span("• Diagnosis Rate: 80%"), style={"fontSize": "0.82rem", "margin": "2px 0"}),
                        html.P(html.Span("• Treatment Rate: 50%"), style={"fontSize": "0.82rem", "margin": "2px 0"}),
                    ]),
                ], md=4),
            ]),
        ]),
    ], style={"borderRadius": "10px"})


MAIN = html.Div([
    # ── KPI Row ──────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col(html.Div(id="kpi-ls-mean"),  md=3),
        dbc.Col(html.Div(id="kpi-ls-prob"),  md=3),
        dbc.Col(html.Div(id="kpi-lr-mean"),  md=3),
        dbc.Col(html.Div(id="kpi-lr-prob"),  md=3),
    ], className="mb-3 g-2"),

    # ── Tabs ───────────────────────────────────────────────────────────
    dbc.Tabs([
        dbc.Tab(label="⚙️ Assumptions",       tab_id="t-assumptions"),
        dbc.Tab(label="📈 Revenue & Cash Flows", tab_id="t-cf"),
        dbc.Tab(label="🎲 Monte Carlo",          tab_id="t-mc"),
        dbc.Tab(label="📊 DCF Table",            tab_id="t-dcf"),
        dbc.Tab(label="🌪️ Tornado / Sensitivity",tab_id="t-sens"),
        dbc.Tab(label="🏦 Licensor Bridge",      tab_id="t-bridge"),
    ], id="main-tabs", active_tab="t-assumptions", className="mb-3"),

    html.Div(id="main-content"),
], style={"padding": "0 8px"})


app.layout = dbc.Container([
    # ── Header ──────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.H3("🧬 GATX-11 Biopharma Licensing — NPV Dashboard",
                    style={"fontWeight": "800", "color": "#1a1a2e", "marginBottom": "2px"}),
            html.Small("Fibrosis · Phase I · EU Exclusive License  |  Licensor ↔ Licensee Monte Carlo Simulation",
                       style={"color": "#666"}),
        ], md=9),
        dbc.Col([
            html.Div("💾 Save & Load Scenarios",
                     style={"textAlign": "right", "color": "#888", "fontSize": "0.78rem", "paddingTop": "18px", "fontWeight": "600"}),
        ], md=3),
    ], className="py-3 mb-2", style={"borderBottom": "3px solid #1565C0"}),

    dbc.Row([
        dbc.Col(ACTION_BAR, md=12),
    ], className="mb-2"),

    dcc.Store(id="store-results"),
    dcc.Store(id="store-scenarios", data={}),
    dcc.Download(id="download-export"),

    dbc.Row([
        dbc.Col(MAIN, md=12),
    ], className="mt-1"),

], fluid=True, style={"backgroundColor": COLORS["bg"], "minHeight": "100vh"})


# ============================================================================
# SECTION 5 — CALLBACKS
# ============================================================================

def build_params(pop, price, pen, cogs, tax, lsw, lrw, p1, p2, p3, p4, upfront, mil):
    return {
        "eu_pop":     float(pop or 450),
        "ts":         0.09,
        "dr":         0.80,
        "tr":         0.50,
        "cogs":       float(cogs or 12) / 100,
        "ga":         0.01,
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


# ── Update dropdown with saved scenarios ────────────────────────────────
@app.callback(
    Output("load-scenario-dropdown", "options"),
    Input("store-scenarios", "data"),
)
def update_scenario_dropdown(scenarios_data):
    if not scenarios_data:
        return []
    return [{"label": name, "value": name} for name in sorted(scenarios_data.keys())]


# ── Load scenario when dropdown changes ──────────────────────────────────
@app.callback(
    Output("in-pop", "value"), Output("in-price", "value"), Output("in-pen", "value"),
    Output("in-cogs", "value"), Output("in-tax", "value"), Output("in-lsw", "value"),
    Output("in-lrw", "value"), Output("p1", "value"), Output("p2", "value"),
    Output("p3", "value"), Output("p4", "value"), Output("in-upfront", "value"),
    Output("in-mil", "value"), Output("scenario-name", "value"),
    Input("btn-load", "n_clicks"),
    State("load-scenario-dropdown", "value"),
    State("store-scenarios", "data"),
    prevent_initial_call=True,
)
def load_scenario(n_clicks, scenario_name, scenarios_data):
    if not scenario_name or not scenarios_data or scenario_name not in scenarios_data:
        return no_update

    s = scenarios_data[scenario_name]
    return (
        s["eu_pop"], s["price"], s["pen"], s["cogs"], s["tax"], s["lsw"],
        s["lrw"], s["p1"], s["p2"], s["p3"], s["p4"], s["upfront"], s["mil"], scenario_name
    )


# ── Run Simulation ───────────────────────────────────────────────────────
@app.callback(
    Output("store-results", "data"),
    Output("run-status", "children"),
    Input("btn-run", "n_clicks"),
    State("in-pop",    "value"), State("in-price", "value"), State("in-pen",   "value"),
    State("in-cogs",   "value"), State("in-tax",   "value"), State("in-lsw",   "value"),
    State("in-lrw",    "value"), State("p1",        "value"), State("p2",       "value"),
    State("p3",        "value"), State("p4",        "value"), State("in-upfront","value"),
    State("in-mil",    "value"), State("sl-sims",   "value"),
    prevent_initial_call=True,
)
def run_simulation(n_clicks, pop, price, pen, cogs, tax, lsw, lrw,
                   p1, p2, p3, p4, upfront, mil, n_sims):
    params = build_params(pop, price, pen, cogs, tax, lsw, lrw, p1, p2, p3, p4, upfront, mil)
    params["peak_pen"] = float(pen or 5) / 100

    base = run_scenario(0.002, params["peak_pen"], float(price or 15000),
                        float(lsw or 10) / 100, float(lrw or 14) / 100, params)

    ls_npvs, lr_npvs = run_montecarlo(int(n_sims or 5000), params, float(price or 15000))
    ls_s = npv_stats(ls_npvs)
    lr_s = npv_stats(lr_npvs)

    # Sensitivity sweep (6 vars × 2 directions)
    sens_vars = {
        "Peak Penetration":  ("peak_pen",    [params["peak_pen"]*0.4, params["peak_pen"]*1.8]),
        "Price / Patient":   ("price_sens",  [float(price)*0.6, float(price)*1.5]),
        "Ph2→Ph3 PTRS":      ("p2",          [params["p2"]*0.6, params["p2"]*1.5]),
        "Licensee WACC":     ("lsw_sens",    [float(lsw)*0.7/100, float(lsw)*1.4/100]),
        "COGS %":            ("cogs",        [params["cogs"]*0.6, params["cogs"]*1.5]),
        "Tax Rate":          ("tax",         [params["tax"]*0.6, params["tax"]*1.5]),
    }
    sens_rows = []
    base_enpv = base["licensee_enpv"]
    for label, (key, (lo_v, hi_v)) in sens_vars.items():
        def _enpv(v, k=key):
            p = {**params}
            if k == "price_sens": pr_v = v
            else: pr_v = float(price); p[k] = v
            return run_scenario(0.002, p.get("peak_pen", params["peak_pen"]),
                                pr_v, p.get("lsw_sens", float(lsw)/100),
                                float(lrw)/100, p)["licensee_enpv"]
        sens_rows.append({
            "label": label,
            "npv_lo": _enpv(lo_v), "npv_hi": _enpv(hi_v),
            "lo_v": lo_v, "hi_v": hi_v,
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
    }, (
        f"✅ {int(n_sims):,} iterations complete │ "
        f"Base eNPV: ${base['licensee_enpv']:.1f}M │ "
        f"P(>0): {ls_s['prob_pos']*100:.1f}%"
    )


# ── Save Scenario ────────────────────────────────────────────────────────
@app.callback(
    Output("store-scenarios", "data"),
    Output("save-status", "children"),
    Input("btn-save", "n_clicks"),
    State("scenario-name", "value"),
    State("in-pop", "value"), State("in-price", "value"), State("in-pen", "value"),
    State("in-cogs", "value"), State("in-tax", "value"), State("in-lsw", "value"),
    State("in-lrw", "value"), State("p1", "value"), State("p2", "value"),
    State("p3", "value"), State("p4", "value"), State("in-upfront", "value"),
    State("in-mil", "value"), State("store-scenarios", "data"),
    prevent_initial_call=True,
)
def save_scenario(n_clicks, scenario_name, pop, price, pen, cogs, tax, lsw, lrw,
                  p1, p2, p3, p4, upfront, mil, scenarios_data):
    if not scenario_name or scenario_name.strip() == "":
        return scenarios_data or {}, "❌ Please enter a scenario name"

    scenario_name = scenario_name.strip()
    scenarios = scenarios_data or {}

    scenarios[scenario_name] = {
        "eu_pop": float(pop or 450),
        "price": float(price or 15000),
        "pen": float(pen or 5),
        "cogs": float(cogs or 12),
        "tax": float(tax or 21),
        "lsw": float(lsw or 10),
        "lrw": float(lrw or 14),
        "p1": float(p1 or 63),
        "p2": float(p2 or 30),
        "p3": float(p3 or 58),
        "p4": float(p4 or 90),
        "upfront": float(upfront or 2),
        "mil": float(mil or 1),
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    return scenarios, f"✅ Saved: {scenario_name} ({len(scenarios)} scenario{'s' if len(scenarios) > 1 else ''})"


# ── Delete Scenario ──────────────────────────────────────────────────────
@app.callback(
    Output("store-scenarios", "data"),
    Output("save-status", "children"),
    Input("btn-delete", "n_clicks"),
    State("load-scenario-dropdown", "value"),
    State("store-scenarios", "data"),
    prevent_initial_call=True,
)
def delete_scenario(n_clicks, scenario_name, scenarios_data):
    if not scenario_name or not scenarios_data or scenario_name not in scenarios_data:
        return scenarios_data or {}, "❌ Select a scenario to delete"

    scenarios = {k: v for k, v in scenarios_data.items() if k != scenario_name}
    return scenarios, f"🗑️ Deleted: {scenario_name}"


# ── Export Scenario as JSON ──────────────────────────────────────────────
@app.callback(
    Output("download-export", "data"),
    Input("btn-export", "n_clicks"),
    State("scenario-name", "value"),
    State("in-pop", "value"), State("in-price", "value"), State("in-pen", "value"),
    State("in-cogs", "value"), State("in-tax", "value"), State("in-lsw", "value"),
    State("in-lrw", "value"), State("p1", "value"), State("p2", "value"),
    State("p3", "value"), State("p4", "value"), State("in-upfront", "value"),
    State("in-mil", "value"), State("store-results", "data"),
    prevent_initial_call=True,
)
def export_scenario(n_clicks, scenario_name, pop, price, pen, cogs, tax, lsw, lrw,
                    p1, p2, p3, p4, upfront, mil, results):
    if not scenario_name:
        scenario_name = "Export"

    export_data = {
        "scenario_name": scenario_name,
        "exported_at": datetime.now().isoformat(),
        "assumptions": {
            "eu_pop": float(pop or 450),
            "price": float(price or 15000),
            "penetration": float(pen or 5),
            "cogs_pct": float(cogs or 12),
            "tax_rate": float(tax or 21),
            "licensee_wacc": float(lsw or 10),
            "licensor_wacc": float(lrw or 14),
            "ph1_to_ph2": float(p1 or 63),
            "ph2_to_ph3": float(p2 or 30),
            "ph3_to_nda": float(p3 or 58),
            "nda_approval": float(p4 or 90),
            "upfront_payment": float(upfront or 2),
            "milestones": float(mil or 1),
        },
        "results": results or {},
    }

    return dcc.send_string(json.dumps(export_data, indent=2), f"{scenario_name}_NPV_Analysis.json")


# ── KPI Cards ──────────────────────────────────────────────────────────
@app.callback(
    Output("kpi-ls-mean", "children"), Output("kpi-ls-prob", "children"),
    Output("kpi-lr-mean", "children"), Output("kpi-lr-prob", "children"),
    Input("store-results", "data"),
)
def update_kpis(data):
    if not data:
        empty = kpi_card("—", "—")
        return empty, empty, empty, empty
    ls, lr = data["ls_stats"], data["lr_stats"]
    return (
        kpi_card("Licensee Mean eNPV",     f"${ls['mean']:.1f}M",   COLORS["blue"],
                 f"P5: ${ls['p5']:.1f}M  |  P95: ${ls['p95']:.1f}M"),
        kpi_card("P(Licensee eNPV > 0)",   f"{ls['prob_pos']*100:.1f}%", COLORS["green"],
                 f"Median: ${ls['p50']:.1f}M"),
        kpi_card("Licensor Mean Deal NPV", f"${lr['mean']:.1f}M",   COLORS["teal"],
                 f"P5: ${lr['p5']:.1f}M  |  P95: ${lr['p95']:.1f}M"),
        kpi_card("P(Licensor NPV > 0)",    f"{lr['prob_pos']*100:.1f}%", COLORS["amber"],
                 f"Median: ${lr['p50']:.1f}M"),
    )


# ── Main Tab Content ────────────────────────────────────────────────────────
@app.callback(
    Output("main-content", "children"),
    Input("main-tabs", "active_tab"),
    Input("store-results", "data"),
)
def render_main(tab, data):
    no_data = dbc.Alert("▶ Click Run Simulation to generate results.", color="info", className="mt-3")

    # ── Assumptions Tab ────────────────────────────────────────────────────
    if tab == "t-assumptions":
        return assumptions_tab_content()

    if not data:
        return no_data

    # ── Revenue & Cash Flows ─────────────────────────────────────────────────
    if tab == "t-cf":
        rev  = data["base_rev"]
        rfcf = data["base_rfcf"]
        ebit = data["base_ebitda"]
        cogs = data["base_cogs"]
        rd_arr = [RD_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)]

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            subplot_titles=("Revenue Build-Up ($M)", "Risk-Adjusted FCF vs EBITDA ($M)"),
                            vertical_spacing=0.12, row_heights=[0.55, 0.45])

        fig.add_trace(go.Bar(x=YEARS, y=rev,  name="Gross Revenue", marker_color=COLORS["blue"],   opacity=0.85), row=1, col=1)
        fig.add_trace(go.Bar(x=YEARS, y=[-v for v in cogs], name="COGS", marker_color=COLORS["red"],   opacity=0.7, base=0), row=1, col=1)
        fig.add_trace(go.Bar(x=YEARS, y=[-v for v in rd_arr], name="R&D", marker_color=COLORS["grey"], opacity=0.7, base=0), row=1, col=1)
        fig.add_trace(go.Scatter(x=YEARS, y=ebit, name="EBITDA", line=dict(color=COLORS["amber"], width=2.5), mode="lines+markers", marker_size=5), row=1, col=1)

        colors_fcf = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in rfcf]
        fig.add_trace(go.Bar(x=YEARS, y=rfcf, name="Risk-Adj FCF", marker_color=colors_fcf, opacity=0.85), row=2, col=1)
        fig.add_trace(go.Scatter(x=YEARS, y=list(np.cumsum(rfcf)), name="Cumulative FCF",
                                 line=dict(color=COLORS["blue"], width=2, dash="dot"), mode="lines"), row=2, col=1)
        fig.add_hline(y=0, line_width=1, line_dash="solid", line_color="black", opacity=0.4, row=2, col=1)

        fig.update_layout(template="plotly_white", height=560, barmode="overlay",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                          margin=dict(t=60, b=40))
        return dbc.Card(dbc.CardBody(dcc.Graph(figure=fig, config={"displayModeBar": False})), style={"borderRadius": "10px"})

    # ── Monte Carlo ────────────────────────────────────────────────────────
    elif tab == "t-mc":
        ls_npvs = data["ls_npvs"]
        lr_npvs = data["lr_npvs"]
        ls_s    = data["ls_stats"]
        lr_s    = data["lr_stats"]

        fig = make_subplots(rows=2, cols=2,
                            subplot_titles=(
                                "Licensee eNPV Distribution",
                                "Licensor NPV Distribution",
                                "Cumulative Probability (S-Curve)",
                                "Percentile Summary",
                            ), vertical_spacing=0.18, horizontal_spacing=0.1)

        # Licensee hist
        fig.add_trace(go.Histogram(x=ls_npvs, nbinsx=60, name="Licensee eNPV",
                                   marker_color=COLORS["blue"], opacity=0.75), row=1, col=1)
        fig.add_vline(x=ls_s["mean"], line_color=COLORS["amber"], line_width=2, line_dash="dash", row=1, col=1)
        fig.add_vline(x=ls_s["p50"],  line_color=COLORS["teal"],  line_width=2, line_dash="dot",  row=1, col=1)
        fig.add_vline(x=0,            line_color="black",          line_width=1,                    row=1, col=1)

        # Licensor hist
        fig.add_trace(go.Histogram(x=lr_npvs, nbinsx=60, name="Licensor NPV",
                                   marker_color=COLORS["teal"], opacity=0.75), row=1, col=2)
        fig.add_vline(x=lr_s["mean"], line_color=COLORS["amber"], line_width=2, line_dash="dash", row=1, col=2)
        fig.add_vline(x=0,            line_color="black",          line_width=1,                    row=1, col=2)

        # S-curve
        sorted_ls = np.sort(ls_npvs)
        sorted_lr = np.sort(lr_npvs)
        n = len(sorted_ls)
        cdf = np.arange(1, n + 1) / n
        fig.add_trace(go.Scatter(x=sorted_ls, y=cdf * 100, name="Licensee CDF",
                                 line=dict(color=COLORS["blue"], width=2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=sorted_lr, y=cdf * 100, name="Licensor CDF",
                                 line=dict(color=COLORS["teal"], width=2)), row=2, col=1)
        fig.add_vline(x=0, line_color="black", line_width=1, row=2, col=1)
        fig.add_hline(y=50, line_color=COLORS["grey"], line_dash="dot", line_width=1, row=2, col=1)

        # Percentile bar chart
        pcts  = ["P5", "P10", "P25", "P50", "P75", "P90", "P95"]
        ls_v  = [ls_s["p5"], ls_s["p10"], ls_s["p25"], ls_s["p50"], ls_s["p75"], ls_s["p90"], ls_s["p95"]]
        lr_v  = [lr_s["p5"], lr_s["p10"], lr_s["p25"], lr_s["p50"], lr_s["p75"], lr_s["p90"], lr_s["p95"]]
        fig.add_trace(go.Bar(x=pcts, y=ls_v, name="Licensee", marker_color=COLORS["blue"], opacity=0.8), row=2, col=2)
        fig.add_trace(go.Bar(x=pcts, y=lr_v, name="Licensor",  marker_color=COLORS["teal"], opacity=0.8), row=2, col=2)

        fig.update_layout(template="plotly_white", height=640, barmode="group",
                          legend=dict(orientation="h", y=1.04, x=0.5, xanchor="center"),
                          margin=dict(t=80, b=40))
        fig.update_yaxes(title_text="Cumulative %",  row=2, col=1)
        fig.update_yaxes(title_text="NPV ($M)",       row=2, col=2)
        fig.update_xaxes(title_text="eNPV ($M)",      row=2, col=1)

        # Annotation for P(>0)
        fig.add_annotation(
            text=f"P(eNPV>0) = {ls_s['prob_pos']*100:.1f}%",
            xref="x domain", yref="y domain", x=0.98, y=0.92,
            showarrow=False, font=dict(color=COLORS["blue"], size=12, family="Arial Black"),
            align="right", row=1, col=1,
        )
        fig.add_annotation(
            text=f"P(NPV>0) = {lr_s['prob_pos']*100:.1f}%",
            xref="x2 domain", yref="y2 domain", x=0.98, y=0.92,
            showarrow=False, font=dict(color=COLORS["teal"], size=12, family="Arial Black"),
            align="right",
        )

        return dbc.Card(dbc.CardBody(dcc.Graph(figure=fig, config={"displayModeBar": False})), style={"borderRadius": "10px"})

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

        # Row-level conditional styles
        style_data_conditional = []

        for idx, (_, _, fmt) in enumerate(metric_rows):
            if fmt == "header":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": "#1a1a2e",
                    "color": "white",
                    "fontWeight": "700",
                    "fontStyle": "normal",
                    "fontSize": "11px",
                    "letterSpacing": "0.05em",
                })
            elif fmt in ("rev",):
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": "#E3F2FD",
                    "color": COLORS["blue"],
                    "fontWeight": "700",
                })
            elif fmt == "ebitda":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": "#F3E5F5",
                    "fontWeight": "700",
                })
            elif fmt == "fcf":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": "#E8F5E9",
                    "fontWeight": "700",
                })
            elif fmt == "rfcf":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": "#E0F7FA",
                    "color": COLORS["teal"],
                    "fontWeight": "700",
                })
            elif fmt == "enpv":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": "#1565C0",
                    "color": "white",
                    "fontWeight": "700",
                    "fontSize": "12px",
                })
            elif fmt == "cost":
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "color": COLORS["red"],
                })
            elif idx % 2 == 0:
                style_data_conditional.append({
                    "if": {"row_index": idx},
                    "backgroundColor": "#FAFAFA",
                })

        style_data_conditional.append({
            "if": {"column_id": "Line Item"},
            "fontWeight": "600",
            "textAlign": "left",
            "backgroundColor": "#F8F9FA",
            "borderRight": "2px solid #dee2e6",
            "minWidth": "180px",
            "maxWidth": "180px",
            "width": "180px",
        })

        total_enpv = data["base_enpv"]
        summary = dbc.Alert([
            html.Strong("Base Case:  "),
            f"Licensee eNPV = ${total_enpv:.2f}M  │  ",
            f"Licensor NPV = ${data['base_lr_npv']:.2f}M  │  ",
            f"Cumulative PTRS = {np.array(data['base_ptr'])[-1]*100:.2f}%  │  ",
            f"Years 2026–2042 (left → right)",
        ], color="primary", className="mb-3")

        table = dash_table.DataTable(
            data=rows,
            columns=columns,
            style_table={
                "overflowX": "auto",
                "minWidth": "100%",
            },
            style_cell={
                "fontFamily": "'Courier New', monospace",
                "fontSize": "11.5px",
                "padding": "5px 9px",
                "border": "1px solid #e9ecef",
                "whiteSpace": "nowrap",
                "textAlign": "right",
                "minWidth": "72px",
                "maxWidth": "90px",
            },
            style_header={
                "backgroundColor": "#1565C0",
                "color": "white",
                "fontWeight": "700",
                "textAlign": "center",
                "border": "1px solid #0d47a1",
                "fontSize": "12px",
                "padding": "7px 6px",
            },
            style_data_conditional=style_data_conditional,
            fixed_columns={"headers": True, "data": 1},
            page_action="none",
        )
        return html.Div([
            summary,
            dbc.Card(dbc.CardBody(table, style={"padding": "0"}),
                     style={"borderRadius": "10px", "overflow": "hidden"}),
        ])

    # ── Tornado / Sensitivity ──────────────────────────────────────────────
    elif tab == "t-sens":
        rows = data["sens_rows"]
        base_e = data["base_enpv"]
        labels   = [r["label"]  for r in rows]
        npv_lo   = [r["npv_lo"] for r in rows]
        npv_hi   = [r["npv_hi"] for r in rows]
        ranges   = [abs(h - l) for l, h in zip(npv_lo, npv_hi)]
        order    = np.argsort(ranges)
        labels   = [labels[i]  for i in order]
        npv_lo   = [npv_lo[i]  for i in order]
        npv_hi   = [npv_hi[i]  for i in order]

        fig = go.Figure()
        for i, (lb, lo, hi) in enumerate(zip(labels, npv_lo, npv_hi)):
            bar_lo = min(lo, hi) - base_e
            bar_hi = max(lo, hi) - base_e
            fig.add_trace(go.Bar(
                y=[lb], x=[bar_hi], name="Upside",   orientation="h",
                marker_color=COLORS["blue"], opacity=0.85,
                showlegend=(i == len(labels) - 1),
            ))
            fig.add_trace(go.Bar(
                y=[lb], x=[bar_lo], name="Downside", orientation="h",
                marker_color=COLORS["red"],  opacity=0.85,
                showlegend=(i == len(labels) - 1),
            ))

        fig.add_vline(x=0, line_color="black", line_width=1.5)
        fig.update_layout(
            template="plotly_white", barmode="overlay", height=380,
            title=f"Tornado — Δ eNPV vs Base Case (${base_e:.1f}M)",
            xaxis_title="Δ eNPV ($M)",
            legend=dict(orientation="h", y=1.08),
            margin=dict(l=160, t=70, b=40),
        )

        # Also add scatter: price sensitivity
        prices_sweep = np.linspace(5000, 40000, 50)
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

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=prices_sweep / 1000, y=enpv_sweep,
                                  mode="lines", line=dict(color=COLORS["blue"], width=2.5),
                                  fill="tozeroy", fillcolor="rgba(21,101,192,0.1)"))
        fig2.add_hline(y=0, line_color="black", line_width=1, line_dash="dash")
        fig2.update_layout(
            template="plotly_white", height=280,
            title="Price Sensitivity: eNPV vs Annual Price per Patient",
            xaxis_title="Price ($K/patient/year)", yaxis_title="Licensee eNPV ($M)",
            margin=dict(t=50, b=40),
        )

        return html.Div([
            dbc.Card(dbc.CardBody(dcc.Graph(figure=fig,  config={"displayModeBar": False})), style={"borderRadius": "10px", "marginBottom": "16px"}),
            dbc.Card(dbc.CardBody(dcc.Graph(figure=fig2, config={"displayModeBar": False})), style={"borderRadius": "10px"}),
        ])

    # ── Licensor Bridge ────────────────────────────────────────────────────
    elif tab == "t-bridge":
        lf_cf   = np.array(data["base_lf_cf"])
        df_lr   = np.array([(1/(1+0.14))**i for i in range(N_YEARS)])
        disc_lc = lf_cf * df_lr

        upfront_pv   = disc_lc[0]
        milestone_pv = sum(disc_lc[i] for i in [2, 4, 6] if i < N_YEARS)
        royalty_pv   = sum(disc_lc[i] for i in range(N_YEARS) if i not in [0, 2, 4, 6] and disc_lc[i] > 0)

        components = ["Upfront\nPayment", "Dev\nMilestones", "Royalty\nIncome", "Total\nDeal NPV"]
        values     = [upfront_pv, milestone_pv, royalty_pv, None]
        running, x_vals, y_vals, texts, bar_colors = 0, [], [], [], []
        for i, (comp, val) in enumerate(zip(components, values)):
            if val is None:
                x_vals.append(comp); y_vals.append(running)
                texts.append(f"${running:.2f}M"); bar_colors.append(COLORS["teal"])
            else:
                x_vals.append(comp); y_vals.append(val)
                texts.append(f"${val:.2f}M")
                bar_colors.append(COLORS["blue"] if val >= 0 else COLORS["red"])
                running += val

        fig_bridge = go.Figure(go.Waterfall(
            x=x_vals,
            measure=["relative", "relative", "relative", "total"],
            y=[upfront_pv, milestone_pv, royalty_pv, 0],
            text=texts,
            textposition="inside",
            connector={"line": {"color": "#ccc"}},
            increasing={"marker": {"color": COLORS["blue"]}},
            decreasing={"marker": {"color": COLORS["red"]}},
            totals={"marker": {"color": COLORS["teal"]}},
        ))
        fig_bridge.update_layout(
            template="plotly_white", height=360,
            title=f"Licensor Deal NPV Bridge — Total = ${data['base_lr_npv']:.2f}M",
            yaxis_title="Discounted Value ($M)",
            margin=dict(t=60, b=40),
        )

        # Annual licensor income bar
        fig_ann = go.Figure()
        colors_lc = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in lf_cf]
        fig_ann.add_trace(go.Bar(x=YEARS, y=lf_cf, name="Licensor Cash Flow",
                                 marker_color=colors_lc, opacity=0.85))
        fig_ann.add_trace(go.Scatter(x=YEARS, y=np.cumsum(disc_lc), mode="lines+markers",
                                     name="Cum. PV of Income", line=dict(color=COLORS["amber"], width=2),
                                     marker_size=4))
        fig_ann.add_hline(y=0, line_color="black", line_width=1)
        fig_ann.update_layout(
            template="plotly_white", height=300,
            title="Annual Licensor Risk-Adjusted Cash Flow",
            yaxis_title="$M", margin=dict(t=50, b=40),
            legend=dict(orientation="h", y=1.06),
        )

        return html.Div([
            dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_bridge, config={"displayModeBar": False})), style={"borderRadius": "10px", "marginBottom": "16px"}),
            dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_ann,    config={"displayModeBar": False})), style={"borderRadius": "10px"}),
        ])

    return no_data


# ============================================================================
# SECTION 6 — ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
