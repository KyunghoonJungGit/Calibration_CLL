import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from datetime import datetime
import os
import glob
import json
from pathlib import Path
import importlib
import sys

# 실험 타입별 모듈 임포트
from tof_dashboard import create_tof_layout, register_tof_callbacks

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# 전역 변수
EXPERIMENT_BASE_PATH = './dashboard_data'
experiment_modules = {
    'tof': ('tof_dashboard', 'Time of Flight'),
    # 추후 다른 실험 모듈 추가
}

# ------------------------------------------------------------------
# 1) 실험 폴더 탐색 ― timestamp 를 **epoch seconds(float)** 로 보관
# ------------------------------------------------------------------
def find_experiments(base_path):
    """실험 폴더들을 찾아서 분류"""
    experiments = {}
    base_path = os.path.normpath(base_path)

    if not os.path.exists(base_path):
        print(f"Warning: Base path not found at {base_path}")
        return experiments

    date_pattern = os.path.join(base_path, '*_*_*')
    date_folders = glob.glob(date_pattern)

    print(f"Looking for experiments in: {base_path}")
    print(f"Found date folders: {date_folders}")

    for date_folder in date_folders:
        if not os.path.isdir(date_folder):
            continue

        exp_pattern = os.path.join(date_folder, '*')
        exp_folders = glob.glob(exp_pattern)

        for exp_folder in exp_folders:
            if not os.path.isdir(exp_folder):
                continue

            folder_name = os.path.basename(exp_folder)

            h5_files   = glob.glob(os.path.join(exp_folder, '*.h5'))
            json_files = glob.glob(os.path.join(exp_folder, '*.json'))

            has_ds_raw = any('ds_raw.h5' in os.path.basename(f) for f in h5_files)
            has_ds_fit = any('ds_fit.h5' in os.path.basename(f) for f in h5_files)

            if has_ds_raw and has_ds_fit and len(json_files) >= 2:
                for exp_keyword, (module_name, exp_title) in experiment_modules.items():
                    if folder_name.startswith(exp_keyword):
                        experiments.setdefault(exp_keyword, []).append({
                            'path'       : exp_folder,
                            'name'       : folder_name,
                            'date_folder': os.path.basename(date_folder),
                            # ▶ epoch seconds 로 저장 (JSON 직렬화 가능)
                            'timestamp'  : os.path.getmtime(exp_folder)
                        })
                        print(f"Found {exp_keyword} experiment: {exp_folder}")
                        break

    for exp_type in experiments:
        experiments[exp_type].sort(key=lambda x: x['timestamp'], reverse=True)

    return experiments

# ------------------------------------------------------------------
# 레이아웃 정의
# ------------------------------------------------------------------
app.layout = dbc.Container(
    [
        dcc.Store(id='current-experiments', data={}),
        dcc.Store(id='selected-experiment', data=None),
        dcc.Interval(id='folder-check-interval', interval=5000, n_intervals=0),
        dbc.Row([dbc.Col([html.H1("Qubit Calibration Dashboard", className="text-center mb-4")])]),
        dbc.Row([dbc.Col([html.Div(id='alert-container')])], className="mb-3"),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        html.H5("실험 선택"),
                                                        dcc.Dropdown(
                                                            id='experiment-type-dropdown',
                                                            options=[],
                                                            placeholder="실험 타입을 선택하세요",
                                                            className="mb-2",
                                                        ),
                                                        dcc.Dropdown(
                                                            id='experiment-folder-dropdown',
                                                            options=[],
                                                            placeholder="실험 폴더를 선택하세요",
                                                            disabled=True,
                                                        ),
                                                    ],
                                                    md=8,
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Button(
                                                            "Refresh",
                                                            id="refresh-button",
                                                            color="primary",
                                                            className="mt-4 w-100",
                                                            size="lg",
                                                        )
                                                    ],
                                                    md=4,
                                                ),
                                            ]
                                        )
                                    ]
                                )
                            ]
                        )
                    ]
                )
            ],
            className="mb-4",
        ),
        dbc.Row([dbc.Col([html.Div(id='experiment-content')])]),
    ],
    fluid=True,
)

