import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
from datetime import datetime
import os, re, glob
from pathlib import Path

# 개별 실험 모듈 ----------------------------------------------------------
from tof_dashboard        import create_tof_layout,   register_tof_callbacks
from resonator_dashboard  import create_res_layout,   register_res_callbacks
from qspec_dashboard      import create_qspec_layout, register_qspec_callbacks   # ★ NEW

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# ----------------------------------------------------------------------
# 전역 설정
# ----------------------------------------------------------------------
EXPERIMENT_BASE_PATH = "./dashboard_data"

# exp_type → dict(layout_func, register_func, title, 패턴목록)
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
    "qspec": dict(                                                     # ★ NEW
        layout_func=create_qspec_layout,
        register_func=register_qspec_callbacks,
        title="Qubit Spectroscopy",
        patterns=["qspec", "qubit_spec", "qubit_spectroscopy"],
    ),
}

# ----------------------------------------------------------------------
# 1. 실험 폴더 검색
# ----------------------------------------------------------------------
def find_experiments(base_path: str):
    """
    날짜폴더: YYYY_MM_DD 또는 YYYY-MM-DD
    실험폴더: '#번호_…<keyword>…_<HHMMSS>'
    """
    exps: dict[str, list] = {}
    base_path = os.path.normpath(base_path)
    if not os.path.exists(base_path):
        return exps

    date_re = re.compile(r"^\d{4}[-_]\d{2}[-_]\d{2}$")
    date_dirs = [d for d in os.listdir(base_path) if date_re.match(d) and os.path.isdir(Path(base_path, d))]
    for dname in date_dirs:
        y, m, d = map(int, re.split(r"[-_]", dname))
        day_dir = Path(base_path, dname)
        for exp_dir in day_dir.iterdir():
            if not exp_dir.is_dir():
                continue
            fname = exp_dir.name.lower()
            # 필수 파일 검사
            if not (exp_dir.joinpath("ds_raw.h5").exists() and exp_dir.joinpath("ds_fit.h5").exists() and len(list(exp_dir.glob("*.json"))) >= 2):
                continue
            # 실험 타입 판정
            typ = None
            for t, info in experiment_modules.items():
                if any(p in fname for p in info["patterns"]):
                    typ = t
                    break
            if typ is None:
                continue
            # 시간 파싱
            m_t = re.search(r"(\d{6})$", fname)
            hh, mm, ss = (int(m_t.group(1)[:2]), int(m_t.group(1)[2:4]), int(m_t.group(1)[4:])) if m_t else (0, 0, 0)
            ts = datetime(y, m, d, hh, mm, ss).timestamp()
            exps.setdefault(typ, []).append(dict(path=str(exp_dir), name=exp_dir.name, date_folder=dname, timestamp=ts))

    for typ in exps:
        exps[typ].sort(key=lambda e: e["timestamp"], reverse=True)
    return exps

# ----------------------------------------------------------------------
# 2. 레이아웃
# ----------------------------------------------------------------------
app.layout = dbc.Container(
    [
        dcc.Store(id="current-experiments", data={}),
        dcc.Interval(id="folder-check-interval", interval=5000, n_intervals=0),
        dbc.Row(dbc.Col(html.H1("Qubit Calibration Dashboard", className="text-center mb-4"))),
        dbc.Row(dbc.Col(html.Div(id="alert-container")), className="mb-3"),

        dbc.Card(
            dbc.CardBody(
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H5("실험 선택"),
                                dcc.Dropdown(id="experiment-type-dropdown", placeholder="실험 타입 선택", className="mb-2"),
                                dcc.Dropdown(id="experiment-folder-dropdown", placeholder="실험 폴더 선택", disabled=True),
                            ],
                            md=8,
                        ),
                        dbc.Col(dbc.Button("Refresh", id="refresh-button", color="primary", className="mt-4 w-100", size="lg"), md=4),
                    ]
                )
            ),
            className="mb-4",
        ),

        dbc.Row(dbc.Col(html.Div(id="experiment-content"))),
    ],
    fluid=True,
)

# ----------------------------------------------------------------------
# 3. 콜백
# ----------------------------------------------------------------------
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
                    f"새로운 {experiment_modules[typ]['title']} 실험 발견: {', '.join(sorted(added))}",
                    color="info",
                    dismissable=True,
                    duration=10000,
                )
                break
    return alert, new


@app.callback(
    [Output("experiment-type-dropdown", "options"), Output("experiment-type-dropdown", "value")],
    [Input("refresh-button", "n_clicks"), Input("current-experiments", "modified_timestamp")],
    [State("current-experiments", "data"), State("experiment-type-dropdown", "value")],
)
def update_type_options(_, __, data, cur):
    if not data:
        return [], None
    opts = [{"label": f"{info['title']} ({len(data.get(t, []))}개)", "value": t} for t, info in experiment_modules.items() if data.get(t)]
    return opts, cur if any(o["value"] == cur for o in opts) else None


@app.callback(
    [Output("experiment-folder-dropdown", "options"), Output("experiment-folder-dropdown", "disabled"), Output("experiment-folder-dropdown", "value")],
    Input("experiment-type-dropdown", "value"),
    State("current-experiments", "data"),
)
def update_folder_options(typ, data):
    if not typ or not data or typ not in data:
        return [], True, None
    opts = [
        dict(label=f"{e['name']} ({e['date_folder']} ‑ {datetime.fromtimestamp(e['timestamp']).strftime('%H:%M:%S')})", value=e["path"])
        for e in data[typ]
    ]
    return opts, False, None


@app.callback(
    Output("experiment-content", "children"),
    [Input("experiment-folder-dropdown", "value"), Input("experiment-type-dropdown", "value")],
)
def display_experiment(path, typ):
    if not path or not typ:
        return html.Div("실험을 선택하세요.", className="text-center text-muted mt-5")
    return experiment_modules[typ]["layout_func"](path)

# 각 모듈 콜백 등록 -------------------------------------------------------
register_tof_callbacks(app)
register_res_callbacks(app)
register_qspec_callbacks(app)    # ★ NEW

# ----------------------------------------------------------------------
# 4. 실행
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("[main] first scan:", find_experiments(EXPERIMENT_BASE_PATH))
    app.run(debug=True, port=8099)
