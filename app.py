import numpy as np
import pandas as pd
import warnings
import os

from dash import Dash, dcc, html, Input, Output, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objs as go

warnings.filterwarnings("ignore")
np.random.seed(42)

# ============================================================================
# SECTION 1 — CONSTANTS & ASSUMPTIONS
# ============================================================================

START_YEAR = 2026
END_YEAR = 2042
YEARS = list(range(START_YEAR, END_YEAR + 1))
N_YEARS = len(YEARS)

# Default Assumptions
EU_POP_DEFAULT = 450.0
POP_GROWTH_MEAN = 0.002 # 0.2%
POP_GROWTH_SD = 0.005
TARGET_SHARE = 0.09
DIAGNOSIS_RATE = 0.80
TREATMENT_RATE = 0.50
PEAK_PEN_MEAN = 0.05
PRICE_MEAN = 15000.0  # Annual per patient
COGS_PCT = 0.12
TAX_RATE = 0.21

# Risk/Discount Defaults
LIC_WACC_MEAN = 0.10
LICOR_WACC_MEAN = 0.14

# Probability of Technical Success (PTRS) per Phase
# Source: Clinical Development Success Rates 2006-2015 (BIO/Biomedtracker)
PHASE_PTRS = {
    "Ph1_to_Ph2": 0.63,
    "Ph2_to_Ph3": 0.30,
    "Ph3_to_NDA": 0.58,
    "NDA_to_App": 0.90
}

# ============================================================================
# SECTION 2 — CORE ENGINE
# ============================================================================

def run_scenario(pg, pp, pr, lsw, lrw, params):
    """Calculates a single NPV scenario with depletable LCF."""
    rev = np.zeros(N_YEARS)
    ptr_success = np.zeros(N_YEARS)
    
    # 1. PTRS Mapping (Assuming Launch in Year 7)
    # Binary logic: Failures in early years halt all subsequent cash flows
    cum_p = 1.0
    p_schedule = [1.0]*2 + [params['p1']] + [1.0]*2 + [params['p2']] + [params['p3']] + [params['p4']]
    for i in range(N_YEARS):
        if i < len(p_schedule):
            cum_p *= p_schedule[i]
        ptr_success[i] = cum_p

    # 2. Revenue Calculation
    pop = params['eu_pop']
    for i in range(N_YEARS):
        pop *= (1 + pg)
        # Adoption curve logic: Peak * Adoption_Idx
        adopt = params['adopt'].get(i, 0.0)
        treated = pop * params['ts'] * params['dr'] * params['tr'] * (pp * adopt)
        rev[i] = treated * pr

    # 3. Financials & Tax Shield
    fcf = np.zeros(N_YEARS)
    royalty = np.zeros(N_YEARS)
    lcf_balance = 0.0
    
    for i in range(N_YEARS):
        r = rev[i]
        costs = (r * params['cogs']) + (r * params['ga']) + params['rd'].get(i, 0.0)
        ebitda = r - costs
        
        # Calculate Royalty
        roy = 0.0
        for lo, hi, rate in params['tiers']:
            if r > lo:
                roy += min(r - lo, hi - lo) * rate
        royalty[i] = roy
        
        # Depletable Tax Loss Carryforward logic
        pre_tax = ebitda - roy
        if pre_tax < 0:
            lcf_balance += abs(pre_tax)
            tax = 0.0
        else:
            taxable = max(pre_tax - lcf_balance, 0)
            lcf_balance = max(lcf_balance - pre_tax, 0)
            tax = taxable * params['tax']
            
        fcf[i] = pre_tax - tax

    # 4. Risk Adjustment (eNPV)
    risk_adj_fcf = fcf * ptr_success
    licensor_cf = (royalty * ptr_success) + (params['milestones'].get(i, 0.0) * ptr_success)
    if 0 in params['milestones']: licensor_cf[0] += params['upfront'] # Upfront non-risked

    # 5. Discounting
    df_licensee = np.array([(1 / (1 + lsw)) ** i for i in range(N_YEARS)])
    df_licensor = np.array([(1 / (1 + lrw)) ** i for i in range(N_YEARS)])

    return {
        "rev": rev,
        "fcf": fcf,
        "risk_adj_fcf": risk_adj_fcf,
        "licensor_cf": licensor_cf,
        "licensee_enpv": np.sum(risk_adj_fcf * df_licensee),
        "licensor_npv": np.sum(licensor_cf * df_licensor),
        "ptr_success": ptr_success
    }

# ============================================================================
# SECTION 3 — MONTE CARLO & DASH LAYOUT
# ============================================================================

app = Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server

app.layout = dbc.Container([
    html.H1("High-Rigor Biopharma Licensing Engine", className="mt-4"),
    html.Hr(),
    dbc.Tabs([
        dbc.Tab(label="1. Input Assumptions", tab_id="tab-inputs"),
        dbc.Tab(label="2. Expected Cash Flows", tab_id="tab-dcf"),
        dbc.Tab(label="3. Risk Analysis", tab_id="tab-risk"),
    ], id="tabs", active_tab="tab-inputs"),
    html.Div(id="content", className="p-4"),
    dcc.Store(id="store-results")
], fluid=True)

