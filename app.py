"""
GATX-11 Biopharma Licensing NPV Dashboard
Complete implementation with Editable DCF, Monte Carlo, and Sensitivity.
"""

import dash
from dash import dcc, html, Input, Output, State, dash_table, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import pandas as pd
import numpy as np

# ============================================================================
# 1. CONSTANTS & INITIAL DATA
# ============================================================================

START_YEAR = 2026
END_YEAR = 2042
YEARS = [str(y) for y in range(START_YEAR, END_YEAR + 1)]
N_YEARS = len(YEARS)

# Base R&D and Pre-marketing costs mapping (in $M)
RD_COSTS = {
    "2026": 4.0, "2027": 4.0,  # Phase 1
    "2028": 5.0, "2029": 5.0,  # Phase 2
    "2030": 7.0, "2031": 7.0,  # Phase 3
    "2032": 1.0                # Approval
}
PRE_MKT_COSTS = {"2032": 1.0}

# Manual Adoption Ramp (as percentage of peak penetration)
ADOPTION_RAMP = [0, 0, 0, 0, 0, 0, 0, 0.6, 0.8, 0.9, 1.0, 1.0, 1.0, 0.7, 0.4, 0.2, 0.2]

# Default Royalty Tiers (Marginal differences to avoid cliffs)
ROYALTY_TIERS = [
    {'threshold': 0, 'rate': 0.05},
    {'threshold': 100, 'rate': 0.02}, # +2% over $100M (Total 7%)
    {'threshold': 200, 'rate': 0.02}  # +2% over $200M (Total 9%)
]

# ============================================================================
# 2. CORE CALCULATION ENGINE
# ============================================================================

