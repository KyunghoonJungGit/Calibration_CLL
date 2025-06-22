import dash
from dash import dcc, html, Input, Output, State, MATCH
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.subplots as subplots
import xarray as xr
import numpy as np
import json
import os
from pathlib import Path

# -------------------------------------------------------------------
#  NEW: 안전하게 H5 파일을 여는 유틸리티
# -------------------------------------------------------------------
def open_xr_dataset(path, engines=("h5netcdf", "netcdf4", None)):
    """
    xarray.open_dataset를 여러 엔진으로 시도.
    첫 번째로 성공한 결과를 반환하고, 모두 실패하면 마지막 예외를 다시 raise.
    """
    last_error = None
    for eng in engines:
        try:
            print(f"  trying engine={eng} ... ", end="")
            ds = xr.open_dataset(path, engine=eng)
            print("✓ success")
            return ds
        except Exception as e:
            print(f"✗ {type(e).__name__}: {e}")
            last_error = e
    raise last_error  # 전부 실패하면 호출부에서 처리하도록 예외 전파


# -------------------------------------------------------------------
# 1. 데이터 로더
# -------------------------------------------------------------------
def load_tof_data(folder_path):
    """TOF 실험 데이터 로드"""
    try:
        folder_path = os.path.normpath(folder_path)

        ds_raw_path  = os.path.join(folder_path, "ds_raw.h5")
        ds_fit_path  = os.path.join(folder_path, "ds_fit.h5")
        data_json_path = os.path.join(folder_path, "data.json")
        node_json_path = os.path.join(folder_path, "node.json")

        # 필수 파일 존재 여부
        required = [ds_raw_path, ds_fit_path, data_json_path, node_json_path]
        if not all(os.path.exists(p) for p in required):
            print(f"[load_tof_data] Missing required files in {folder_path}")
            return None

        print(f"[load_tof_data] opening datasets in {folder_path}")
        ds_raw = open_xr_dataset(ds_raw_path)
        ds_fit = open_xr_dataset(ds_fit_path)

        with open(data_json_path, "r", encoding="utf-8") as f:
            data_json = json.load(f)
        with open(node_json_path, "r", encoding="utf-8") as f:
            node_json = json.load(f)

        qubits       = ds_raw["qubit"].values
        n_qubits     = len(qubits)
        success      = ds_fit["success"].values
        delays       = ds_fit["delay"].values
        thresholds   = ds_fit["threshold"].values
        readout_time = ds_raw["readout_time"].values

        print(f"[load_tof_data] loaded OK – {n_qubits} qubits")
        return dict(
            ds_raw=ds_raw,
            ds_fit=ds_fit,
            data_json=data_json,
            node_json=node_json,
            qubits=qubits,
            n_qubits=n_qubits,
            success=success,
            delays=delays,
            thresholds=thresholds,
            readout_time=readout_time,
        )

    except Exception as e:
        print(f"[load_tof_data] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


# -------------------------------------------------------------------
# 2. 플롯 생성
# -------------------------------------------------------------------
def create_tof_plots(data, view_mode="averaged"):
    if not data:
        return go.Figure()

    qubits       = data["qubits"]
    n_qubits     = data["n_qubits"]
    readout_time = data["readout_time"]
    delays       = data["delays"]
    thresholds   = data["thresholds"]
    success      = data["success"]
    ds_raw       = data["ds_raw"]

    print(f"[create_tof_plots] qubits={n_qubits}, mode={view_mode}")

    n_cols = 2
    n_rows = int(np.ceil(n_qubits / n_cols))
    fig = subplots.make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=[f"{q}" for q in qubits],
        vertical_spacing=0.08,
        horizontal_spacing=0.1,
    )

    color_I, color_Q, color_tof = "blue", "red", "black"
    adc_range = 0.5  # mV

    for idx, qubit in enumerate(qubits):
        row, col = idx // n_cols + 1, idx % n_cols + 1

        if view_mode == "averaged":
            adcI = ds_raw["adcI"].sel(qubit=qubit).values * 1e3
            adcQ = ds_raw["adcQ"].sel(qubit=qubit).values * 1e3
        else:  # single
            adcI = ds_raw["adc_single_runI"].sel(qubit=qubit).values * 1e3
            adcQ = ds_raw["adc_single_runQ"].sel(qubit=qubit).values * 1e3

        # 회색 배경 – ADC 범위
        fig.add_trace(
            go.Scatter(
                x=[readout_time[0], readout_time[-1], readout_time[-1], readout_time[0], readout_time[0]],
                y=[-adc_range, -adc_range, adc_range, adc_range, -adc_range],
                fill="toself",
                fillcolor="lightgray",
                line=dict(width=0),
                opacity=0.3,
                hoverinfo="skip",
                showlegend=False,
            ),
            row=row,
            col=col,
        )

        # I, Q 곡선
        fig.add_trace(
            go.Scatter(
                x=readout_time,
                y=adcI,
                mode="lines",
                name="I" if idx == 0 else None,
                line=dict(color=color_I, width=1),
                legendgroup="I",
                showlegend=(idx == 0),
            ),
            row=row,
            col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=readout_time,
                y=adcQ,
                mode="lines",
                name="Q" if idx == 0 else None,
                line=dict(color=color_Q, width=1),
                legendgroup="Q",
                showlegend=(idx == 0),
            ),
            row=row,
            col=col,
        )

        # TOF 지점
        if success[idx]:
            fig.add_vline(
                x=delays[idx],
                line=dict(color=color_tof, dash="dash", width=1),
                row=row,
                col=col,
            )
            if idx == 0:
                fig.add_trace(
                    go.Scatter(
                        x=[None],
                        y=[None],
                        mode="lines",
                        name="TOF",
                        line=dict(color=color_tof, dash="dash", width=1),
                        showlegend=True,
                    ),
                    row=row,
                    col=col,
                )

        # 축 범위/레이블
        fig.update_xaxes(
            range=[0, 1000],
            title_text="Time [ns]" if row == n_rows else None,
            showgrid=True,
            gridcolor="rgba(0,0,0,0.1)",
            row=row,
            col=col,
        )
        y_range = 0.6 if view_mode == "averaged" else 3
        fig.update_yaxes(
            range=[-y_range, y_range],
            title_text="Readout amplitude [mV]" if col == 1 else None,
            showgrid=True,
            gridcolor="rgba(0,0,0,0.1)",
            row=row,
            col=col,
        )

    fig.update_layout(
        title=f"Time of Flight Calibration – {'Averaged' if view_mode=='averaged' else 'Single'} Run",
        height=300 * n_rows,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# -------------------------------------------------------------------
# 3. 요약 테이블
# -------------------------------------------------------------------
def create_summary_table(data):
    if not data:
        return html.Div("데이터 없음")

    qubits     = data["qubits"]
    delays     = data["delays"]
    thresholds = data["thresholds"]
    success    = data["success"]

    header = html.Thead(
        html.Tr([html.Th("Qubit"), html.Th("Delay (ns)"), html.Th("Threshold (mV)"), html.Th("Fit OK")])
    )
    body_rows = [
        html.Tr(
            [
                html.Td(q),
                html.Td(f"{delays[i]:.1f}"),
                html.Td(f"{thresholds[i]*1e3:.3f}"),
                html.Td("✓" if success[i] else "✗"),
            ],
            className="table-success" if success[i] else "table-warning",
        )
        for i, q in enumerate(qubits)
    ]
    return dbc.Table([header, html.Tbody(body_rows)], bordered=True, striped=True, size="sm", responsive=True)


# -------------------------------------------------------------------
# 4. 레이아웃
# -------------------------------------------------------------------
def create_tof_layout(folder_path):
    unique_id = folder_path.replace("\\", "_").replace("/", "_").replace(":", "")
    data = load_tof_data(folder_path)

    if not data:
        return html.Div(
            [
                dbc.Alert("데이터 로드 실패 ‑ 파일을 찾을 수 없거나 읽을 수 없습니다.", color="danger"),
                html.Pre(f"Folder path: {folder_path}"),
            ]
        )

    initial_fig = create_tof_plots(data, "averaged")

    return html.Div(
        [
            dcc.Store(id={"type": "tof-data", "index": unique_id}, data={"folder_path": folder_path}),
            dbc.Row(dbc.Col(html.H3(f"TOF Calibration – {os.path.basename(folder_path)}")), className="mb-3"),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.Label("View Mode:"),
                                                dcc.RadioItems(
                                                    id={"type": "tof-view-mode", "index": unique_id},
                                                    options=[
                                                        {"label": " Averaged Run", "value": "averaged"},
                                                        {"label": " Single Run", "value": "single"},
                                                    ],
                                                    value="averaged",
                                                    inline=True,
                                                    className="ms-2",
                                                ),
                                            ],
                                            md=6,
                                        ),
                                        dbc.Col(html.Div(f"Total Qubits: {data['n_qubits']}", className="text-end mt-2"), md=6),
                                    ]
                                )
                            )
                        ),
                        md=12,
                    )
                ],
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Loading(
                            id="loading-tof-plot",
                            type="default",
                            children=[
                                dcc.Graph(
                                    id={"type": "tof-plot", "index": unique_id},
                                    figure=initial_fig,
                                    config={"displayModeBar": True},
                                )
                            ],
                        ),
                        md=8,
                    ),
                    dbc.Col(
                        [
                            html.H5("Summary Statistics"),
                            create_summary_table(data),
                            html.Hr(),
                            html.H6("Debug Info"),
                            html.Pre(
                                f"Folder: {folder_path}\nQubits: {len(data['qubits'])}\n"
                                f"Success: {sum(data['success'])}/{len(data['success'])}"
                            ),
                        ],
                        md=4,
                    ),
                ]
            ),
        ]
    )


# -------------------------------------------------------------------
# 5. 콜백 등록
# -------------------------------------------------------------------
def register_tof_callbacks(app):
    @app.callback(
        Output({"type": "tof-plot", "index": MATCH}, "figure"),
        Input({"type": "tof-view-mode", "index": MATCH}, "value"),
        State({"type": "tof-data", "index": MATCH}, "data"),
    )
    def update_tof_plot(view_mode, tof_data):
        if not tof_data:
            return go.Figure()
        data = load_tof_data(tof_data["folder_path"])
        return create_tof_plots(data, view_mode)