# ------------------------------------------------------------------
# 2) 콜백들
# ------------------------------------------------------------------

# 폴더 감시
@app.callback(
    [Output('alert-container', 'children'), Output('current-experiments', 'data')],
    [Input('folder-check-interval', 'n_intervals')],
    [State('current-experiments', 'data')],
)
def check_new_experiments(n_intervals, current_experiments):
    experiments = find_experiments(EXPERIMENT_BASE_PATH)
    alert = None
    if current_experiments:
        for exp_type, exp_list in experiments.items():
            if exp_type in current_experiments:
                current_names = {exp['name'] for exp in current_experiments[exp_type]}
                new_names = {exp['name'] for exp in exp_list}
                new_exps = new_names - current_names
                if new_exps:
                    alert = dbc.Alert(
                        f"새로운 {experiment_modules[exp_type][1]} 실험이 발견되었습니다: {', '.join(new_exps)}",
                        color="info",
                        dismissable=True,
                        duration=10000,
                    )
    return alert, experiments


# Refresh 버튼
@app.callback(
    [Output('experiment-type-dropdown', 'options'), Output('experiment-type-dropdown', 'value')],
    [Input('refresh-button', 'n_clicks'), Input('current-experiments', 'modified_timestamp')],
    [State('current-experiments', 'data'), State('experiment-type-dropdown', 'value')],
)
def update_experiment_types(n_clicks, ts, experiments, current_value):
    if not experiments:
        return [], None
    options = [
        {'label': f"{exp_title} ({len(experiments[exp_type])}개)", 'value': exp_type}
        for exp_type, (module, exp_title) in experiment_modules.items()
        if exp_type in experiments and experiments[exp_type]
    ]
    if current_value and any(opt['value'] == current_value for opt in options):
        return options, current_value
    return options, None


# ------------------------------------------------------------------
#  (★) 폴더 목록 업데이트 ― timestamp 파싱 후 strftime
# ------------------------------------------------------------------
@app.callback(
    [
        Output('experiment-folder-dropdown', 'options'),
        Output('experiment-folder-dropdown', 'disabled'),
        Output('experiment-folder-dropdown', 'value'),
    ],
    [Input('experiment-type-dropdown', 'value')],
    [State('current-experiments', 'data')],
)
def update_folder_list(exp_type, experiments):
    if not exp_type or not experiments or exp_type not in experiments:
        return [], True, None

    options = []
    for exp in experiments[exp_type]:
        ts = exp['timestamp']

        # 숫자(epoch) → datetime
        if isinstance(ts, (int, float)):
            ts_dt = datetime.fromtimestamp(ts)

        # 문자열(ISO 등) → datetime
        elif isinstance(ts, str):
            try:
                ts_dt = datetime.fromisoformat(ts)
            except ValueError:
                ts_dt = datetime.fromtimestamp(float(ts))
        else:
            ts_dt = ts  # 안전장치

        options.append(
            {
                'label': f"{exp['name']} ({exp['date_folder']} - {ts_dt.strftime('%H:%M')})",
                'value': exp['path'],
            }
        )
    return options, False, None


# 실험 레이아웃
@app.callback(
    Output('experiment-content', 'children'),
    [Input('experiment-folder-dropdown', 'value'), Input('experiment-type-dropdown', 'value')],
)
def display_experiment(folder_path, exp_type):
    if not folder_path or not exp_type:
        return html.Div("실험을 선택하세요.", className="text-center text-muted mt-5")
    if exp_type == 'tof':
        return create_tof_layout(folder_path)
    return html.Div(
        f"'{exp_type}' 실험 타입은 아직 구현되지 않았습니다.",
        className="text-center text-warning mt-5",
    )


# TOF용 콜백 등록
register_tof_callbacks(app)

# ------------------------------------------------------------------
# 앱 실행
# ------------------------------------------------------------------
if __name__ == '__main__':
    print("Initial experiments:", find_experiments(EXPERIMENT_BASE_PATH))
    app.run(debug=True, port=8099)
