import numpy as np
import pandas as pd
import warnings

from dash import Dash, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objs as go

warnings.filterwarnings("ignore")
np.random.seed(42)

# ============================================================================
# SECTION 1 — ASSUMPTIONS  (editable via UI)
# ============================================================================

# Simulation control
DEFAULT_N_SIMULATIONS = 10_000
START_YEAR = 2026
END_YEAR = 2042
YEARS = list(range(START_YEAR, END_YEAR + 1))
N_YEARS = len(YEARS)

# Revenue model assumptions (defaults)
EU_POPULATION_M_DEFAULT = 450.0
POP_GROWTH_RATE_MEAN_DEFAULT = 0.020
POP_GROWTH_RATE_SD_DEFAULT = 0.04

TARGET_PATIENT_SHARE_DEFAULT = 0.09
DIAGNOSIS_RATE_DEFAULT = 0.80
TREATMENT_RATE_DEFAULT = 0.50

PEAK_PENETRATION_MEAN_DEFAULT = 0.05
PEAK_PENETRATION_SD_DEFAULT = 0.01
YEARS_TO_PEAK_DEFAULT = 5

PRICE_PER_UNIT_MEAN_DEFAULT = 100.0
PRICE_PER_UNIT_SD_DEFAULT = 25.0

ANNUAL_PREVALENCE_GROWTH_DEFAULT = 0.02

ADOPTION_SCHEDULE_DEFAULT = {
    0: 0.00, 1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00, 6: 0.00,
    7: 0.60, 8: 0.80, 9: 0.90, 10: 1.00, 11: 1.00, 12: 1.00,
    13: 0.70, 14: 0.40, 15: 0.20, 16: 0.20
}

# Cost assumptions
COGS_PCT_DEFAULT = 0.12
GA_OPEX_PCT_DEFAULT = 0.01
TAX_RATE_DEFAULT = 0.21
WORKING_CAPITAL_DEFAULT = 0.15  # not directly used in base engine

RD_SCHEDULE_DEFAULT = {
    0: 2, 1: 3, 2: 2, 3: 3, 4: 3, 5: 3, 6: 2
}

# Discount rates
LICENSEE_WACC_MEAN_DEFAULT = 0.10
LICENSEE_WACC_SD_DEFAULT = 0.025
LICENSOR_WACC_MEAN_DEFAULT = 0.14
LICENSOR_WACC_SD_DEFAULT = 0.025
RISK_FREE_RATE_DEFAULT = 0.04

# Clinical probabilities
P_PH1_PH2_DEFAULT = 0.300
P_PH2_PH3_DEFAULT = 0.490
P_PH3_NDA_DEFAULT = 0.553
P_NDA_APPROV_DEFAULT = 0.950

# Deal terms
UPFRONT_M_DEFAULT = 2.0
MILESTONES_DEFAULT = {
    0: 1.0,
    2: 1.0,
    4: 1.0,
    6: 2.0,
}

ROYALTY_TIERS_DEFAULT = [
    (0, 100, 0.050),
    (100, 200, 0.070),
    (200, np.inf, 0.090),
]


def compute_royalty(revenue_m, royalty_tiers):
    royalty = 0.0
    for lo, hi, rate in royalty_tiers:
        if revenue_m > lo:
            royalty += min(revenue_m - lo, hi - lo) * rate
    return royalty


# ============================================================================
# SECTION 2 — CORE ENGINE (single scenario)
# ============================================================================

