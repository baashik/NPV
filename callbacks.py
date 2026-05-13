"""NPV Model — Dash callbacks."""

import json
from datetime import datetime
import numpy as np
from dash import html, no_update, dcc, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from config import ScenarioParams, N_YEARS, YEARS, COLORS, RD_SCHEDULE, build_params
from engine import run_scenario, run_montecarlo, npv_stats, run_sensitivity
from ui import kpi_card
from styles import CARD


def register_callbacks(app):
    """Attach all callbacks to the Dash app instance."""

    # ==========================================================================
    # Sidebar navigation
    # ==========================================================================
    pages = ["dcf", "mc", "bridge", "sens"]
    nav_ids = ["nav-dcf", "nav-mc", "nav-bridge", "nav-sens"]

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
         Output("in-tax", "value"), Output("in-lsw", "value"),
         Output("in-lrw", "value"), Output("p1", "value"),
         Output("p2", "value"), Output("p3", "value"),
         Output("p4", "value"), Output("in-upfront", "value"),
         Output("in-mil", "value"), Output("scenario-name", "value")],
        Input("load-scenario-dropdown", "value"),
        State("store-scenarios", "data"),
    )
    def load_scenario(name, data):
        if not name or not data or name not in data:
            return (no_update,) * 14
        s = data[name]
        return (s["eu_pop"], s["price"], s["pen"], s["cogs"],
                s["tax"], s["lsw"], s["lrw"], s["p1"], s["p2"],
                s["p3"], s["p4"], s["upfront"], s["mil"], name)

    # ==========================================================================
    # Run simulation
    # ==========================================================================
    @app.callback(
        Output("store-results", "data"),
        Output("run-status", "children"),
        Input("btn-run", "n_clicks"),
        State("in-pop", "value"), State("in-price", "value"),
        State("in-pen", "value"), State("in-cogs", "value"),
        State("in-tax", "value"), State("in-lsw", "value"),
        State("in-lrw", "value"), State("p1", "value"),
        State("p2", "value"), State("p3", "value"),
        State("p4", "value"), State("in-upfront", "value"),
        State("in-mil", "value"), State("sl-sims", "value"),
        prevent_initial_call=True,
    )
    def run_sim(n_clicks, pop, price, pen, cogs, tax, lsw, lrw,
                p1, p2, p3, p4, upfront, mil, n_sims):
        params = build_params(pop, price, pen, cogs, tax, lsw, lrw,
                              p1, p2, p3, p4, upfront, mil)
        base = run_scenario(0.002, params.peak_pen, float(price or 15000),
                            float(lsw or 10) / 100, float(lrw or 14) / 100, params)
        ls, lr = run_montecarlo(int(n_sims or 5000), params, float(price or 15000))
        ls_s = npv_stats(ls)
        lr_s = npv_stats(lr)
        sens = run_sensitivity(params, float(price or 15000), base["licensee_enpv"])

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
            "base_df_ls": base["df_ls"].tolist(),
            "base_lf_cf": base["licensor_cf"].tolist(),
            "base_enpv": base["licensee_enpv"],
            "base_lr_npv": base["licensor_npv"],
            "sens_rows": sens,
        }, (
            f"✅ {int(n_sims):,} iters  |  "
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
        State("in-tax", "value"), State("in-lsw", "value"),
        State("in-lrw", "value"), State("p1", "value"),
        State("p2", "value"), State("p3", "value"),
        State("p4", "value"), State("in-upfront", "value"),
        State("in-mil", "value"), State("store-scenarios", "data"),
        prevent_initial_call=True,
    )
    def save_scenario(n_clicks, name, pop, price, pen, cogs, tax,
                      lsw, lrw, p1, p2, p3, p4, upfront, mil, data):
        if not name or not name.strip():
            return data or {}, "❌ Enter a name"
        n = name.strip()
        s = data or {}
        s[n] = {
            "eu_pop": float(pop or 450), "price": float(price or 15000),
            "pen": float(pen or 5), "cogs": float(cogs or 12),
            "tax": float(tax or 21), "lsw": float(lsw or 10),
            "lrw": float(lrw or 14), "p1": float(p1 or 63),
            "p2": float(p2 or 30), "p3": float(p3 or 58),
            "p4": float(p4 or 90), "upfront": float(upfront or 2),
            "mil": float(mil or 1),
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
        State("in-tax", "value"), State("in-lsw", "value"),
        State("in-lrw", "value"), State("p1", "value"),
        State("p2", "value"), State("p3", "value"),
        State("p4", "value"), State("in-upfront", "value"),
        State("in-mil", "value"), State("store-results", "data"),
        prevent_initial_call=True,
    )
    def export(n_clicks, name, pop, price, pen, cogs, tax, lsw, lrw,
               p1, p2, p3, p4, upfront, mil, results):
        n = name or "Export"
        d = {
            "scenario_name": n, "exported_at": datetime.now().isoformat(),
            "assumptions": {
                "eu_pop": float(pop or 450), "price": float(price or 15000),
                "penetration": float(pen or 5), "cogs_pct": float(cogs or 12),
                "tax_rate": float(tax or 21), "licensee_wacc": float(lsw or 10),
                "licensor_wacc": float(lrw or 14), "ph1_to_ph2": float(p1 or 63),
                "ph2_to_ph3": float(p2 or 30), "ph3_to_nda": float(p3 or 58),
                "nda_approval": float(p4 or 90), "upfront": float(upfront or 2),
                "milestones": float(mil or 1),
            },
            "results": results or {},
        }
        return dcc.send_string(json.dumps(d, indent=2), f"{n}_NPV_Analysis.json")

    # ==========================================================================
    # Summary cards
    # ==========================================================================
    @app.callback(
        Output("summary-lic-mean", "children"),
        Output("summary-lic-prob", "children"),
        Output("summary-lr-mean", "children"),
        Output("summary-lr-prob", "children"),
        Input("store-results", "data"),
    )
    def update_cards(data):
        if not data:
            e = kpi_card("—", "—")
            return e, e, e, e
        ls, lr = data["ls_stats"], data["lr_stats"]
        return (
            kpi_card("Licensee Mean eNPV", f"${ls['mean']:.1f}M", COLORS["blue"],
                     f"P5: ${ls['p5']:.1f}M  |  P95: ${ls['p95']:.1f}M"),
            kpi_card("P(Licensee eNPV > 0)", f"{ls['prob_pos']*100:.1f}%", COLORS["green"],
                     f"Median: ${ls['p50']:.1f}M"),
            kpi_card("Licensor Deal NPV", f"${lr['mean']:.1f}M", COLORS["teal"],
                     f"P5: ${lr['p5']:.1f}M  |  P95: ${lr['p95']:.1f}M"),
            kpi_card("P(Licensor NPV > 0)", f"{lr['prob_pos']*100:.1f}%", COLORS["amber"],
                     f"Median: ${lr['p50']:.1f}M"),
        )

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
        Output("bridge-chart", "figure"),
        Output("bridge-annual-chart", "figure"),
        Input("store-results", "data"),
    )
    def update_bridge(data):
        if not data:
            return go.Figure(), go.Figure()
        lf_cf = np.array(data["base_lf_cf"])
        df_lr = np.array([(1 / (1 + 0.14)) ** i for i in range(N_YEARS)])
        disc = lf_cf * df_lr
        up = disc[0]
        ms = sum(disc[i] for i in [2, 4, 6] if i < N_YEARS)
        roy = sum(disc[i] for i in range(N_YEARS) if i not in [0, 2, 4, 6] and disc[i] > 0)

        fig1 = go.Figure(go.Waterfall(
            x=["Upfront", "Milestones", "Royalty", "Total"],
            measure=["relative", "relative", "relative", "total"],
            y=[up, ms, roy, 0],
            text=[f"${up:.1f}M", f"${ms:.1f}M", f"${roy:.1f}M", f"${data['base_lr_npv']:.1f}M"],
            textposition="inside",
            connector={"line": {"color": "#ccc"}},
            increasing={"marker": {"color": COLORS["blue"]}},
            totals={"marker": {"color": COLORS["teal"]}},
        ))
        fig1.update_layout(template="plotly_white", height=340,
                           title=f"Licensor NPV Bridge — ${data['base_lr_npv']:.1f}M",
                           margin=dict(t=40, b=20))

        colors_lc = [COLORS["teal"] if v >= 0 else COLORS["red"] for v in lf_cf]
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=list(YEARS), y=list(lf_cf), name="Cash Flow", marker_color=colors_lc))
        fig2.add_trace(go.Scatter(x=list(YEARS), y=list(np.cumsum(disc)), name="Cum. PV",
                                  line=dict(color=COLORS["amber"], width=2)))
        fig2.update_layout(template="plotly_white", height=280,
                           title="Annual Licensor CF", margin=dict(t=30, b=20))
        return fig1, fig2

    @app.callback(
        Output("tornado-chart", "figure"),
        Output("price-sens-chart", "figure"),
        Input("store-results", "data"),
    )
    def update_sens(data):
        if not data:
            return go.Figure(), go.Figure()
        sens = data["sens_rows"]
        base_e = data["base_enpv"]

        labels = [r["label"] for r in sens]
        lo = [r["npv_lo"] for r in sens]
        hi = [r["npv_hi"] for r in sens]
        order = np.argsort([abs(h - l) for l, h in zip(lo, hi)])

        fig1 = go.Figure()
        for i in order:
            lb, lv, hv = labels[i], lo[i], hi[i]
            fig1.add_trace(go.Bar(y=[lb], x=[max(lv, hv) - base_e], name="Upside",
                                  orientation="h", marker_color=COLORS["blue"], showlegend=False))
            fig1.add_trace(go.Bar(y=[lb], x=[min(lv, hv) - base_e], name="Downside",
                                  orientation="h", marker_color=COLORS["red"], showlegend=False))
        fig1.add_vline(x=0, line_color="black", line_width=1.5)
        fig1.update_layout(template="plotly_white", height=360,
                           title=f"Tornado (Base: ${base_e:.1f}M)",
                           xaxis_title="Δ eNPV ($M)", margin=dict(l=140, t=40, b=20))

        prices = np.linspace(5000, 40000, 50)
        enpv = []
        for pv in prices:
            p = ScenarioParams(eu_pop=450, ts=0.09, dr=0.80, tr=0.50,
                               cogs=0.12, ga=0.01, tax=0.21, upfront=2.0,
                               p1=0.63, p2=0.30, p3=0.58, p4=0.90, peak_pen=0.05)
            enpv.append(run_scenario(0.002, 0.05, pv, 0.10, 0.14, p)["licensee_enpv"])

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=prices / 1000, y=enpv, mode="lines",
                                  line=dict(color=COLORS["blue"], width=2.5),
                                  fill="tozeroy", fillcolor="rgba(31,111,235,0.1)"))
        fig2.add_hline(y=0, line_color="black", line_dash="dash")
        fig2.update_layout(template="plotly_white", height=260,
                           title="Price Sensitivity",
                           xaxis_title="Price ($K/patient/yr)",
                           yaxis_title="eNPV ($M)", margin=dict(t=30, b=20))
        return fig1, fig2
