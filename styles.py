"""Shared styling for the Dash valuation dashboard."""

COLORS = {
    "bg": "#f6f7f9",
    "panel": "#ffffff",
    "panel_alt": "#f9fafb",
    "border": "#d8dee6",
    "text": "#172033",
    "muted": "#667085",
    "header": "#eef1f5",
    "section": "#e7ebf0",
    "accent": "#1f6feb",
    "green": "#16833a",
    "red": "#b42318",
    "amber": "#b7791f",
}

PAGE = {
    "backgroundColor": COLORS["bg"],
    "minHeight": "100vh",
    "fontFamily": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "color": COLORS["text"],
}

SIDEBAR = {
    "width": "250px",
    "minWidth": "250px",
    "backgroundColor": COLORS["panel"],
    "borderRight": f"1px solid {COLORS['border']}",
    "padding": "22px 16px",
    "minHeight": "100vh",
    "position": "sticky",
    "top": "0",
}

CONTENT = {
    "padding": "24px 28px",
    "width": "calc(100% - 250px)",
}

CARD = {
    "backgroundColor": COLORS["panel"],
    "border": f"1px solid {COLORS['border']}",
    "borderRadius": "8px",
    "boxShadow": "0 1px 2px rgba(16, 24, 40, 0.05)",
}

SMALL_LABEL = {
    "fontSize": "0.74rem",
    "fontWeight": "700",
    "color": COLORS["muted"],
    "marginBottom": "4px",
}

TABLE_STYLE = {
    "overflowX": "auto",
    "border": f"1px solid {COLORS['border']}",
    "borderRadius": "8px",
}

TABLE_CELL = {
    "fontFamily": "Menlo, Consolas, 'SFMono-Regular', monospace",
    "fontSize": "12px",
    "padding": "6px 8px",
    "border": f"1px solid {COLORS['border']}",
    "whiteSpace": "nowrap",
    "textAlign": "right",
    "minWidth": "86px",
}

TABLE_HEADER = {
    "backgroundColor": COLORS["header"],
    "color": COLORS["text"],
    "fontWeight": "700",
    "textAlign": "center",
    "border": f"1px solid {COLORS['border']}",
    "fontSize": "12px",
}