def run_scenario(
    pop_growth,
    peak_penetration,
    price,
    licensee_wacc,
    licensor_wacc,
    eu_population_m,
    target_patient_share,
    diagnosis_rate,
    treatment_rate,
    cogs_pct,
    ga_opex_pct,
    tax_rate,
    rd_schedule,
    adoption_schedule,
    p_ph1_ph2,
    p_ph2_ph3,
    p_ph3_nda,
    p_nda_approv,
    upfront_m,
    milestones,
    royalty_tiers,
):
    revenue = np.zeros(N_YEARS)
    fcf_full = np.zeros(N_YEARS)
    royalty = np.zeros(N_YEARS)

    population = eu_population_m
    for i in range(N_YEARS):
        population *= (1 + pop_growth)
        adopt = adoption_schedule.get(i, 0.0)
        penetration = peak_penetration * adopt

        treated = (
            population
            * target_patient_share
            * diagnosis_rate
            * treatment_rate
            * penetration
        )

        rev = treated * price
        revenue[i] = max(rev, 0)

    for i in range(N_YEARS):
        rev = revenue[i]
        cogs = rev * cogs_pct
        gross = rev - cogs
        ga = rev * ga_opex_pct
        rd_cost = rd_schedule.get(i, 0.0)
        ebitda = gross - ga - rd_cost

        cum_loss = sum(rd_schedule.get(j, 0.0) for j in range(i + 1) if revenue[j] == 0)
        taxable = max(ebitda - cum_loss, 0)
        tax = taxable * tax_rate if ebitda > 0 else 0

        royalty[i] = compute_royalty(rev, royalty_tiers)
        fcf_full[i] = ebitda - tax - royalty[i]

    # Probability-adjusted risk
    cum_prob = np.ones(N_YEARS)
    cum = 1.0
    phase_probs = [1.0, p_ph1_ph2, 1.0, p_ph2_ph3, 1.0, p_ph3_nda, p_nda_approv]
    for i in range(N_YEARS):
        if i < len(phase_probs):
            cum *= phase_probs[i]
        cum_prob[i] = min(cum, 1.0)

    risk_adj_fcf = fcf_full * cum_prob

    df_licensee = np.array([(1 / (1 + licensee_wacc)) ** i for i in range(N_YEARS)])
    df_licensor = np.array([(1 / (1 + licensor_wacc)) ** i for i in range(N_YEARS)])

    licensee_enpv = float(np.sum(risk_adj_fcf * df_licensee))

    licensor_cf = np.zeros(N_YEARS)
    licensor_cf[0] += upfront_m
    for yr_idx, mil_m in milestones.items():
        if yr_idx < N_YEARS:
            licensor_cf[yr_idx] += mil_m

    risk_adj_royalty = royalty * cum_prob
    licensor_cf += risk_adj_royalty

    licensor_npv = float(np.sum(licensor_cf * df_licensor))

    return {
        "revenue": revenue,
        "royalty": royalty,
        "fcf": fcf_full,
        "risk_adj_fcf": risk_adj_fcf,
        "licensor_cf": licensor_cf,
        "licensee_enpv": licensee_enpv,
        "licensor_npv": licensor_npv,
        "cum_prob": cum_prob,
        "df_licensee": df_licensee,
    }


# ============================================================================
# SECTION 3 — MONTE CARLO WRAPPER
# ============================================================================

