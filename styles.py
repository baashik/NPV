"""Shared styling tokens."""

COLORS = {
    "bg": "#f6f7f9",
    "panel": "#ffffff",
    "border": "#d8dee6",
    "text": "#172033",
    "muted": "#667085",
    "header": "#eef1f5",
    "blue": "#1f6feb",
    "accent": "#1f6feb",
    "green": "#16833a",
    "red": "#b42318",
    "amber": "#b7791f",
    "teal": "#00838F",
}

CARD = {
    "backgroundColor": COLORS["panel"],
    "border": f"1px solid {COLORS['border']}",
    "borderRadius": "8px",
    "boxShadow": "0 1px 2px rgba(16, 24, 40, 0.05)",
}

PAGE = {
    "backgroundColor": COLORS["bg"],
    "minHeight": "100vh",
    "fontFamily": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "color": COLORS["text"],
}

SIDEBAR = {
    "width": "220px",
    "minWidth": "220px",
    "backgroundColor": COLORS["panel"],
    "borderRight": f"1px solid {COLORS['border']}",
    "padding": "20px 14px",
    "minHeight": "100vh",
    "position": "sticky",
    "top": "0",
}

CONTENT = {
    "padding": "20px 24px",
    "width": "calc(100% - 220px)",
}

SMALL_LABEL = {
    "fontSize": "0.72rem",
    "fontWeight": "700",
    "color": COLORS["muted"],
    "marginBottom": "4px",
}

TABLE_CELL = {
    "fontFamily": "monospace",
    "fontSize": "0.8rem",
    "padding": "3px 6px",
    "textAlign": "right",
    "border": "1px solid #e9ecef",
}

TABLE_HEADER = {
    "backgroundColor": "#1f6feb",
    "color": "white",
    "fontWeight": "700",
    "fontSize": "0.78rem",
    "padding": "4px 6px",
    "textAlign": "right",
}

TABLE_STYLE = {
    "overflowX": "auto",
    "border": f"1px solid {COLORS['border']}",
}
