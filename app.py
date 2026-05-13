import os
from dash import Dash
import dash_bootstrap_components as dbc

from callbacks import register_callbacks
from layout import build_layout

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Biopharma Licensing Monte Carlo NPV Dashboard",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server

app.layout = build_layout()
register_callbacks(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)