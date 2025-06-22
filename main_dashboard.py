import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
from datetime import datetime
import plotly.graph_objs as go
import os, re, glob, json
from pathlib import Path

# 실험 타입별 모듈
from tof_dashboard import create_tof_layout, register_tof_callbacks

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# ------------------------------------------------------------------
# 전역 설정
# ------------------------------------------------------------------
EXPERIMENT_BASE_PATH = "./dashboard_data"

#  experiment_modules  :  exp_type  →  (module_name, title,  식별용 패턴 list)
experiment_modules = {
    "tof": ("tof_dashboard", "Time of Flight", ["tof", "time_of_flight"]),
    # 향후 다른 실험 타입을 여기에 추가
}

# ------------------------------------------------------------------
# 1. 실험 폴더 스캔
# ------------------------------------------------------------------
def find_experiments(base_path: str):
    """
    새 경로 규칙 지원:
      • 날짜 폴더:  YYYY_MM_DD  또는  YYYY-MM-DD
      • 실험 폴더: '#21_01b_time_of_flight_mw_fem_114314' 등
         └ 맨 뒤 6자리(HHMMSS)가 측정 시각
    """
    experiments: dict[str, list] = {}
    base_path = os.path.normpath(base_path)

    if not os.path.exists(base_path):
        print(f"[find_experiments] base path not found → {base_path}")
        return experiments

    # --- ① 날짜 폴더 목록 필터링 ---
    date_regex = re.compile(r"^\d{4}[-_]\d{2}[-_]\d{2}$")
    date_folders = [
        os.path.join(base_path, d)
        for d in os.listdir(base_path)
        if os.path.isdir(os.path.join(base_path, d)) and date_regex.match(d)
    ]
    print(f"[find_experiments] date folders: {date_folders}")

    # --- ② 각 날짜 폴더 내부 탐색 ---
    for date_folder in date_folders:
        date_label = os.path.basename(date_folder)          # '2025-06-19'
        y, m, d = map(int, re.split(r"[-_]", date_label))   # 날짜 정보 추출

        for exp_folder in glob.glob(os.path.join(date_folder, "*")):
            if not os.path.isdir(exp_folder):
                continue
            fname = os.path.basename(exp_folder)

            # 필수 데이터 파일 존재 여부
            has_ds_raw = os.path.exists(os.path.join(exp_folder, "ds_raw.h5"))
            has_ds_fit = os.path.exists(os.path.join(exp_folder, "ds_fit.h5"))
            has_json   = len(glob.glob(os.path.join(exp_folder, "*.json"))) >= 2
            if not (has_ds_raw and has_ds_fit and has_json):
                continue

            # --- ③ 실험 타입 판정 ---
            exp_type_detected = None
            for exp_type, (_, _, patterns) in experiment_modules.items():
                if any(p in fname.lower() for p in patterns):
                    exp_type_detected = exp_type
                    break
            if exp_type_detected is None:
                continue  # 알 수 없는 실험 타입

            # --- ④ 시간(HHMMSS) 파싱 ---
            t_match = re.search(r"(\d{6})$", fname)
            if t_match:
                hh, mm, ss = map(int, (t_match.group(1)[:2], t_match.group(1)[2:4], t_match.group(1)[4:]))
            else:  # 실패하면 00:00:00
                hh, mm, ss = 0, 0, 0
            dt = datetime(y, m, d, hh, mm, ss)
            ts_epoch = dt.timestamp()

            experiments.setdefault(exp_type_detected, []).append(
                dict(
                    path=exp_folder,
                    name=fname,
                    date_folder=date_label,
                    timestamp=ts_epoch,
                )
            )
            print(f"  ↳ found {exp_type_detected}: {exp_folder}")

    # --- ⑤ 최신순 정렬 ---
    for typ in experiments:
        experiments[typ].sort(key=lambda x: x["timestamp"], reverse=True)
    return experiments

