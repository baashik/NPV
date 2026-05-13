"""NPV Model — Dash callbacks."""

import json
from datetime import datetime
import numpy as np
from dash import html, no_update, dcc, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from config import ScenarioParams, N_YEARS, YEARS, COLORS, RD_SCHEDULE, build_params
from engine import run_scenario, run_montecarlo, npv_stats, run_sensitivity as eng_run_sensitivity, ROYALTY_TIERS_DEFAULT
from model_engine import run_sensitivity, clean_assumptions, DEFAULT_ASSUMPTIONS
from styles import CARD


def compute_tiered_royalty_callback(rev, tier1_thresh, tier2_thresh, tier1_rate, tier2_rate, tier3_rate):
    """Compute tiered royalty from a single revenue value."""
    tier1 = tier1_thresh
    tier2 = tier2_thresh
    r1 = tier1_rate / 100
    r2 = tier2_rate / 100
    r3 = tier3_rate / 100

    roy = 0.0
    remaining = rev
    if remaining > 0:
        roy += min(remaining, tier1) * r1
        remaining = max(remaining - tier1, 0)
    if remaining > 0:
        roy += min(remaining, tier2 - tier1) * r2
        remaining = max(remaining - (tier2 - tier1), 0)
    if remaining > 0:
        roy += remaining * r3
    return roy


def build_licensor_data(params, base_arrays, ptr, df_lr):
    """
    Build licensor economics from engine output and license term inputs.
    Returns dict with licensor arrays for bridge and annual charts.
    """
    n = N_YEARS
    price = params.get("price", 15000)
    lsw = params.get("lsw", 0.10)
    lrw = params.get("lrw", 0.14)

    # License term inputs
    upfront = float(params.get("upfront", 2.0))
    dev_milestone = float(params.get("dev_mil", 1.0))
    reg_milestone = float(params.get("reg_mil", 2.0))
    comm_milestone = float(params.get("comm_mil", 0.0))
    tier1_thresh = float(params.get("tier1_thresh", 100.0))
    tier2_thresh = float(params.get("tier2_thresh", 200.0))
    tier1_rate = float(params.get("roy_tier1", 5.0))
    tier2_rate = float(params.get("roy_tier2", 7.0))
    tier3_rate = float(params.get("roy_tier3", 9.0))
    royalty_start = int(params.get("royalty_start", 2033))
    start_year = 2026

    # PTRS probabilities for risk adjustment
    p1, p2, p3, p4 = 0.63, 0.30, 0.58, 0.90
    p2_to_approval = p3 * p4
    full_prob = p1 * p2 * p3 * p4

    # Licensor income components
    upfront_income = [upfront] + [0.0] * (n - 1)
    dev_milestone_income = [0.0] * n
    if 2 < n:
        dev_milestone_income[2] = dev_milestone

    reg_milestone_income = [0.0] * n
    comm_milestone_income = [0.0] * n
    royalty_income = [0.0] * n

    launch_idx = royalty_start - start_year  # year index for launch
    if launch_idx < n:
        reg_milestone_income[launch_idx] = reg_milestone
        if launch_idx + 1 < n:
            comm_milestone_income[launch_idx + 1] = comm_milestone

    # Compute royalties for royalty period
    rev = base_arrays.get("base_rev", [0.0] * n)
    for i in range(n):
        year = start_year + i
        if royalty_start <= year <= 2042:
            royalty_income[i] = compute_tiered_royalty_callback(
                rev[i], tier1_thresh, tier2_thresh, tier1_rate, tier2_rate, tier3_rate
            )

    # Raw licensor cash flow
    licensor_cf_raw = [
        upfront_income[i] + dev_milestone_income[i] + reg_milestone_income[i] +
        comm_milestone_income[i] + royalty_income[i]
        for i in range(n)
    ]

    # Risk-adjusted licensor cash flow
    risk_adj = [0.0] * n
    for i in range(n):
        if i == 0:
            risk_adj[i] = upfront_income[0]
        elif i == 2:
            risk_adj[i] = dev_milestone_income[2] * p2_to_approval
        elif i == launch_idx:
            risk_adj[i] = reg_milestone_income[launch_idx] * full_prob
        elif i == launch_idx + 1 and launch_idx + 1 < n:
            risk_adj[i] = comm_milestone_income[launch_idx + 1] * full_prob
        else:
            risk_adj[i] = (royalty_income[i] + dev_milestone_income[i] +
                          reg_milestone_income[i] + comm_milestone_income[i]) * ptr[i]

    # Discounted licensor cash flow
    disc_licensor = [risk_adj[i] * df_lr[i] for i in range(n)]
    licensor_npv = sum(disc_licensor)

    # Bridge components (discounted values)
    upfront_pv = disc_licensor[0]
    dev_pv = disc_licensor[2] if 2 < n else 0.0
    reg_pv = disc_licensor[launch_idx] if launch_idx < n else 0.0
    comm_pv = disc_licensor[launch_idx + 1] if launch_idx + 1 < n else 0.0
    royalty_pv = sum(disc_licensor[launch_idx:])

    total_milestones_pv = upfront_pv + dev_pv + reg_pv + comm_pv

    return {
        "licensor_npv": licensor_npv,
        "risk_adj_licensor_cf": risk_adj,
        "raw_licensor_cf": licensor_cf_raw,
        "upfront_income": upfront_income,
        "dev_milestone_income": dev_milestone_income,
        "reg_milestone_income": reg_milestone_income,
        "comm_milestone_income": comm_milestone_income,
        "royalty_income": royalty_income,
        "disc_licensor": disc_licensor,
        "df_lr": df_lr.tolist(),
        "bridge": {
            "upfront_pv": upfront_pv,
            "dev_pv": dev_pv,
            "reg_pv": reg_pv,
            "comm_pv": comm_pv,
            "royalty_pv": royalty_pv,
            "total_milestones_pv": total_milestones_pv,
            "total_deal_value": licensor_npv,
        },
        "totals": {
            "upfront": upfront,
            "dev_milestone": dev_milestone,
            "reg_milestone": reg_milestone,
            "comm_milestone": comm_milestone,
            "total_royalties": sum(royalty_income),
            "total_milestones": sum(upfront_income) + sum(dev_milestone_income) +
                                 sum(reg_milestone_income) + sum(comm_milestone_income),
        }
    }