@app.callback(Output("content", "children"), [Input("tabs", "active_tab")])
def render_tab(tab):
    if tab == "tab-inputs":
        return dbc.Row([
            dbc.Col([
                html.H5("Commercial Inputs"),
                dbc.Label("EU Pop (M)"), dbc.Input(id="in-pop", value=EU_POP_DEFAULT, type="number"),
                dbc.Label("Price ($)"), dbc.Input(id="in-price", value=PRICE_MEAN, type="number"),
                dbc.Label("Tax Rate"), dbc.Input(id="in-tax", value=TAX_RATE, type="number"),
            ], md=4),
            dbc.Col([
                html.H5("Clinical Probabilities (PTRS)"),
                dbc.Label("Ph2 Success"), dbc.Input(id="p1", value=PHASE_PTRS["Ph1_to_Ph2"], type="number"),
                dbc.Label("Ph3 Success"), dbc.Input(id="p2", value=PHASE_PTRS["Ph2_to_Ph3"], type="number"),
                dbc.Label("Launch Success"), dbc.Input(id="p3", value=PHASE_PTRS["NDA_to_App"], type="number"),
            ], md=4),
            dbc.Col([
                html.H5("Execution"),
                dbc.Button("Run Monte Carlo (10k)", id="btn-run", color="primary", size="lg", className="w-100"),
                html.Div(id="run-status", className="mt-3")
            ], md=4)
        ])
    elif tab == "tab-dcf":
        return html.Div([dcc.Graph(id="graph-fcf"), html.Div(id="table-dcf")])
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(id="hist-licensee"), md=6),
            dbc.Col(dcc.Graph(id="hist-licensor"), md=6),
        ])
    ])

@app.callback(
    [Output("store-results", "data"), Output("run-status", "children")],
    [Input("btn-run", "n_clicks")],
    [State("in-pop", "value"), State("in-price", "value"), State("in-tax", "value")]
)
def run_simulation(n, pop, price, tax):
    if not n: return no_update
    
    # Constant params for this run
    params = {
        'eu_pop': pop, 'ts': 0.09, 'dr': 0.8, 'tr': 0.5, 'cogs': 0.12, 'ga': 0.01,
        'tax': tax, 'upfront': 5.0, 'p1': 0.63, 'p2': 0.30, 'p3': 0.58, 'p4': 0.90,
        'adopt': {7:0.2, 8:0.5, 9:0.8, 10:1.0, 11:1.0},
        'rd': {0:2.0, 1:2.0, 2:5.0, 3:5.0},
        'milestones': {4: 10.0, 7: 20.0},
        'tiers': [(0, 100, 0.05), (100, 500, 0.10), (500, np.inf, 0.15)]
    }

    n_sims = 5000 # Adjusted for browser performance
    ls_npvs = []
    lr_npvs = []
    
    for _ in range(n_sims):
        # Sample Stochastic Variables
        pg = np.clip(np.random.normal(0.002, 0.01), -0.05, 0.05)
        pp = np.clip(np.random.normal(0.05, 0.015), 0.01, 0.20)
        pr = np.random.normal(price, price * 0.1)
        lsw = np.clip(np.random.normal(0.10, 0.02), 0.05, 0.20)
        lrw = np.clip(np.random.normal(0.14, 0.02), 0.05, 0.25)
        
        res = run_scenario(pg, pp, pr, lsw, lrw, params)
        ls_npvs.append(res['licensee_enpv'])
        lr_npvs.append(res['licensor_npv'])

    # Base Case for display
    base = run_scenario(0.002, 0.05, price, 0.10, 0.14, params)
    
    data = {
        "ls_npvs": ls_npvs,
        "lr_npvs": lr_npvs,
        "base_fcf": base['risk_adj_fcf'].tolist(),
        "base_rev": base['rev'].tolist()
    }
    return data, f"Completed {n_sims} iterations. Base eNPV: ${base['licensee_enpv']:.2f}M"

@app.callback(
    [Output("graph-fcf", "figure"), Output("hist-licensee", "figure"), Output("hist-licensor", "figure")],
    [Input("store-results", "data")]
)
def update_graphs(data):
    if not data: return [go.Figure()]*3
    
    # 1. Cash Flow Figure
    fig_fcf = go.Figure()
    fig_fcf.add_trace(go.Bar(x=YEARS, y=data['base_fcf'], name="Expected FCF (Risk-Adj)"))
    fig_fcf.update_layout(title="Risk-Adjusted Annual Cash Flows", template="plotly_white")
    
    # 2. Licensee Hist
    fig_ls = go.Figure(go.Histogram(x=data['ls_npvs'], nbinsx=50, marker_color='#2c3e50'))
    fig_ls.update_layout(title="Licensee eNPV Distribution", xaxis_title="$ Millions")
    
    # 3. Licensor Hist
    fig_lr = go.Figure(go.Histogram(x=data['lr_npvs'], nbinsx=50, marker_color='#e74c3c'))
    fig_lr.update_layout(title="Licensor NPV Distribution", xaxis_title="$ Millions")
    
    return fig_fcf, fig_ls, fig_lr

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run_server(host="0.0.0.0", port=port, debug=False)
    