# ------------------------------------------------------------------
# 2. 대시보드 레이아웃
# ------------------------------------------------------------------
app.layout = dbc.Container(
    [
        dcc.Store(id="current-experiments", data={}),
        dcc.Interval(id="folder-check-interval", interval=5000, n_intervals=0),
        dbc.Row(dbc.Col(html.H1("Qubit Calibration Dashboard", className="text-center mb-4"))),
        dbc.Row(dbc.Col(html.Div(id="alert-container")), className="mb-3"),

        # 컨트롤 패널 ---------------------------------------------------
        dbc.Card(
            dbc.CardBody(
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H5("실험 선택"),
                                dcc.Dropdown(
                                    id="experiment-type-dropdown",
                                    placeholder="실험 타입 선택",
                                    className="mb-2",
                                ),
                                dcc.Dropdown(
                                    id="experiment-folder-dropdown",
                                    placeholder="실험 폴더 선택",
                                    disabled=True,
                                ),
                            ],
                            md=8,
                        ),
                        dbc.Col(
                            dbc.Button("Refresh", id="refresh-button", color="primary", className="mt-4 w-100", size="lg"),
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

# ------------------------------------------------------------------
# 3. 콜백
# ------------------------------------------------------------------

# 3‑1) 주기적 폴더 감시
@app.callback(
    [Output("alert-container", "children"), Output("current-experiments", "data")],
    Input("folder-check-interval", "n_intervals"),
    State("current-experiments", "data"),
)
def check_new(n, current):
    exps = find_experiments(EXPERIMENT_BASE_PATH)
    alert = None
    if current:
        for typ, lst in exps.items():
            old = {e["name"] for e in current.get(typ, [])}
            new = {e["name"] for e in lst} - old
            if new:
                alert = dbc.Alert(
                    f"새로운 {experiment_modules[typ][1]} 실험 발견: {', '.join(sorted(new))}",
                    color="info",
                    dismissable=True,
                    duration=10000,
                )
                break
    return alert, exps

# 3‑2) Refresh 버튼 & 데이터 스토어 갱신
@app.callback(
    [Output("experiment-type-dropdown", "options"), Output("experiment-type-dropdown", "value")],
    [Input("refresh-button", "n_clicks"), Input("current-experiments", "modified_timestamp")],
    [State("current-experiments", "data"), State("experiment-type-dropdown", "value")],
)
def refresh_types(n_clicks, ts, data, cur_val):
    if not data:
        return [], None
    opts = [
        dict(label=f"{title} ({len(data[typ])}개)", value=typ)
        for typ, (_, title, _) in experiment_modules.items()
        if typ in data
    ]
    if cur_val and any(o["value"] == cur_val for o in opts):
        return opts, cur_val
    return opts, None

# 3‑3) 실험 타입 선택 → 폴더 드롭다운 채우기
@app.callback(
    [Output("experiment-folder-dropdown", "options"),
     Output("experiment-folder-dropdown", "disabled"),
     Output("experiment-folder-dropdown", "value")],
    Input("experiment-type-dropdown", "value"),
    State("current-experiments", "data"),
)
def update_folder_list(exp_type, data):
    if not exp_type or not data or exp_type not in data:
        return [], True, None
    opts = []
    for exp in data[exp_type]:
        dt = datetime.fromtimestamp(exp["timestamp"])
        opts.append(
            dict(
                label=f"{exp['name']} ({exp['date_folder']} ‑ {dt.strftime('%H:%M:%S')})",
                value=exp["path"],
            )
        )
    return opts, False, None

# 3‑4) 폴더 선택 → 실험 레이아웃
@app.callback(
    Output("experiment-content", "children"),
    [Input("experiment-folder-dropdown", "value"), Input("experiment-type-dropdown", "value")],
)
def display_exp(path, typ):
    if not path or not typ:
        return html.Div("실험을 선택하세요.", className="text-center text-muted mt-5")
    if typ == "tof":
        return create_tof_layout(path)
    return html.Div(f"{typ} 타입은 아직 미구현입니다.", className="text-center text-warning mt-5")

# TOF 플롯용 콜백 등록
register_tof_callbacks(app)

# ------------------------------------------------------------------
# 4. 실행
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("[main] initial scan:", find_experiments(EXPERIMENT_BASE_PATH))
    app.run(debug=True, port=8099)