def monte_carlo_run(
    n_sims,
    eu_population_m,
    pop_growth_mean,
    pop_growth_sd,
    peak_pen_mean,
    peak_pen_sd,
    price_mean,
    price_sd,
    licensee_wacc_mean,
    licensee_wacc_sd,
    licensor_wacc_mean,
    licensor_wacc_sd,
    target_patient_share,
    diagnosis_rate,
    treatment_rate,
    cogs_pct,
    ga_opex_pct,
    tax_rate,
    rd_schedule,
    adoption_schedule,
    p_ph1_ph2,
    p_ph2_ph3,
    p_ph3_nda,
    p_nda_approv,
    upfront_m,
    milestones,
    royalty_tiers,
):
    licensee_npvs = np.zeros(n_sims)
    licensor_npvs = np.zeros(n_sims)
    rev_paths = []

    for s in range(n_sims):
        pg = np.random.normal(pop_growth_mean, pop_growth_sd)
        pp = max(np.random.normal(peak_pen_mean, peak_pen_sd), 0.001)
        pr = max(np.random.normal(price_mean, price_sd), 10)
        lsw = max(np.random.normal(licensee_wacc_mean, licensee_wacc_sd), 0.05)
        lrw = max(np.random.normal(licensor_wacc_mean, licensor_wacc_sd), 0.05)

        res = run_scenario(
            pg, pp, pr, lsw, lrw,
            eu_population_m, target_patient_share, diagnosis_rate, treatment_rate,
            cogs_pct, ga_opex_pct, tax_rate,
            rd_schedule, adoption_schedule,
            p_ph1_ph2, p_ph2_ph3, p_ph3_nda, p_nda_approv,
            upfront_m, milestones, royalty_tiers
        )

        licensee_npvs[s] = res["licensee_enpv"]
        licensor_npvs[s] = res["licensor_npv"]
        if s < 200:
            rev_paths.append(res["revenue"])

    rev_paths = np.array(rev_paths)
    base_case = run_scenario(
        pop_growth_mean, peak_pen_mean, price_mean,
        licensee_wacc_mean, licensor_wacc_mean,
        eu_population_m, target_patient_share, diagnosis_rate, treatment_rate,
        cogs_pct, ga_opex_pct, tax_rate,
        rd_schedule, adoption_schedule,
        p_ph1_ph2, p_ph2_ph3, p_ph3_nda, p_nda_approv,
        upfront_m, milestones, royalty_tiers
    )

    return licensee_npvs, licensor_npvs, rev_paths, base_case


def mc_stats(arr):
    pct = np.percentile(arr, [5, 10, 25, 50, 75, 90, 95])
    prob_pos = np.mean(arr > 0)
    return {
        "mean": np.mean(arr),
        "std": np.std(arr),
        "min": np.min(arr),
        "p5": pct[0],
        "p10": pct[1],
        "p25": pct[2],
        "p50": pct[3],
        "p75": pct[4],
        "p90": pct[5],
        "p95": pct[6],
        "max": np.max(arr),
        "prob_pos": prob_pos,
    }

# ============================================================================
# SECTION 4 — DASH APP LAYOUT
# ============================================================================

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