def run_dcf_engine(assumptions, overrides=None):
    """Calculates the full DCF and Deal NPVs based on inputs and table overrides."""
    
    df = pd.DataFrame(index=[
        "Total Population (EU)", "Target Patient Population (M)", 
        "Diagnosed Patients (M)", "Treated Patients (M)", 
        "Adoption Ramp", "Market Penetration (%)", "Patients on Therapy (M)",
        "Price Per Unit", "Gross Revenue ($M)", "COGS ($M)", "R&D & Pre-Mkt ($M)", 
        "G&A ($M)", "EBITDA ($M)", "Tax Paid ($M)", "Free Cash Flow (Pre-Deal, $M)", 
        "Licensor Upfront & Milestones ($M)", "Licensor Royalty ($M)", 
        "Total Licensor Income ($M)", "Cum. Prob. of Success", 
        "RA FCF Licensee ($M)", "RA Income Licensor ($M)"
    ], columns=YEARS)
    
    # Fill static/ramp rows
    df.loc["Adoption Ramp", :] = ADOPTION_RAMP[:N_YEARS]
    
    # 1. Population & Epidemiology (Handling Overrides)
    pop_base = assumptions['pop_base']
    for i, year in enumerate(YEARS):
        # Apply override if exists, otherwise apply growth to previous year
        if overrides and "Total Population (EU)" in overrides and str(overrides["Total Population (EU)"].get(year, "")) != "":
            val = float(overrides["Total Population (EU)"][year])
            pop_base = val / ((1 + assumptions['pop_growth']) ** 0) # reset anchor
        else:
            val = pop_base * ((1 + assumptions['pop_growth']) ** i)
            
        df.loc["Total Population (EU)", year] = val

    df.loc["Target Patient Population (M)"] = df.loc["Total Population (EU)"] * assumptions['prevalence'] * ((1 + assumptions['prevalence_growth']) ** np.arange(N_YEARS))
    df.loc["Diagnosed Patients (M)"] = df.loc["Target Patient Population (M)"] * assumptions['diag_rate']
    df.loc["Treated Patients (M)"] = df.loc["Diagnosed Patients (M)"] * assumptions['treat_rate']
    
    # 2. Revenue Build
    for i, year in enumerate(YEARS):
        df.loc["Market Penetration (%)", year] = assumptions['peak_pen'] * df.loc["Adoption Ramp", year]
        df.loc["Patients on Therapy (M)", year] = df.loc["Treated Patients (M)", year] * df.loc["Market Penetration (%)", year]
        
        # Price Override check
        price = assumptions['price']
        if overrides and "Price Per Unit" in overrides and str(overrides["Price Per Unit"].get(year, "")) != "":
            price = float(overrides["Price Per Unit"][year])
            
        df.loc["Price Per Unit", year] = price
        df.loc["Gross Revenue ($M)", year] = df.loc["Patients on Therapy (M)", year] * price

    # 3. Expenses & Tax (Loss Carry-Forward)
    df.loc["COGS ($M)"] = -df.loc["Gross Revenue ($M)"] * assumptions['cogs_pct']
    df.loc["G&A ($M)"] = -df.loc["Gross Revenue ($M)"] * assumptions['ga_pct']
    df.loc["R&D & Pre-Mkt ($M)"] = [-RD_COSTS.get(y, 0) - PRE_MKT_COSTS.get(y, 0) for y in YEARS]
    
    df.loc["EBITDA ($M)"] = df.loc["Gross Revenue ($M)"] + df.loc["COGS ($M)"] + df.loc["G&A ($M)"] + df.loc["R&D & Pre-Mkt ($M)"]
    
    loss_cf = 0
    for year in YEARS:
        ebitda = df.loc["EBITDA ($M)", year]
        if ebitda < 0:
            loss_cf -= ebitda
            df.loc["Tax Paid ($M)", year] = 0
        else:
            taxable = max(0, ebitda - loss_cf)
            df.loc["Tax Paid ($M)", year] = -taxable * assumptions['tax_rate']
            loss_cf = max(0, loss_cf - ebitda)
            
    df.loc["Free Cash Flow (Pre-Deal, $M)"] = df.loc["EBITDA ($M)"] + df.loc["Tax Paid ($M)"]
    
    # 4. Risk Adjustment (CPoS)
    success_rates = np.ones(N_YEARS)
    success_rates[1] = assumptions['pos_ph1_2']  # Transition to Ph2
    success_rates[3] = assumptions['pos_ph2_3']  # Transition to Ph3
    success_rates[5] = assumptions['pos_ph3_nda']# Transition to NDA
    success_rates[6] = assumptions['pos_nda_app']# Transition to App
    df.loc["Cum. Prob. of Success"] = np.cumprod(success_rates)
    
    # 5. Deal Structure (Licensor Income)
    upfront_mstones = np.zeros(N_YEARS)
    upfront_mstones[0] = assumptions['upfront']
    upfront_mstones[2] = assumptions['milestones'] # Ph2 start
    upfront_mstones[4] = assumptions['milestones'] # Ph3 start
    upfront_mstones[6] = assumptions['milestones'] * 2 # NDA/App
    df.loc["Licensor Upfront & Milestones ($M)"] = upfront_mstones
    
    for year in YEARS:
        rev = df.loc["Gross Revenue ($M)", year]
        royalty = sum(max(0, rev - t['threshold']) * t['rate'] for t in ROYALTY_TIERS)
        df.loc["Licensor Royalty ($M)", year] = royalty
        
    df.loc["Total Licensor Income ($M)"] = df.loc["Licensor Upfront & Milestones ($M)"] + df.loc["Licensor Royalty ($M)"]
    
    # 6. Final Risk-Adjusted Cash Flows
    df.loc["RA Income Licensor ($M)"] = df.loc["Total Licensor Income ($M)"] * df.loc["Cum. Prob. of Success"]
    df.loc["RA FCF Licensee ($M)"] = (df.loc["Free Cash Flow (Pre-Deal, $M)"] - df.loc["Total Licensor Income ($M)"]) * df.loc["Cum. Prob. of Success"]

    # NPV Calculations
    df_licensee = 1 / (1 + assumptions['wacc_licensee']) ** np.arange(N_YEARS)
    df_licensor = 1 / (1 + assumptions['wacc_licensor']) ** np.arange(N_YEARS)
    
    enpv_licensee = np.sum(df.loc["RA FCF Licensee ($M)"] * df_licensee)
    enpv_licensor = np.sum(df.loc["RA Income Licensor ($M)"] * df_licensor)
    
    return df, enpv_licensee, enpv_licensor


# ============================================================================
# 3. DASHBOARD UI SETUP
# ============================================================================

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server

