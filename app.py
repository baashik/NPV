"""
GATX-11 Biopharma Licensing NPV Strategist
Optimized Professional Implementation - All-in-One app.py
"""

import os
import io
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output, State, no_update
import dash_bootstrap_components as dbc

# ============================================================================
# ARCHITECTURAL CONSTANTS
# ============================================================================

START_YEAR = 2026
END_YEAR = 2042
YEARS = np.arange(START_YEAR, END_YEAR + 1)
N_YEARS = len(YEARS)

# Adoption Curve: R&D (0-6), Launch (7), Peak (10-12), Erosion (13+)
ADOPTION_CURVE = np.zeros(N_YEARS)
ADOPTION_CURVE[7:13] = [0.2, 0.5, 0.8, 1.0, 1.0, 1.0]
ADOPTION_CURVE[13:] = [0.7, 0.4, 0.2, 0.2]

# R&D Spent Schedule (Ph1-NDA Phase)
RD_SCHEDULE = np.zeros(N_YEARS)
RD_SCHEDULE[0:7] = [2.0, 3.0, 2.0, 3.0, 3.0, 3.0, 2.0]

# ============================================================================
# VECTORIZED NPV ENGINE
# ============================================================================

class NPVEngine:
    @staticmethod
    def calculate(params, n_sims=None):
        """
        Unified calculation engine.
        If n_sims is None, runs deterministic base case.
        If n_sims > 0, runs vectorized Monte Carlo.
        """
        rng = np.random.default_rng(42)
        sim_count = n_sims if n_sims else 1
        
        # 1. Stochastic Variable Sampling (Monte Carlo Mode)
        if n_sims:
            prices = rng.lognormal(np.log(params['price']), 0.15, sim_count).reshape(-1, 1)
            pens = np.clip(rng.normal(params['pen'], 0.015, sim_count), 0.005, 0.25).reshape(-1, 1)
            lsws = rng.normal(params['lsw'], 0.02, sim_count).reshape(-1, 1)
            lrws = lsws + 0.04 # Risk premium for Licensor
        else:
            prices = np.array([[params['price']]])
            pens = np.array([[params['pen']]])
            lsws = np.array([[params['lsw']]])
            lrws = np.array([[params['lrw']]])

        # 2. Vectorized Clinical Logic (PTRS)
        p_milestones = np.array([1.0, params['p1'], 1.0, params['p2'], 1.0, params['p3'], params['p4']])
        cum_ptr = np.cumprod(p_milestones)
        ptr = np.concatenate([cum_ptr, np.full(N_YEARS - len(cum_ptr), cum_ptr[-1])])
        
        # 3. Revenue Modeling
        pop = params['eu_pop'] * (1.002 ** np.arange(N_YEARS))
        market_size = pop * 0.09 * 0.80 * 0.50 # Subgroup * Diag * Treat
        # Result shape: (sim_count, n_years)
        revenue = (market_size * pens) * prices * ADOPTION_CURVE
        
        # 4. Cash Flow Logic
        # Tiered Royalties: 5% < 100M | 7% 100-200M | 9% > 200M
        royalty = (np.minimum(revenue, 100) * 0.05 + 
                   np.maximum(0, np.minimum(revenue - 100, 100)) * 0.07 + 
                   np.maximum(0, revenue - 200) * 0.09)
        
        cogs = revenue * 0.12 # Fixed 12% COGS
        ebitda = revenue - cogs - (revenue * 0.01) - RD_SCHEDULE # - Ga - RD
        fcf = (ebitda - royalty) * (1 - 0.21) # Post-tax at 21%
        risk_adj_fcf = fcf * ptr
        
        # 5. Discounting
        df_ls = (1 / (1 + lsws)) ** np.arange(N_YEARS)
        df_lr = (1 / (1 + lrws)) ** np.arange(N_YEARS)
        
        ls_enpv = np.sum(risk_adj_fcf * df_ls, axis=1)
        
        # Licensor Economics
        licensor_cf = royalty * ptr
        licensor_cf[:, 0] += params['upfront']
        for yr in [2, 4, 6]:
            licensor_cf[:, yr] += params['milestone'] * ptr[yr]
        lr_npv = np.sum(licensor_cf * df_lr, axis=1)
        
        if n_sims:
            return {'ls_sims': ls_enpv, 'lr_sims': lr_npv}
        else:
            return {
                'rev': revenue[0], 'fcf': risk_adj_fcf[0], 'ebitda': ebitda[0],
                'ls_enpv': ls_enpv[0], 'lr_npv': lr_npv[0], 'ptr': ptr
            }

# ============================================================================
# DASH UI DEFINITION
# ============================================================================

app = Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server

# Custom Styles
COLORS = {"primary": "#2C3E50", "secondary": "#18BC9C", "accent": "#E74C3C", "bg": "#F8F9FA"}