def assumptions_layout():
    return dbc.Container(
        [
            html.H2("GATX-11 EU License — Monte Carlo NPV Engine"),
            html.P("Edit core assumptions, then run the simulation."),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H5("Population & Epidemiology"),
                            dbc.Label("EU Population (M)"),
                            dbc.Input(id="eu_population", type="number",
                                      value=EU_POPULATION_M_DEFAULT, step=10),
                            dbc.Label("Population Growth Mean"),
                            dbc.Input(id="pop_growth_mean", type="number",
                                      value=POP_GROWTH_RATE_MEAN_DEFAULT, step=0.005),
                            dbc.Label("Population Growth SD"),
                            dbc.Input(id="pop_growth_sd", type="number",
                                      value=POP_GROWTH_RATE_SD_DEFAULT, step=0.005),
                            dbc.Label("Target Patient Share"),
                            dbc.Input(id="target_share", type="number",
                                      value=TARGET_PATIENT_SHARE_DEFAULT, step=0.01),
                            dbc.Label("Diagnosis Rate"),
                            dbc.Input(id="diagnosis_rate", type="number",
                                      value=DIAGNOSIS_RATE_DEFAULT, step=0.05),
                            dbc.Label("Treatment Rate"),
                            dbc.Input(id="treatment_rate", type="number",
                                      value=TREATMENT_RATE_DEFAULT, step=0.05),
                        ],
                        md=4,
                    ),
                    dbc.Col(
                        [
                            html.H5("Price & Penetration"),
                            dbc.Label("Peak Penetration Mean"),
                            dbc.Input(id="peak_pen_mean", type="number",
                                      value=PEAK_PENETRATION_MEAN_DEFAULT, step=0.01),
                            dbc.Label("Peak Penetration SD"),
                            dbc.Input(id="peak_pen_sd", type="number",
                                      value=PEAK_PENETRATION_SD_DEFAULT, step=0.005),
                            dbc.Label("Price / Patient / Year"),
                            dbc.Input(id="price_mean", type="number",
                                      value=PRICE_PER_UNIT_MEAN_DEFAULT, step=5),
                            dbc.Label("Price SD"),
                            dbc.Input(id="price_sd", type="number",
                                      value=PRICE_PER_UNIT_SD_DEFAULT, step=5),
                            dbc.Label("COGS %"),
                            dbc.Input(id="cogs_pct", type="number",
                                      value=COGS_PCT_DEFAULT, step=0.01),
                            dbc.Label("G&A %"),
                            dbc.Input(id="ga_opex_pct", type="number",
                                      value=GA_OPEX_PCT_DEFAULT, step=0.005),
                            dbc.Label("Tax Rate"),
                            dbc.Input(id="tax_rate", type="number",
                                      value=TAX_RATE_DEFAULT, step=0.01),
                        ],
                        md=4,
                    ),
                    dbc.Col(
                        [
                            html.H5("Discount & Deal Terms"),
                            dbc.Label("Licensee WACC Mean"),
                            dbc.Input(id="licensee_wacc_mean", type="number",
                                      value=LICENSEE_WACC_MEAN_DEFAULT, step=0.01),
                            dbc.Label("Licensee WACC SD"),
                            dbc.Input(id="licensee_wacc_sd", type="number",
                                      value=LICENSEE_WACC_SD_DEFAULT, step=0.005),
                            dbc.Label("Licensor WACC Mean"),
                            dbc.Input(id="licensor_wacc_mean", type="number",
                                      value=LICENSOR_WACC_MEAN_DEFAULT, step=0.01),
                            dbc.Label("Licensor WACC SD"),
                            dbc.Input(id="licensor_wacc_sd", type="number",
                                      value=LICENSOR_WACC_SD_DEFAULT, step=0.005),
                            dbc.Label("Upfront Payment ($M)"),
                            dbc.Input(id="upfront_m", type="number",
                                      value=UPFRONT_M_DEFAULT, step=0.5),
                            dbc.Label("Number of Simulations"),
                            dbc.Input(id="n_sims", type="number",
                                      value=DEFAULT_N_SIMULATIONS, step=1000),
                            html.Br(),
                            dbc.Button("Run Simulation", id="run_sim", color="primary"),
                            html.Div(id="status_text", className="mt-2 text-muted"),
                        ],
                        md=4,
                    ),
                ]
            ),
        ],
        fluid=True,
    )


def dcf_table_layout():
    return dbc.Container(
        [
            html.H3("Base Case — Annual DCF Table"),
            html.Div(id="dcf_summary_kpis", className="mb-3"),
            html.Div(id="dcf_table"),
        ],
        fluid=True,
    )


def figures_layout():
    return dbc.Container(
        [
            html.H3("Figures & Distributions"),
            dbc.Row(
                [
                    dbc.Col(dcc.Graph(id="rev_fan_chart"), md=6),
                    dbc.Col(dcc.Graph(id="licensee_hist"), md=6),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(dcc.Graph(id="licensor_hist"), md=6),
                    dbc.Col(dcc.Graph(id="s_curve"), md=6),
                ]
            ),
        ],
        fluid=True,
    )


app.layout = dbc.Container(
    [
        html.H1("Biopharma Licensing Monte Carlo NPV — GATX-11 (EU)"),
        dcc.Tabs(
            id="tabs",
            value="tab-assumptions",
            children=[
                dcc.Tab(label="1. Assumptions", value="tab-assumptions"),
                dcc.Tab(label="2. DCF Table & NPVs", value="tab-dcf"),
                dcc.Tab(label="3. Figures", value="tab-figures"),
            ],
        ),
        html.Div(id="tab-content"),
        dcc.Store(id="mc_store"),
    ],
    fluid=True,
)


@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
)
def render_tab(tab):
    if tab == "tab-assumptions":
        return assumptions_layout()
    elif tab == "tab-dcf":
        return dcf_table_layout()
    elif tab == "tab-figures":
        return figures_layout()
    return html.Div("Unknown tab")