# Sidebar / Assumptions Input
assumptions_panel = dbc.Card([
    dbc.CardHeader("⚙️ Base Assumptions", className="font-weight-bold"),
    dbc.CardBody([
        dbc.Label("EU Pop Growth Rate (%)", className="mt-2 text-muted small"),
        dbc.Input(id="in-pop-growth", type="number", value=0.02, step=0.005),
        
        dbc.Label("Base Price per Unit ($)", className="mt-2 text-muted small"),
        dbc.Input(id="in-price", type="number", value=100.0, step=5),
        
        dbc.Label("Peak Market Pen. (%)", className="mt-2 text-muted small"),
        dbc.Input(id="in-peak-pen", type="number", value=0.05, step=0.01),
        
        dbc.Label("Tax Rate (%)", className="mt-2 text-muted small"),
        dbc.Input(id="in-tax-rate", type="number", value=0.21, step=0.01),
        
        html.Hr(),
        dbc.Label("Prob. of Success (PTRS)", className="font-weight-bold"),
        dbc.Row([
            dbc.Col([dbc.Label("Ph1→2", className="small"), dbc.Input(id="in-p1", type="number", value=0.30, step=0.05)]),
            dbc.Col([dbc.Label("Ph2→3", className="small"), dbc.Input(id="in-p2", type="number", value=0.49, step=0.05)]),
        ]),
        dbc.Row([
            dbc.Col([dbc.Label("Ph3→NDA", className="small"), dbc.Input(id="in-p3", type="number", value=0.553, step=0.05)]),
            dbc.Col([dbc.Label("NDA→App", className="small"), dbc.Input(id="in-p4", type="number", value=0.95, step=0.05)]),
        ]),
        
        html.Hr(),
        dbc.Button("Recalculate Model", id="btn-calc", color="primary", className="w-100 mt-2")
    ])
], className="mb-4 shadow-sm")


app.layout = dbc.Container([
    dbc.Row([dbc.Col(html.H2("GATX-11 Biopharma NPV Model", className="text-primary mt-4 mb-3"), md=12)]),
    
    # KPI Row
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Licensor rNPV ($M)", className="text-muted"), html.H3(id="kpi-licensor", className="text-success")])), md=6),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Licensee rNPV ($M)", className="text-muted"), html.H3(id="kpi-licensee", className="text-primary")])), md=6),
    ], className="mb-4"),
    
    dbc.Row([
        dbc.Col(assumptions_panel, md=3),
        dbc.Col([
            dbc.Tabs([
                dbc.Tab(label="📊 Editable DCF Table", tab_id="tab-dcf"),
                dbc.Tab(label="🌪️ Sensitivity (Tornado)", tab_id="tab-tornado"),
                dbc.Tab(label="🎲 Monte Carlo Simulation", tab_id="tab-mc"),
            ], id="main-tabs", active_tab="tab-dcf"),
            html.Div(id="tab-content", className="mt-4")
        ], md=9)
    ])
], fluid=True)


# ============================================================================
# 4. DASHBOARD CALLBACKS
# ============================================================================

def get_current_assumptions(growth, price, peak_pen, tax, p1, p2, p3, p4):
    """Helper to package inputs into the required dictionary."""
    return {
        'pop_base': 450.0, 'pop_growth': float(growth), 'prevalence': 0.09,
        'prevalence_growth': 0.02, 'diag_rate': 0.80, 'treat_rate': 0.50,
        'peak_pen': float(peak_pen), 'price': float(price), 'cogs_pct': 0.12,
        'ga_pct': 0.01, 'tax_rate': float(tax),
        'wacc_licensee': 0.10, 'wacc_licensor': 0.14, # Using 14% licensor from specs
        'pos_ph1_2': float(p1), 'pos_ph2_3': float(p2),
        'pos_ph3_nda': float(p3), 'pos_nda_app': float(p4),
        'upfront': 2.0, 'milestones': 1.0
    }

def extract_overrides(table_data):
    """Parses Dash DataTable data to extract user overrides."""
    overrides = {"Total Population (EU)": {}, "Price Per Unit": {}}
    if not table_data: return overrides
    
    for row in table_data:
        if row.get("Line Item") in overrides:
            for y in YEARS:
                if y in row and row[y] != "":
                    overrides[row["Line Item"]][y] = row[y]
    return overrides

