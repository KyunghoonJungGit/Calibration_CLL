# theme.py  –  registers a project‑wide Plotly template
import plotly.io as pio
from plotly import graph_objects as go

dashboard_dark = go.layout.Template(
    layout=dict(
        paper_bgcolor="#2A2A2C",      # Card color (outer frame)
        plot_bgcolor="#E6E6E6",       # Light‑gray interior (requirement)
        font=dict(color="#E0E0E0", size=14, family="Segoe UI, Arial"),
        legend=dict(bgcolor="#2A2A2C"),
        xaxis=dict(gridcolor="#555555"),
        yaxis=dict(gridcolor="#555555"),
    )
)

pio.templates["dashboard_dark"] = dashboard_dark
pio.templates.default = "dashboard_dark"   # Make it the default