# ============================================================================
# SECTION 5 — CALLBACK TO RUN SIMULATION
# ============================================================================

@app.callback(
    Output("mc_store", "data"),
    Output("status_text", "children"),
    Input("run_sim", "n_clicks"),
    State("eu_population", "value"),
    State("pop_growth_mean", "value"),
    State("pop_growth_sd", "value"),
    State("target_share", "value"),
    State("diagnosis_rate", "value"),
    State("treatment_rate", "value"),
    State("peak_pen_mean", "value"),
    State("peak_pen_sd", "value"),
    State("price_mean", "value"),
    State("price_sd", "value"),
    State("cogs_pct", "value"),
    State("ga_opex_pct", "value"),
    State("tax_rate", "value"),
    State("licensee_wacc_mean", "value"),
    State("licensee_wacc_sd", "value"),
    State("licensor_wacc_mean", "value"),
    State("licensor_wacc_sd", "value"),
    State("upfront_m", "value"),
    State("n_sims", "value"),
    prevent_initial_call=True,
)
def run_simulation(
    n_clicks,
    eu_pop,
    pop_g_mean,
    pop_g_sd,
    target_share,
    diagnosis_rate,
    treatment_rate,
    peak_pen_mean,
    peak_pen_sd,
    price_mean,
    price_sd,
    cogs_pct,
    ga_opex_pct,
    tax_rate,
    lic_wacc_mean,
    lic_wacc_sd,
    licor_wacc_mean,
    licor_wacc_sd,
    upfront_m,
    n_sims,
):
    if n_clicks is None:
        return dash.no_update, ""

    (licensee_npvs, licensor_npvs, rev_paths, base_case) = monte_carlo_run(
        int(n_sims),
        float(eu_pop),
        float(pop_g_mean),
        float(pop_g_sd),
        float(peak_pen_mean),
        float(peak_pen_sd),
        float(price_mean),
        float(price_sd),
        float(lic_wacc_mean),
        float(lic_wacc_sd),
        float(licor_wacc_mean),
        float(licor_wacc_sd),
        float(target_share),
        float(diagnosis_rate),
        float(treatment_rate),
        float(cogs_pct),
        float(ga_opex_pct),
        float(tax_rate),
        RD_SCHEDULE_DEFAULT,
        ADOPTION_SCHEDULE_DEFAULT,
        P_PH1_PH2_DEFAULT,
        P_PH2_PH3_DEFAULT,
        P_PH3_NDA_DEFAULT,
        P_NDA_APPROV_DEFAULT,
        float(upfront_m),
        MILESTONES_DEFAULT,
        ROYALTY_TIERS_DEFAULT,
    )

    ls_stats = mc_stats(licensee_npvs)
    lr_stats = mc_stats(licensor_npvs)

    # Prepare base-case DCF table
    summary_rows = []
    for i, y in enumerate(YEARS):
        summary_rows.append(
            {
                "Year": y,
                "Revenue_M": round(base_case["revenue"][i], 3),
                "COGS_M": round(base_case["revenue"][i] * cogs_pct, 3),
                "Royalty_Paid_M": round(base_case["royalty"][i], 3),
                "RD_Expense_M": RD_SCHEDULE_DEFAULT.get(i, 0.0),
                "FCF_Licensee_M": round(base_case["fcf"][i], 3),
                "CumProb_Success": round(base_case["cum_prob"][i], 4),
                "RiskAdj_FCF_M": round(base_case["risk_adj_fcf"][i], 3),
                "DiscFactor_Licensee": round(base_case["df_licensee"][i], 4),
                "Disc_eNPV_M": round(
                    base_case["risk_adj_fcf"][i] * base_case["df_licensee"][i], 3
                ),
                "Licensor_CF_M": round(base_case["licensor_cf"][i], 3),
            }
        )
    dcf_df = pd.DataFrame(summary_rows)

    data = {
        "licensee_npvs": licensee_npvs.tolist(),
        "licensor_npvs": licensor_npvs.tolist(),
        "rev_paths": rev_paths.tolist(),
        "base_case": {
            "revenue": base_case["revenue"].tolist(),
            "royalty": base_case["royalty"].tolist(),
            "fcf": base_case["fcf"].tolist(),
            "risk_adj_fcf": base_case["risk_adj_fcf"].tolist(),
            "licensor_cf": base_case["licensor_cf"].tolist(),
            "cum_prob": base_case["cum_prob"].tolist(),
            "df_licensee": base_case["df_licensee"].tolist(),
            "licensee_enpv": base_case["licensee_enpv"],
            "licensor_npv": base_case["licensor_npv"],
        },
        "dcf_table": dcf_df.to_dict("records"),
        "ls_stats": ls_stats,
        "lr_stats": lr_stats,
    }

    status = (
        f"Ran {int(n_sims):,} simulations. "
        f"Base Licensee eNPV: ${base_case['licensee_enpv']:.1f}M · "
        f"Base Licensor NPV: ${base_case['licensor_npv']:.1f}M"
    )
    return data, status