def register_callbacks(app):
    """Attach all callbacks to the Dash app instance."""

    # ==========================================================================
    # Sidebar navigation
    # ==========================================================================
    pages = ["dcf", "licensee", "mc", "bridge", "sens"]
    nav_ids = ["nav-dcf", "nav-licensee", "nav-mc", "nav-bridge", "nav-sens"]

    @app.callback(
        [Output(f"page-{p}", "style") for p in pages]
        + [Output(n, "active") for n in nav_ids],
        [Input(n, "n_clicks") for n in nav_ids],
    )
    def navigate(*_):
        ctx = dash.triggered
        if not ctx:
            active = "dcf"
        else:
            triggered_id = ctx[0]["prop_id"].split(".")[0]
            active = triggered_id.replace("nav-", "")

        styles = []
        for p in pages:
            styles.append({"display": "block" if p == active else "none"})

        actives = [p == active for p in pages]
        return styles + actives

    # ==========================================================================
    # Scenario dropdown
    # ==========================================================================
    @app.callback(
        Output("load-scenario-dropdown", "options"),
        Input("store-scenarios", "data"),
    )
    def update_dropdown(data):
        if not data:
            return []
        return [{"label": n, "value": n} for n in sorted(data.keys())]

    # ==========================================================================
    # Load scenario — auto-load on dropdown change
    # ==========================================================================
    @app.callback(
        [Output("in-pop", "value"), Output("in-price", "value"),
         Output("in-pen", "value"), Output("in-cogs", "value"),
         Output("in-tax", "value"), Output("in-asset-dr", "value"),
         Output("in-lsw", "value"), Output("in-lrw", "value"),
         Output("p1", "value"), Output("p2", "value"),
         Output("p3", "value"), Output("p4", "value"),
         Output("in-upfront", "value"), Output("in-mil", "value"),
         Output("scenario-name", "value")],
        Input("load-scenario-dropdown", "value"),
        State("store-scenarios", "data"),
    )
    def load_scenario(name, data):
        if not name or not data or name not in data:
            return (no_update,) * 13
        s = data[name]
        return (s["eu_pop"], s["price"], s["pen"], s["cogs"],
                s["tax"], s.get("asset_dr", 12), s["lsw"], s["lrw"],
                s["p1"], s["p2"], s["p3"], s["p4"], s["upfront"], s["mil"], name)

    # ==========================================================================
    # Run simulation
    # ==========================================================================
    @app.callback(
        Output("store-results", "data"),
        Output("run-status", "children"),
        Input("btn-run", "n_clicks"),
        State("in-pop", "value"), State("in-price", "value"),
        State("in-pen", "value"), State("in-cogs", "value"),
        State("in-tax", "value"), State("in-asset-dr", "value"),
        State("in-lsw", "value"), State("in-lrw", "value"),
        State("p1", "value"), State("p2", "value"),
        State("p3", "value"), State("p4", "value"),
        State("in-upfront", "value"), State("in-mil", "value"),
        # License terms (available for future use)
        State("in-dev-mil", "value"), State("in-reg-mil", "value"),
        State("in-comm-mil", "value"), State("in-roy-tier1", "value"),
        State("in-roy-tier2", "value"), State("in-roy-tier3", "value"),
        State("in-tier1-thresh", "value"), State("in-tier2-thresh", "value"),
        State("sl-sims", "value"),
        prevent_initial_call=True,
    )
    def run_sim(n_clicks, pop, price, pen, cogs, tax, asset_dr, lsw, lrw,
                p1, p2, p3, p4, upfront, mil,
                dev_mil, reg_mil, comm_mil, roy_tier1, roy_tier2, roy_tier3,
                tier1_thresh, tier2_thresh, n_sims):
        # License terms currently not used in calculation
        params = build_params(pop, price, pen, cogs, tax,
                              asset_dr, lsw, lrw,
                              p1, p2, p3, p4, upfront, mil)
        base = run_scenario(
            0.002, params.peak_pen, float(price or 15000),
            params.asset_discount_rate, params.licensee_wacc, params.licensor_discount_rate,
            params
        )
        ls, lr = run_montecarlo(int(n_sims or 5000), params, float(price or 15000))
        ls_s = npv_stats(ls)
        lr_s = npv_stats(lr)

        return {
            "ls_npvs": ls.tolist(), "lr_npvs": lr.tolist(),
            "ls_stats": ls_s, "lr_stats": lr_s,
            "base_rev": base["rev"].tolist(),
            "base_fcf": base["fcf"].tolist(),
            "base_rfcf": base["risk_adj_fcf"].tolist(),
            "base_ebitda": base["ebitda"].tolist(),
            "base_cogs": base["cogs"].tolist(),
            "base_royalty": base["royalty"].tolist(),
            "base_ptr": base["ptr"].tolist(),
            "base_df_asset": base["df_asset"].tolist(),
            "base_df_ls": base["df_ls"].tolist(),
            "base_lf_cf": base["licensor_cf"].tolist(),
            "base_rnpv": base["asset_rnpv"],
            "base_enpv": base["licensee_enpv"],
            "base_lr_npv": base["licensor_npv"],
        }, (
            f"✅ {int(n_sims):,} iters  |  "
            f"rNPV: ${base['asset_rnpv']:.1f}M  |  "
            f"eNPV: ${base['licensee_enpv']:.1f}M  |  "
            f"P>0: {ls_s['prob_pos']*100:.1f}%"
        )

    # ==========================================================================
    # Save / Delete / Export
    # ==========================================================================
    @app.callback(
        Output("store-scenarios", "data"),
        Output("save-status", "children"),
        Input("btn-save", "n_clicks"),
        State("scenario-name", "value"),
        State("in-pop", "value"), State("in-price", "value"),
        State("in-pen", "value"), State("in-cogs", "value"),
        State("in-tax", "value"), State("in-asset-dr", "value"),
        State("in-lsw", "value"), State("in-lrw", "value"),
        State("p1", "value"), State("p2", "value"),
        State("p3", "value"), State("p4", "value"),
        State("in-upfront", "value"), State("in-mil", "value"),
        # License terms (available for future use)
        State("in-dev-mil", "value"), State("in-reg-mil", "value"),
        State("in-comm-mil", "value"), State("in-roy-tier1", "value"),
        State("in-roy-tier2", "value"), State("in-roy-tier3", "value"),
        State("in-tier1-thresh", "value"), State("in-tier2-thresh", "value"),
        State("store-scenarios", "data"),
        prevent_initial_call=True,
    )
    def save_scenario(n_clicks, name, pop, price, pen, cogs, tax,
                      asset_dr, lsw, lrw, p1, p2, p3, p4, upfront, mil,
                      dev_mil, reg_mil, comm_mil, roy_tier1, roy_tier2, roy_tier3,
                      tier1_thresh, tier2_thresh, data):
        if not name or not name.strip():
            return data or {}, "❌ Enter a name"
        n = name.strip()
        s = data or {}
        s[n] = {
            "eu_pop": float(pop or 450), "price": float(price or 15000),
            "pen": float(pen or 5), "cogs": float(cogs or 12),
            "tax": float(tax or 21), "asset_dr": float(asset_dr or 12),
            "lsw": float(lsw or 10), "lrw": float(lrw or 14),
            "p1": float(p1 or 63), "p2": float(p2 or 30),
            "p3": float(p3 or 58), "p4": float(p4 or 90),
            "upfront": float(upfront or 2), "mil": float(mil or 1),
            # License terms saved for future use
            "dev_mil": float(dev_mil or 1),
            "reg_mil": float(reg_mil or 2),
            "comm_mil": float(comm_mil or 0),
            "roy_tier1": float(roy_tier1 or 5),
            "roy_tier2": float(roy_tier2 or 7),
            "roy_tier3": float(roy_tier3 or 9),
            "tier1_thresh": float(tier1_thresh or 100),
            "tier2_thresh": float(tier2_thresh or 200),
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return s, f"✅ Saved: {n}"

    @app.callback(
        Output("store-scenarios", "data"),
        Output("save-status", "children"),
        Input("btn-delete", "n_clicks"),
        State("load-scenario-dropdown", "value"),
        State("store-scenarios", "data"),
        prevent_initial_call=True,
    )
    def delete_scenario(n_clicks, name, data):
        if not name or not data or name not in data:
            return data or {}, "❌ Select a scenario"
        return {k: v for k, v in data.items() if k != name}, f"🗑️ Deleted: {name}"

    @app.callback(
        Output("download-export", "data"),
        Input("btn-export", "n_clicks"),
        State("scenario-name", "value"),
        State("in-pop", "value"), State("in-price", "value"),
        State("in-pen", "value"), State("in-cogs", "value"),
        State("in-tax", "value"), State("in-asset-dr", "value"),
        State("in-lsw", "value"), State("in-lrw", "value"),
        State("p1", "value"), State("p2", "value"),
        State("p3", "value"), State("p4", "value"),
        State("in-upfront", "value"), State("in-mil", "value"),
        # License terms (available for future use)
        State("in-dev-mil", "value"), State("in-reg-mil", "value"),
        State("in-comm-mil", "value"), State("in-roy-tier1", "value"),
        State("in-roy-tier2", "value"), State("in-roy-tier3", "value"),
        State("in-tier1-thresh", "value"), State("in-tier2-thresh", "value"),
        State("store-results", "data"),
        prevent_initial_call=True,
    )
    def export(n_clicks, name, pop, price, pen, cogs, tax, asset_dr, lsw, lrw,
               p1, p2, p3, p4, upfront, mil,
               dev_mil, reg_mil, comm_mil, roy_tier1, roy_tier2, roy_tier3,
               tier1_thresh, tier2_thresh, results):
        n = name or "Export"
        d = {
            "scenario_name": n, "exported_at": datetime.now().isoformat(),
            "assumptions": {
                "eu_pop": float(pop or 450), "price": float(price or 15000),
                "penetration": float(pen or 5), "cogs_pct": float(cogs or 12),
                "tax_rate": float(tax or 21),
                "asset_discount_rate": float(asset_dr or 12),
                "licensee_wacc": float(lsw or 10),
                "licensor_discount_rate": float(lrw or 14),
                "ph1_to_ph2": float(p1 or 63),
                "ph2_to_ph3": float(p2 or 30), "ph3_to_nda": float(p3 or 58),
                "nda_approval": float(p4 or 90), "upfront": float(upfront or 2),
                "milestones": float(mil or 1),
                # License terms (for future use)
                "dev_milestone": float(dev_mil or 1),
                "reg_milestone": float(reg_mil or 2),
                "comm_milestone": float(comm_mil or 0),
                "royalty_tier_1_rate": float(roy_tier1 or 5),
                "royalty_tier_2_rate": float(roy_tier2 or 7),
                "royalty_tier_3_rate": float(roy_tier3 or 9),
                "royalty_tier_1_threshold": float(tier1_thresh or 100),
                "royalty_tier_2_threshold": float(tier2_thresh or 200),
            },
            "results": results or {},
        }
        return dcc.send_string(json.dumps(d, indent=2), f"{n}_NPV_Analysis.json")

    # ==========================================================================
    # Summary cards
    # ==========================================================================
    @app.callback(
        Output("summary-dcf-lic-mean", "children"),
        Output("summary-dcf-lic-prob", "children"),
        Output("summary-dcf-lr-mean", "children"),
        Output("summary-dcf-lr-prob", "children"),
        Output("summary-mc-lic-mean", "children"),
        Output("summary-mc-lic-prob", "children"),
        Output("summary-mc-lr-mean", "children"),
        Output("summary-mc-lr-prob", "children"),
        Output("summary-br-lic-mean", "children"),
        Output("summary-br-lic-prob", "children"),
        Output("summary-br-lr-mean", "children"),
        Output("summary-br-lr-prob", "children"),
        Output("summary-se-lic-mean", "children"),
        Output("summary-se-lic-prob", "children"),
        Output("summary-se-lr-mean", "children"),
        Output("summary-se-lr-prob", "children"),
        Input("store-results", "data"),
    )
    def update_cards(data):
        if not data:
            e = kpi_card("—", "—")
            return [e] * 16
        ls, lr = data["ls_stats"], data["lr_stats"]
        card1 = kpi_card("Licensee Mean eNPV", f"${ls['mean']:.1f}M", COLORS["blue"],
                         f"P5: ${ls['p5']:.1f}M  |  P95: ${ls['p95']:.1f}M")
        card2 = kpi_card("P(Licensee eNPV > 0)", f"{ls['prob_pos']*100:.1f}%", COLORS["green"],
                         f"Median: ${ls['p50']:.1f}M")
        card3 = kpi_card("Licensor Deal NPV", f"${lr['mean']:.1f}M", COLORS["teal"],
                         f"P5: ${lr['p5']:.1f}M  |  P95: ${lr['p95']:.1f}M")
        card4 = kpi_card("P(Licensor NPV > 0)", f"{lr['prob_pos']*100:.1f}%", COLORS["amber"],
                         f"Median: ${lr['p50']:.1f}M")
        return [card1, card2, card3, card4] * 4

    # ==========================================================================
    # Sidebar mini DCF
    # ==========================================================================
    @app.callback(
        Output("sidebar-dcf-mini", "children"),
        Input("store-results", "data"),
    )
    def update_sidebar_dcf(data):
        if not data:
            return html.Span("Run simulation", style={"fontSize": "0.75rem", "color": "#667085"})

        base_mock = {k: np.array(data[k]) for k in
                     ["base_rev", "base_cogs", "base_ebitda", "base_royalty",
                      "base_fcf", "base_rfcf", "base_ptr", "base_df_ls"]}
        from ui import build_dcf_table
        columns, rows, metric_rows = build_dcf_table(base_mock)

        total = data["base_enpv"]
        table = dash_table.DataTable(
            data=rows, columns=columns,
            style_table={"fontSize": "9px", "overflowX": "auto"},
            style_cell={"fontFamily": "monospace", "fontSize": "9px", "padding": "1px 3px",
                        "border": "1px solid #e9ecef", "textAlign": "right",
                        "minWidth": "38px", "maxWidth": "48px"},
            style_header={"backgroundColor": "#1f6feb", "color": "white", "fontSize": "9px",
                          "fontWeight": "700", "padding": "2px 2px"},
            style_data_conditional=[
                {"if": {"column_id": "Line Item"},
                 "fontWeight": "600", "textAlign": "left",
                 "minWidth": "90px", "maxWidth": "90px", "fontSize": "9px"},
            ],
            fixed_columns={"headers": True, "data": 1},
            page_action="none",
        )
        return html.Div([
            html.Div(f"eNPV: ${total:.1f}M  |  Lic: ${data['base_lr_npv']:.1f}M",
                     style={"fontSize": "10px", "fontWeight": "700", "color": "#1f6feb",
                            "padding": "4px", "backgroundColor": "#eef1f5", "borderRadius": "4px",
                            "marginBottom": "4px"}),
            table,
        ])

    # ==========================================================================
    # Charts
    # ==========================================================================
    @app.callback(
        Output("cf-chart", "figure"),
        Input("store-results", "data"),
    )
    def update_cf_chart(data):
        if not data:
            return go.Figure()
        rev = data["base_rev"]
        rfcf = data["base_rfcf"]
        ebit = data["base_ebitda"]
        cogs = data["base_cogs"]
        rd_arr = np.array([RD_SCHEDULE.get(i, 0.0) for i in range(N_YEARS)])

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            subplot_titles=("Revenue Build-Up ($M)", "Risk-Adjusted FCF vs EBITDA ($M)"),
                            vertical_spacing=0.12, row_heights=[0.55, 0.45])
        fig.add_trace(go.Bar(x=YEARS, y=rev, name="Gross Revenue", marker_color=COLORS["blue"], opacity=0.85), row=1, col=1)
        fig.add_trace(go.Bar(x=YEARS, y=[-v for v in cogs], name="COGS", marker_color=COLORS["red"], opacity=0.7), row=1, col=1)
        fig.add_trace(go.Bar(x=YEARS, y=[-v for v in rd_arr], name="R&D", marker_color="#667085", opacity=0.7), row=1, col=1)
        fig.add_trace(go.Scatter(x=YEARS, y=ebit, name="EBITDA",
                                 line=dict(color=COLORS["amber"], width=2.5), mode="lines+markers"), row=1, col=1)
        colors_fcf = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in rfcf]
        fig.add_trace(go.Bar(x=YEARS, y=rfcf, name="Risk-Adj FCF", marker_color=colors_fcf, opacity=0.85), row=2, col=1)
        fig.add_trace(go.Scatter(x=YEARS, y=list(np.cumsum(rfcf)), name="Cumulative",
                                 line=dict(color=COLORS["blue"], width=2, dash="dot")), row=2, col=1)
        fig.add_hline(y=0, line_width=1, line_color="black", opacity=0.4, row=2, col=1)
        fig.update_layout(template="plotly_white", height=500,
                          legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
                          margin=dict(t=50, b=30))
        return fig

    @app.callback(
        Output("mc-chart", "figure"),
        Input("store-results", "data"),
    )
    def update_mc_chart(data):
        if not data:
            return go.Figure()
        ls, lr = np.array(data["ls_npvs"]), np.array(data["lr_npvs"])
        ls_s, lr_s = data["ls_stats"], data["lr_stats"]

        fig = make_subplots(rows=2, cols=2,
                            subplot_titles=("Licensee eNPV", "Licensor NPV",
                                            "S-Curve", "Percentiles"),
                            vertical_spacing=0.18, horizontal_spacing=0.1)
        fig.add_trace(go.Histogram(x=ls, nbinsx=60, name="Licensee",
                                   marker_color=COLORS["blue"], opacity=0.75), row=1, col=1)
        fig.add_vline(x=ls_s["mean"], line_color=COLORS["amber"], line_width=2, line_dash="dash", row=1, col=1)
        fig.add_vline(x=0, line_color="black", line_width=1, row=1, col=1)

        fig.add_trace(go.Histogram(x=lr, nbinsx=60, name="Licensor",
                                   marker_color=COLORS["teal"], opacity=0.75), row=1, col=2)
        fig.add_vline(x=lr_s["mean"], line_color=COLORS["amber"], line_width=2, line_dash="dash", row=1, col=2)
        fig.add_vline(x=0, line_color="black", line_width=1, row=1, col=2)

        n = len(ls)
        cdf = np.arange(1, n + 1) / n
        fig.add_trace(go.Scatter(x=np.sort(ls), y=cdf * 100, name="Licensee CDF",
                                 line=dict(color=COLORS["blue"], width=2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=np.sort(lr), y=cdf * 100, name="Licensor CDF",
                                 line=dict(color=COLORS["teal"], width=2)), row=2, col=1)
        fig.add_hline(y=50, line_color="#667085", line_dash="dot", row=2, col=1)

        pcts = ["P5", "P10", "P25", "P50", "P75", "P90", "P95"]
        ls_v = [ls_s[p] for p in ["p5", "p10", "p25", "p50", "p75", "p90", "p95"]]
        lr_v = [lr_s[p] for p in ["p5", "p10", "p25", "p50", "p75", "p90", "p95"]]
        fig.add_trace(go.Bar(x=pcts, y=ls_v, name="Licensee", marker_color=COLORS["blue"]), row=2, col=2)
        fig.add_trace(go.Bar(x=pcts, y=lr_v, name="Licensor", marker_color=COLORS["teal"]), row=2, col=2)

        fig.update_layout(template="plotly_white", height=600,
                          legend=dict(orientation="h", y=1.04, x=0.5, xanchor="center"),
                          margin=dict(t=60, b=30))
        fig.add_annotation(text=f"P>0 = {ls_s['prob_pos']*100:.1f}%",
                           xref="x domain", yref="y domain", x=0.98, y=0.92,
                           showarrow=False, font=dict(color=COLORS["blue"], size=11), row=1, col=1)
        return fig

    @app.callback(
        Output("licensor-npv", "children"),
        Output("licensor-total-milestones", "children"),
        Output("licensor-total-royalties", "children"),
        Output("licensor-total-deal-value", "children"),
        Output("bridge-chart", "figure"),
        Output("bridge-annual-chart", "figure"),
        Input("store-results", "data"),
        State("in-asset-dr", "value"), State("in-lrw", "value"),
        State("in-upfront", "value"),
        State("in-dev-mil", "value"), State("in-reg-mil", "value"),
        State("in-comm-mil", "value"),
        State("in-roy-tier1", "value"), State("in-roy-tier2", "value"),
        State("in-roy-tier3", "value"),
        State("in-tier1-thresh", "value"), State("in-tier2-thresh", "value"),
    )
    def update_licensor(data, asset_dr, lrw, upfront,
                        dev_mil, reg_mil, comm_mil,
                        roy_t1, roy_t2, roy_t3, t1_thresh, t2_thresh):
        if not data:
            empty = "—"
            return empty, empty, empty, empty, go.Figure(), go.Figure()

        base_arrays = data

        # Build licensor data from engine output
        params = {
            "price": base_arrays.get("price"),
            "lsw": float(asset_dr or 12) / 100,
            "lrw": float(lrw or 14) / 100,
            "upfront": float(upfront or 2.0),
            "dev_mil": float(dev_mil or 1.0),
            "reg_mil": float(reg_mil or 2.0),
            "comm_mil": float(comm_mil or 0.0),
            "roy_tier1": float(roy_t1 or 5.0),
            "roy_tier2": float(roy_t2 or 7.0),
            "roy_tier3": float(roy_t3 or 9.0),
            "tier1_thresh": float(t1_thresh or 100.0),
            "tier2_thresh": float(t2_thresh or 200.0),
            "royalty_start": 2033,
        }
        lrw_rate = float(lrw or 14) / 100
        df_lr = np.array([(1 / (1 + lrw_rate)) ** i for i in range(N_YEARS)])
        ptr = np.array(base_arrays.get("base_ptr", [1.0] * N_YEARS))

        lic = build_licensor_data(params, base_arrays, ptr, df_lr)
        b = lic["bridge"]
        t = lic["totals"]

        # Summary cards
        npv_str = f"${lic['licensor_npv']:.1f}M"
        mil_str = f"${t['total_milestones']:.1f}M"
        roy_str = f"${t['total_royalties']:.1f}M"
        deal_str = f"${lic['licensor_npv']:.1f}M"

        # Bridge waterfall chart
        fig1 = go.Figure(go.Waterfall(
            x=["Upfront", "Dev Milestone", "Reg Milestone", "Comm Milestone", "Royalties", "Total"],
            measure=["relative", "relative", "relative", "relative", "relative", "total"],
            y=[b["upfront_pv"], b["dev_pv"], b["reg_pv"], b["comm_pv"], b["royalty_pv"], 0],
            text=[f"${b['upfront_pv']:.1f}M", f"${b['dev_pv']:.1f}M",
                  f"${b['reg_pv']:.1f}M", f"${b['comm_pv']:.1f}M",
                  f"${b['royalty_pv']:.1f}M", f"${lic['licensor_npv']:.1f}M"],
            textposition="inside",
            connector={"line": {"color": "#ccc"}},
            increasing={"marker": {"color": COLORS["blue"]}},
            totals={"marker": {"color": COLORS["teal"]}},
        ))
        fig1.update_layout(
            template="plotly_white", height=340,
            title=f"Licensor Deal NPV Bridge — ${lic['licensor_npv']:.1f}M",
            margin=dict(t=40, b=20)
        )

        # Annual cash flow chart
        colors_lc = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in lic["risk_adj_licensor_cf"]]
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=list(YEARS), y=lic["risk_adj_licensor_cf"],
            name="Risk-Adj CF", marker_color=colors_lc
        ))
        disc_cum = np.cumsum(lic["disc_licensor"])
        fig2.add_trace(go.Scatter(
            x=list(YEARS), y=list(disc_cum), name="Cum. PV",
            line=dict(color=COLORS["amber"], width=2)
        ))
        fig2.update_layout(
            template="plotly_white", height=280,
            title="Annual Risk-Adjusted Licensor CF",
            margin=dict(t=30, b=20),
            legend=dict(orientation="h", y=1.06)
        )

        return npv_str, mil_str, roy_str, deal_str, fig1, fig2

    # ==========================================================================
    # Sensitivity / Tornado
    # ==========================================================================
    @app.callback(
        Output("sensitivity-tornado-chart", "figure"),
        Output("sensitivity-table", "data"),
        Output("sensitivity-table", "columns"),
        Output("sens-base-npv", "children"),
        Input("store-results", "data"),
        Input("sens-metric", "value"),
    )
    def update_sensitivity(data, metric):
        if not data:
            return go.Figure(), [], [], ""

        metric_key = metric or "core_dcf_npv"
        assumptions = dict(DEFAULT_ASSUMPTIONS)

        assumptions["asset_discount_rate"] = 12.0
        assumptions["licensee_wacc"] = 10.0
        assumptions["licensor_discount_rate"] = 14.0
        assumptions["peak_penetration"] = 5.0
        assumptions["price_per_unit"] = 15000.0
        assumptions["cogs_pct"] = 12.0
        assumptions["target_patient_pct"] = 9.0

        df = run_sensitivity(assumptions, selected_metric=metric_key)

        base_rnpv = data.get("base_rnpv", 0.0)
        base_enpv = data.get("base_enpv", 0.0)
        base_lr_npv = data.get("base_lr_npv", 0.0)
        if metric_key == "licensee_npv":
            base_display = f"Base: ${base_enpv:.1f}M"
        elif metric_key == "licensor_npv":
            base_display = f"Base: ${base_lr_npv:.1f}M"
        else:
            base_display = f"Base: ${base_rnpv:.1f}M"

        fig = go.Figure()
        for _, row in df.iterrows():
            base_npv = row["base_npv"]
            lo_delta = row["delta_low"]
            hi_delta = row["delta_high"]
            label = row["variable"]

            if lo_delta < 0:
                lo_bar = lo_delta
                hi_bar = hi_delta
            else:
                lo_bar = lo_delta
                hi_bar = hi_delta

            fig.add_trace(go.Bar(
                y=[label], x=[lo_delta],
                orientation="h", marker_color=COLORS["red"],
                showlegend=False, name="Downside"
            ))
            fig.add_trace(go.Bar(
                y=[label], x=[hi_delta],
                orientation="h", marker_color=COLORS["blue"],
                showlegend=False, name="Upside"
            ))

        fig.add_vline(x=0, line_color="black", line_width=1.5)
        fig.update_layout(
            template="plotly_white", height=400,
            title=f"Tornado — {metric_key.replace('_', ' ').title()}",
            xaxis_title="Δ NPV ($M)", margin=dict(l=160, t=40, b=30),
            barmode="relative",
            showlegend=False,
        )

        table_data = []
        for _, row in df.iterrows():
            table_data.append({
                "Variable": row["variable"],
                "Low": row["low_case"],
                "Base": row["base_case"],
                "High": row["high_case"],
                "Δ Low": f"{row['delta_low']:.1f}",
                "Δ High": f"{row['delta_high']:.1f}",
                "Impact": f"{row['absolute_impact']:.1f}",
            })

        table_cols = [
            {"name": "Variable", "id": "Variable"},
            {"name": "Low Case", "id": "Low"},
            {"name": "Base Case", "id": "Base"},
            {"name": "High Case", "id": "High"},
            {"name": "Δ Low ($M)", "id": "Δ Low"},
            {"name": "Δ High ($M)", "id": "Δ High"},
            {"name": "|Impact| ($M)", "id": "Impact"},
        ]

        return fig, table_data, table_cols, base_display

    # ==========================================================================
    # Licensee Model page
    # ==========================================================================
    @app.callback(
        Output("licensee-npv", "children"),
        Output("licensee-total-payments", "children"),
        Output("licensee-peak-revenue", "children"),
        Output("licensee-wacc-output", "children"),
        Output("licensee-annual-cf-chart", "figure"),
        Output("licensee-cumulative-pv-chart", "figure"),
        Input("store-results", "data"),
        State("in-lsw", "value"),
    )
    def update_licensee(data, lsw):
        if not data:
            empty = "—"
            return empty, empty, empty, empty, go.Figure(), go.Figure()

        fcf = np.array(data.get("base_fcf", [0.0] * N_YEARS))
        royalty = np.array(data.get("base_royalty", [0.0] * N_YEARS))
        ptr = np.array(data.get("base_ptr", [1.0] * N_YEARS))
        rev = np.array(data.get("base_rev", [0.0] * N_YEARS))
        disc_factor_ls = np.array(data.get("base_df_ls", [1.0] * N_YEARS))
        licensor_cf = np.array(data.get("base_lf_cf", [0.0] * N_YEARS))

        licensee_npv = data.get("base_enpv", 0.0)
        total_payments = float(np.sum(licensor_cf))
        peak_rev = float(np.max(rev))
        wacc_val = float(lsw or 10.0)

        licensee_cf = fcf - royalty
        risk_adj_cf = licensee_cf * ptr
        disc_cum = np.cumsum(risk_adj_cf * disc_factor_ls)

        npv_str = f"${licensee_npv:.1f}M"
        payments_str = f"${total_payments:.1f}M"
        peak_str = f"${peak_rev:.1f}M"
        wacc_str = f"{wacc_val:.1f}%"

        colors = [COLORS["blue"] if v >= 0 else COLORS["red"] for v in risk_adj_cf]

        fig1 = go.Figure()
        fig1.add_trace(go.Bar(x=list(YEARS), y=risk_adj_cf.tolist(),
                              name="Risk-Adj CF", marker_color=colors, opacity=0.85))
        fig1.update_layout(
            template="plotly_white", height=300,
            title="Annual Risk-Adjusted Licensee CF",
            xaxis_title="Year", yaxis_title="$M",
            margin=dict(t=30, b=20),
            legend=dict(orientation="h", y=1.06)
        )

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=list(YEARS), y=disc_cum.tolist(),
                                  name="Cum. PV (Lic. WACC)",
                                  line=dict(color=COLORS["blue"], width=2.5),
                                  fill="tozeroy", fillcolor="rgba(31,111,235,0.1)"))
        fig2.update_layout(
            template="plotly_white", height=280,
            title="Cumulative Discounted Licensee CF",
            xaxis_title="Year", yaxis_title="$M (PV)",
            margin=dict(t=30, b=20),
            legend=dict(orientation="h", y=1.06)
        )

        return npv_str, payments_str, peak_str, wacc_str, fig1, fig2
