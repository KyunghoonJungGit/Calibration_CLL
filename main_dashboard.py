# ======================================================================
#  main_dashboard.py   (FULL / REPLACEMENT  – RB module included)
# ======================================================================
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
from datetime import datetime
import os, re
from pathlib import Path

# ────────────────────────────────────────────────────────────────────
# Import Dash modules for each experiment
# ────────────────────────────────────────────────────────────────────
from tof_dashboard        import create_tof_layout,   register_tof_callbacks
from resonator_dashboard  import create_res_layout,   register_res_callbacks
from qspec_dashboard      import create_qspec_layout, register_qspec_callbacks
from power_rabi_dashboard import create_prabi_layout, register_prabi_callbacks
from t1_dashboard         import create_t1_layout,    register_t1_callbacks
from echo_dashboard       import create_echo_layout,  register_echo_callbacks
from ramsey_dashboard     import create_ramsey_layout, register_ramsey_callbacks
from iq_dashboard         import create_iq_layout,    register_iq_callbacks
from readout_power_opt_dashboard import create_rpo_layout, register_rpo_callbacks
from drag_dashboard       import create_drag_layout,   register_drag_callbacks
from rb1q_dashboard       import create_rb_layout,     register_rb_callbacks     # ★ NEW ★

# ────────────────────────────────────────────────────────────────────
# App instance & global settings
# ────────────────────────────────────────────────────────────────────
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
EXPERIMENT_BASE_PATH = "./dashboard_data"

# Experiment type metadata ------------------------------------------------
experiment_modules = {
    "tof": dict(
        layout_func=create_tof_layout,
        register_func=register_tof_callbacks,
        title="Time of Flight",
        patterns=["tof", "time_of_flight"],
    ),
    "res": dict(
        layout_func=create_res_layout,
        register_func=register_res_callbacks,
        title="Resonator Spectroscopy",
        patterns=["res_spec", "resonator", "resonator_spectroscopy"],
    ),
    "qspec": dict(
        layout_func=create_qspec_layout,
        register_func=register_qspec_callbacks,
        title="Qubit Spectroscopy",
        patterns=["qspec", "qubit_spec", "qubit_spectroscopy"],
    ),
    "prabi": dict(
        layout_func=create_prabi_layout,
        register_func=register_prabi_callbacks,
        title="Power Rabi",
        patterns=["prabi", "power_rabi", "power‑rabi", "pwr_rabi", "rabi"],
    ),
    "t1": dict(
        layout_func=create_t1_layout,
        register_func=register_t1_callbacks,
        title="T1 Relaxation",
        patterns=["t1", "t1_relax", "relaxation"],
    ),
    "echo": dict(
        layout_func=create_echo_layout,
        register_func=register_echo_callbacks,
        title="T2 Echo",
        patterns=["echo", "t2echo", "t2_echo", "t2e"],
    ),
    "ramsey": dict(
        layout_func=create_ramsey_layout,
        register_func=register_ramsey_callbacks,
        title="Ramsey (T2*)",
        patterns=["ramsey", "t2star", "t2*", "ramsey_exp"],
    ),
    "iq": dict(
        layout_func=create_iq_layout,
        register_func=register_iq_callbacks,
        title="IQ Discrimination",
        patterns=["iq", "iq_blobs", "iq_readout"],
    ),
    "rpo": dict(
        layout_func=create_rpo_layout,
        register_func=register_rpo_callbacks,
        title="Readout Power Opt.",
        patterns=["readout_power", "power_opt", "readout_power_optimization",
                  "rpo", "readout‑power"],
    ),
    "drag": dict(
        layout_func=create_drag_layout,
        register_func=register_drag_callbacks,
        title="DRAG Calibration",
        patterns=["drag", "drag_cal", "dragcal", "drag_calibration"],
    ),
    "rb1q": dict(                              # ★ NEW ★
        layout_func=create_rb_layout,
        register_func=register_rb_callbacks,
        title="1Q Randomized Benchmark",
        patterns=["rb1q", "1q_rb", "Randomized", "Randomized_benchmarking", "benchmarking"],
    ),
}

# ────────────────────────────────────────────────────────────────────
# 1. Scan experiment folders (using experiment_modules)
# ────────────────────────────────────────────────────────────────────
def find_experiments(base_path: str):
    """
    Date folders: YYYY_MM_DD or YYYY-MM-DD
    Experiment folders: '#number_…<keyword>…_<HHMMSS>'
    """
    exps: dict[str, list] = {}
    base_path = os.path.normpath(base_path)
    if not os.path.exists(base_path):
        return exps

    date_re = re.compile(r"^\d{4}[-_]\d{2}[-_]\d{2}$")
    date_dirs = [
        d for d in os.listdir(base_path)
        if date_re.match(d) and os.path.isdir(Path(base_path, d))
    ]

    for dname in date_dirs:
        y, m, d = map(int, re.split(r"[-_]", dname))
        day_dir = Path(base_path, dname)

        for exp_dir in day_dir.iterdir():
            if not exp_dir.is_dir():
                continue
            fname = exp_dir.name.lower()

            # Check if required data files exist
            required_ok = all(
                (exp_dir / f).exists()
                for f in ("ds_raw.h5", "ds_fit.h5")
            ) and len(list(exp_dir.glob("*.json"))) >= 2
            if not required_ok:
                continue

            # Determine experiment type
            typ = None
            for t, info in experiment_modules.items():
                if any(p in fname for p in info["patterns"]):
                    typ = t
                    break
            if typ is None:
                continue

            # Timestamp
            m_t = re.search(r"(\d{6})$", fname)
            hh, mm, ss = (
                int(m_t.group(1)[:2]),
                int(m_t.group(1)[2:4]),
                int(m_t.group(1)[4:]),
            ) if m_t else (0, 0, 0)
            ts = datetime(y, m, d, hh, mm, ss).timestamp()

            exps.setdefault(typ, []).append(
                dict(
                    path=str(exp_dir),
                    name=exp_dir.name,
                    date_folder=dname,
                    timestamp=ts,
                )
            )

    for typ in exps:
        exps[typ].sort(key=lambda e: e["timestamp"], reverse=True)
    return exps