# ============================================================================
# SECTION 6 — DCF TABLE & KPIs TAB
# ============================================================================

@app.callback(
    Output("dcf_table", "children"),
    Output("dcf_summary_kpis", "children"),
    Input("mc_store", "data"),
)
def update_dcf_table(data):
    if not data:
        return html.Div("Run the simulation first from the Assumptions tab."), ""

    dcf_records = data["dcf_table"]
    dcf_df = pd.DataFrame(dcf_records)
    ls_stats = data["ls_stats"]
    lr_stats = data["lr_stats"]
    base_enpv = data["base_case"]["licensee_enpv"]
    base_l_npv = data["base_case"]["licensor_npv"]

    kpi_row = dbc.Row(
        [
            dbc.Col(html.Div([
                html.H5("Licensee Base eNPV"),
                html.H3(f"${base_enpv:.1f}M")
            ])),
            dbc.Col(html.Div([
                html.H5("Licensor Base NPV"),
                html.H3(f"${base_l_npv:.1f}M")
            ])),
            dbc.Col(html.Div([
                html.H5("P(Licensee NPV>0)"),
                html.H3(f"{ls_stats['prob_pos']*100:.1f}%")
            ])),
            dbc.Col(html.Div([
                html.H5("P(Licensor NPV>0)"),
                html.H3(f"{lr_stats['prob_pos']*100:.1f}%")
            ])),
        ]
    )

    table = dbc.Table.from_dataframe(dcf_df, striped=True, bordered=True, hover=True)

    return table, kpi_row


# ============================================================================
# SECTION 7 — FIGURES TAB
# ============================================================================