@app.callback(
    [Output("tab-content", "children"), Output("kpi-licensor", "children"), Output("kpi-licensee", "children")],
    [Input("btn-calc", "n_clicks"), Input("main-tabs", "active_tab")],
    [State("in-pop-growth", "value"), State("in-price", "value"), State("in-peak-pen", "value"),
     State("in-tax-rate", "value"), State("in-p1", "value"), State("in-p2", "value"),
     State("in-p3", "value"), State("in-p4", "value"), State("dcf-table", "data")],
    prevent_initial_call=False
)
def update_dashboard(n_clicks, active_tab, growth, price, peak_pen, tax, p1, p2, p3, p4, table_data):
    ctx = callback_context
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # 1. Package assumptions and check for table overrides
    assumptions = get_current_assumptions(growth, price, peak_pen, tax, p1, p2, p3, p4)
    overrides = extract_overrides(table_data) if table_data else None
    
    # Run primary engine
    df, npv_licensee, npv_licensor = run_dcf_engine(assumptions, overrides)
    
    # Format KPIs
    str_npv_licensor = f"${npv_licensor:,.2f}"
    str_npv_licensee = f"${npv_licensee:,.2f}"
    
    # 2. Render appropriate tab
    if active_tab == "tab-dcf":
        df_display = df.copy()
        df_display = df_display.round(2).reset_index().rename(columns={"index": "Line Item"})
        
        table_ui = html.Div([
            html.P("✏️ Tip: You can edit cells in the Population and Price rows.", className="text-muted small"),
            dash_table.DataTable(
                id='dcf-table',
                columns=[
                    {"name": i, "id": i, "editable": (i in YEARS and r in ["Total Population (EU)", "Price Per Unit"])} 
                    for i in df_display.columns for r in df_display["Line Item"]
                ],
                data=df_display.to_dict('records'),
                style_table={'overflowX': 'auto', 'minWidth': '100%'},
                style_cell={'fontSize': '12px', 'padding': '8px', 'minWidth': '80px'},
                style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'},
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': '#fcfcfc'},
                    {'if': {'column_editable': True}, 'backgroundColor': '#e8f4f8', 'border': '1px dashed #2196F3'}
                ]
            )
        ])
        return table_ui, str_npv_licensor, str_npv_licensee

    elif active_tab == "tab-tornado":
        # Run 1-way sensitivity
        vars_to_test = {
            'peak_pen': [assumptions['peak_pen']*0.7, assumptions['peak_pen']*1.3],
            'price': [assumptions['price']*0.8, assumptions['price']*1.2],
            'pos_ph2_3': [max(0.1, assumptions['pos_ph2_3'] - 0.2), min(1.0, assumptions['pos_ph2_3'] + 0.2)]
        }
        
        sens_data = []
        for var, bounds in vars_to_test.items():
            for bound, label in zip(bounds, ["Low", "High"]):
                temp_assump = assumptions.copy()
                temp_assump[var] = bound
                _, _, temp_npv = run_dcf_engine(temp_assump, overrides)
                sens_data.append({"Variable": var, "Scenario": label, "NPV": temp_npv})
        
        sens_df = pd.DataFrame(sens_data)
        base_npv = npv_licensor
        
        fig = go.Figure()
        for var in vars_to_test.keys():
            low_val = sens_df[(sens_df['Variable'] == var) & (sens_df['Scenario'] == 'Low')]['NPV'].values[0]
            high_val = sens_df[(sens_df['Variable'] == var) & (sens_df['Scenario'] == 'High')]['NPV'].values[0]
            fig.add_trace(go.Bar(y=[var], x=[low_val - base_npv], base=base_npv, orientation='h', name=f'{var} (Low)', marker_color='#E74C3C'))
            fig.add_trace(go.Bar(y=[var], x=[high_val - base_npv], base=base_npv, orientation='h', name=f'{var} (High)', marker_color='#2ECC71'))

        fig.update_layout(title="Tornado Chart (Licensor rNPV Impact)", barmode='overlay', xaxis_title="NPV ($M)", showlegend=False, template="plotly_white")
        fig.add_vline(x=base_npv, line_dash="dash", line_color="black")
        
        return dcc.Graph(figure=fig), str_npv_licensor, str_npv_licensee

    elif active_tab == "tab-mc":
        # Run Monte Carlo
        n_sims = 500
        mc_results = []
        for _ in range(n_sims):
            sim_assumptions = assumptions.copy()
            sim_assumptions['pop_growth'] = np.random.normal(assumptions['pop_growth'], 0.01)
            sim_assumptions['peak_pen'] = max(0, np.random.normal(assumptions['peak_pen'], 0.01))
            sim_assumptions['price'] = max(10, np.random.normal(assumptions['price'], 20))
            _, _, temp_npv = run_dcf_engine(sim_assumptions, overrides)
            mc_results.append(temp_npv)
            
        fig = go.Figure(data=[go.Histogram(x=mc_results, nbinsx=40, marker_color='#3498DB', opacity=0.7)])
        fig.add_vline(x=np.mean(mc_results), line_dash="dash", line_color="red", annotation_text=f"Mean: ${np.mean(mc_results):.2f}M")
        fig.update_layout(title=f"Monte Carlo Distribution ({n_sims} Iterations)", xaxis_title="Licensor rNPV ($M)", yaxis_title="Frequency", template="plotly_white")
        
        return dcc.Graph(figure=fig), str_npv_licensor, str_npv_licensee

    return html.Div(), str_npv_licensor, str_npv_licensee

# Needed to define the component on load before callbacks fire
app.validation_layout = html.Div([
    app.layout,
    dash_table.DataTable(id='dcf-table')
])

if __name__ == '__main__':
    app.run_server(debug=True)