# ────────────────────────────────────────────────────────────────────
# 2. Layout
# ────────────────────────────────────────────────────────────────────
app.layout = dbc.Container(
    [
        dcc.Store(id="current-experiments", data={}),
        dcc.Interval(id="folder-check-interval", interval=5000, n_intervals=0),

        dbc.Row(dbc.Col(html.H1("Qubit Calibration Dashboard",
                                className="text-center mb-4"))),
        dbc.Row(dbc.Col(html.Div(id="alert-container")), className="mb-3"),

        dbc.Card(
            dbc.CardBody(
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H5("Experiment Selection"),
                                dcc.Dropdown(
                                    id="experiment-type-dropdown",
                                    placeholder="Select experiment type",
                                    className="mb-2",
                                ),
                                dcc.Dropdown(
                                    id="experiment-folder-dropdown",
                                    placeholder="Select experiment folder",
                                    disabled=True,
                                ),
                            ],
                            md=8,
                        ),
                        dbc.Col(
                            dbc.Button(
                                "Refresh",
                                id="refresh-button",
                                color="primary",
                                className="mt-4 w-100",
                                size="lg",
                            ),
                            md=4,
                        ),
                    ]
                )
            ),
            className="mb-4",
        ),

        dbc.Row(dbc.Col(html.Div(id="experiment-content"))),
    ],
    fluid=True,
)

# ────────────────────────────────────────────────────────────────────
# 3. Callbacks
# ────────────────────────────────────────────────────────────────────
@app.callback(
    [Output("alert-container", "children"), Output("current-experiments", "data")],
    Input("folder-check-interval", "n_intervals"),
    State("current-experiments", "data"),
)
def poll_folder(_, cur):
    new = find_experiments(EXPERIMENT_BASE_PATH)
    alert = None
    if cur:
        for typ, lst in new.items():
            added = {e["name"] for e in lst} - {e["name"] for e in cur.get(typ, [])}
            if added:
                alert = dbc.Alert(
                    f"New {experiment_modules[typ]['title']} experiment found: {', '.join(sorted(added))}",
                    color="info",
                    dismissable=True,
                    duration=10000,
                )
                break
    return alert, new


@app.callback(
    [Output("experiment-type-dropdown", "options"),
     Output("experiment-type-dropdown", "value")],
    [Input("refresh-button", "n_clicks"),
     Input("current-experiments", "modified_timestamp")],
    [State("current-experiments", "data"),
     State("experiment-type-dropdown", "value")],
)
def update_type_options(_, __, data, cur):
    if not data:
        return [], None
    opts = [
        {
            "label": f"{info['title']} ({len(data.get(t, []))} items)",
            "value": t,
        }
        for t, info in experiment_modules.items()
        if data.get(t)
    ]
    return opts, cur if any(o["value"] == cur for o in opts) else None


@app.callback(
    [Output("experiment-folder-dropdown", "options"),
     Output("experiment-folder-dropdown", "disabled"),
     Output("experiment-folder-dropdown", "value")],
    Input("experiment-type-dropdown", "value"),
    State("current-experiments", "data"),
)
def update_folder_options(typ, data):
    if not typ or not data or typ not in data:
        return [], True, None
    opts = [
        dict(
            label=f"{e['name']} ({e['date_folder']} – "
                  f"{datetime.fromtimestamp(e['timestamp']).strftime('%H:%M:%S')})",
            value=e["path"],
        )
        for e in data[typ]
    ]
    return opts, False, None


@app.callback(
    Output("experiment-content", "children"),
    [Input("experiment-folder-dropdown", "value"),
     Input("experiment-type-dropdown", "value")],
)
def display_experiment(path, typ):
    if not path or not typ:
        return html.Div("Please select an experiment.", className="text-center text-muted mt-5")
    return experiment_modules[typ]["layout_func"](path)


# ────────────────────────────────────────────────────────────────────
# Register callbacks for each module
# ────────────────────────────────────────────────────────────────────
register_tof_callbacks(app)
register_res_callbacks(app)
register_qspec_callbacks(app)
register_prabi_callbacks(app)
register_t1_callbacks(app)
register_echo_callbacks(app)
register_ramsey_callbacks(app)
register_iq_callbacks(app)
register_rpo_callbacks(app)
register_drag_callbacks(app)
register_rb_callbacks(app)          


# ────────────────────────────────────────────────────────────────────
# 4. run
# ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[main] first scan:", find_experiments(EXPERIMENT_BASE_PATH))
    app.run(debug=True, port=7700)