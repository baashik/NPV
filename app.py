import pandas as pd
import numpy as np
import plotly.express as px
from dash import Dash, html, dcc, Input, Output, State, callback
import dash_ag_grid as dag

app = Dash(__name__)
server = app.server

app.layout = html.Div([
    html.H1("Biotech NPV Engine"),
    dag.AgGrid(
        id="grid",
        rowData=[{"Year": f"Year {i}", "Cost": 10.0} for i in range(1, 11)],
        columnDefs=[{"field": "Year"}, {"field": "Cost", "editable": True}],
    ),
    html.Button("Run Simulation", id="run-btn"),
    dcc.Graph(id="graph")
])

@callback(
    Output("graph", "figure"),
    Input("run-btn", "n_clicks"),
    State("grid", "rowData"),
    prevent_initial_call=True
)
def update(n, rows):
    costs = [float(r["Cost"]) for r in rows]
    total_cost = sum(costs)
    res = [
        np.random.normal(600, 100) - total_cost
        if np.random.rand() > 0.5 else -total_cost
        for _ in range(1000)
    ]
    return px.histogram(res, title="Monte Carlo Results")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