@app.callback(
    Output("rev_fan_chart", "figure"),
    Output("licensee_hist", "figure"),
    Output("licensor_hist", "figure"),
    Output("s_curve", "figure"),
    Input("mc_store", "data"),
)
def update_figures(data):
    if not data:
        empty_fig = go.Figure().update_layout(
            annotations=[dict(text="Run simulation first", showarrow=False)]
        )
        return empty_fig, empty_fig, empty_fig, empty_fig

    rev_paths = np.array(data["rev_paths"])
    licensee_npvs = np.array(data["licensee_npvs"])
    licensor_npvs = np.array(data["licensor_npvs"])
    base_rev = np.array(data["base_case"]["revenue"])
    ls_stats = data["ls_stats"]
    lr_stats = data["lr_stats"]

    # Revenue fan
    pct5 = np.percentile(rev_paths, 5, axis=0)
    pct25 = np.percentile(rev_paths, 25, axis=0)
    pct50 = np.percentile(rev_paths, 50, axis=0)
    pct75 = np.percentile(rev_paths, 75, axis=0)
    pct95 = np.percentile(rev_paths, 95, axis=0)

    fig_rev = go.Figure()
    fig_rev.add_traces([
        go.Scatter(
            x=YEARS, y=pct95,
            line=dict(color="rgba(21,101,192,0)"),
            showlegend=False, hoverinfo="skip"
        ),
        go.Scatter(
            x=YEARS, y=pct5,
            fill="tonexty",
            fillcolor="rgba(21,101,192,0.15)",
            line=dict(color="rgba(21,101,192,0)"),
            name="P5–P95"
        ),
        go.Scatter(
            x=YEARS, y=pct75,
            line=dict(color="rgba(21,101,192,0)"),
            showlegend=False, hoverinfo="skip"
        ),
        go.Scatter(
            x=YEARS, y=pct25,
            fill="tonexty",
            fillcolor="rgba(21,101,192,0.3)",
            line=dict(color="rgba(21,101,192,0)"),
            name="P25–P75"
        ),
        go.Scatter(
            x=YEARS, y=pct50,
            line=dict(color="rgb(21,101,192)", width=2),
            name="Median"
        ),
        go.Scatter(
            x=YEARS, y=base_rev,
            line=dict(color="#F57F17", width=2, dash="dash"),
            name="Base Case"
        ),
    ])
    fig_rev.update_layout(
        title="Revenue Forecast Fan Chart",
        xaxis_title="Year",
        yaxis_title="Revenue ($M)",
        template="plotly_white",
    )

    # Licensee hist
    fig_ls = go.Figure()
    fig_ls.add_trace(
        go.Histogram(
            x=licensee_npvs,
            nbinsx=80,
            marker_color="#1565C0",
            opacity=0.75,
        )
    )
    fig_ls.add_vline(
        x=ls_stats["mean"],
        line=dict(color="#F57F17", dash="dash", width=2),
    )
    fig_ls.add_vline(
        x=ls_stats["p50"],
        line=dict(color="#00838F", dash="dot", width=2),
    )
    fig_ls.update_layout(
        title=f"Licensee eNPV Distribution (Mean=${ls_stats['mean']:.1f}M, P>0={ls_stats['prob_pos']*100:.1f}%)",
        xaxis_title="eNPV ($M)",
        yaxis_title="Frequency",
        template="plotly_white",
    )

    # Licensor hist
    fig_lr = go.Figure()
    fig_lr.add_trace(
        go.Histogram(
            x=licensor_npvs,
            nbinsx=80,
            marker_color="#00838F",
            opacity=0.75,
        )
    )
    fig_lr.add_vline(
        x=lr_stats["mean"],
        line=dict(color="#F57F17", dash="dash", width=2),
    )
    fig_lr.add_vline(
        x=lr_stats["p50"],
        line=dict(color="#1565C0", dash="dot", width=2),
    )
    fig_lr.update_layout(
        title=f"Licensor NPV Distribution (Mean=${lr_stats['mean']:.1f}M, P>0={lr_stats['prob_pos']*100:.1f}%)",
        xaxis_title="Deal NPV ($M)",
        yaxis_title="Frequency",
        template="plotly_white",
    )

    # S-curve
    sorted_ls = np.sort(licensee_npvs)
    sorted_lr = np.sort(licensor_npvs)
    cdf = np.arange(1, len(sorted_ls) + 1) / len(sorted_ls)

    fig_s = go.Figure()
    fig_s.add_trace(
        go.Scatter(
            x=sorted_ls,
            y=cdf,
            name="Licensee eNPV",
            line=dict(color="#1565C0"),
        )
    )
    fig_s.add_trace(
        go.Scatter(
            x=sorted_lr,
            y=cdf,
            name="Licensor NPV",
            line=dict(color="#00838F"),
        )
    )
    fig_s.add_vline(x=0, line=dict(color="black", dash="dash"))
    fig_s.update_layout(
        title="Cumulative Probability (S-Curve)",
        xaxis_title="NPV ($M)",
        yaxis_title="Cumulative Probability",
        template="plotly_white",
        yaxis_tickformat=".0%",
    )

    return fig_rev, fig_ls, fig_lr, fig_s


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=7860, debug=False)
```