app.layout = dbc.Container([
    # Header
    dbc.Row([
        dbc.Col([
            html.Div([
                html.H2("GATX-11 Biopharma Licensing NPV", className="fw-bold mb-0"),
                html.Span("Vectorized Monte Carlo Intelligence", className="text-muted small text-uppercase fw-bold")
            ], className="border-start border-4 border-primary ps-3 mt-4 mb-4")
        ])
    ]),
    
    dbc.Row([
        # Sidebar
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Strategy Inputs", className="fw-bold bg-primary text-white"),
                dbc.CardBody([
                    html.Label("Peak Penetration (%)", className="small fw-bold"),
                    dcc.Slider(0.01, 0.20, 0.01, value=0.05, id="p-pen", marks={0.05: '5%', 0.15: '15%'}),
                    
                    html.Label("Price ($/Patient)", className="small fw-bold mt-3"),
                    dbc.Input(id="p-price", type="number", value=15000, size="sm"),
                    
                    html.Label("Licensee WACC (%)", className="small fw-bold mt-3"),
                    dcc.Slider(0.05, 0.2, 0.01, value=0.10, id="p-wacc"),
                    
                    html.Hr(),
                    html.Label("Deal Terms ($M)", className="small fw-bold text-muted"),
                    dbc.InputGroup([
                        dbc.InputGroupText("Upfront"), dbc.Input(id="p-up", type="number", value=2.0),
                    ], size="sm", className="mb-2"),
                    dbc.InputGroup([
                        dbc.InputGroupText("Milestone"), dbc.Input(id="p-mil", type="number", value=1.0),
                    ], size="sm"),
                    
                    dbc.Button("Run Analysis", id="btn-run", color="primary", className="w-100 mt-4 shadow-sm fw-bold")
                ])
            ], className="border-0 shadow-sm")
        ], lg=3),
        
        # Dashboard Content
        dbc.Col([
            dbc.Row(id="kpi-row", className="mb-4 g-3"),
            
            dbc.Tabs([
                dbc.Tab(label="Deterministic View", tab_id="tab-det", children=[
                    dbc.Card(dbc.CardBody(dcc.Graph(id="graph-det")), className="mt-3 border-0 shadow-sm")
                ]),
                dbc.Tab(label="Risk Simulation", tab_id="tab-sim", children=[
                    dbc.Row([
                        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(id="graph-range")), className="mt-3 border-0 shadow-sm"), lg=7),
                        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(id="graph-scurve")), className="mt-3 border-0 shadow-sm"), lg=5),
                    ])
                ]),
            ], id="tabs", active_tab="tab-det")
        ], lg=9)
    ], className="mb-5")
], fluid=True, style={"backgroundColor": COLORS["bg"], "minHeight": "100vh"})

# ============================================================================
# INTERACTIVITY (CALLBACKS)
# ============================================================================

@app.callback(
    [Output("kpi-row", "children"),
     Output("graph-det", "figure"),
     Output("graph-range", "figure"),
     Output("graph-scurve", "figure")],
    [Input("btn-run", "n_clicks")],
    [State("p-pen", "value"), State("p-price", "value"),
     State("p-wacc", "value"), State("p-up", "value"), State("p-mil", "value")]
)
def update_outputs(n, pen, price, wacc, up, mil):
    params = {
        'eu_pop': 450, 'pen': pen, 'price': price, 'lsw': wacc, 'lrw': wacc + 0.04,
        'p1': 0.63, 'p2': 0.30, 'p3': 0.58, 'p4': 0.90, 'upfront': up, 'milestone': mil
    }
    
    # Run Calculations
    base = NPVEngine.calculate(params)
    mc = NPVEngine.calculate(params, n_sims=5000)
    
    # 1. Generate KPIs
    kpis = [
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Licensee eNPV", className="text-muted small"),
            html.H4(f"${np.mean(mc['ls_sims']):.1f}M", className="text-primary fw-bold")
        ]), className="border-0 shadow-sm border-start border-primary border-4")),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Prob Positivity", className="text-muted small"),
            html.H4(f"{np.mean(mc['ls_sims'] > 0)*100:.1f}%", className="text-success fw-bold")
        ]), className="border-0 shadow-sm border-start border-success border-4")),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Licensor Deal NPV", className="text-muted small"),
            html.H4(f"${np.mean(mc['lr_sims']):.1f}M", className="text-dark fw-bold")
        ]), className="border-0 shadow-sm border-start border-dark border-4")),
    ]
    
    # 2. Main Deterministic Chart
    fig_det = make_subplots(specs=[[{"secondary_y": True}]])
    fig_det.add_trace(go.Bar(x=YEARS, y=base['rev'], name="Revenue", marker_color="#34495E", opacity=0.85))
    fig_det.add_trace(go.Scatter(x=YEARS, y=base['fcf'], name="Post-Tax eFCF", line=dict(color="#E74C3C", width=3)), secondary_y=True)
    fig_det.update_layout(title="Base Case Forecast", template="plotly_white", barmode="overlay")
    
    # 3. Monte Carlo Histogram
    fig_mc = go.Figure()
    fig_mc.add_trace(go.Histogram(x=mc['ls_sims'], nbinsx=40, name="Simulations", marker_color="#18BC9C"))
    fig_mc.add_vline(x=0, line_width=2, line_color="black")
    fig_mc.update_layout(title="Probability Distribution (eNPV)", template="plotly_white")
    
    # 4. S-Curve
    sorted_ls = np.sort(mc['ls_sims'])
    fig_s = go.Figure(go.Scatter(x=sorted_ls, y=np.linspace(0, 100, len(sorted_ls)), name="S-Curve", line=dict(color="#2C3E50")))
    fig_s.add_hline(y=50, line_dash="dot", line_color="gray")
    fig_s.update_layout(title="Cumulative Probability", template="plotly_white", yaxis_title="Percentile (%)")
    
    return kpis, fig_det, fig_mc, fig_s

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=3000, debug=False)
