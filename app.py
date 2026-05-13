"""
NPV Model — Entry point.
"""

import os
from dash import Dash
import dash_bootstrap_components as dbc

from config import COLORS
from ui import build_app_layout
from callbacks import register_callbacks

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY, dbc.icons.BOOTSTRAP],
    title="NPV Model",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server

app.layout = build_app_layout()

register_callbacks(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
