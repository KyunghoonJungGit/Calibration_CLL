import dash
from dash import dcc, html, Input, Output, State, MATCH
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.subplots as subplots
import xarray as xr
import numpy as np
import json, os
from pathlib import Path

# --------------------------------------------------------------------
# 공용 헬퍼 : xarray open_dataset 여러 엔진 시도
# --------------------------------------------------------------------
def open_xr_dataset(path, engines=("h5netcdf", "netcdf4", None)):
    last_err = None
    for eng in engines:
        try:
            return xr.open_dataset(path, engine=eng)
        except Exception as e:
            last_err = e
    raise last_err


# --------------------------------------------------------------------
# 1. 데이터 로더
# --------------------------------------------------------------------
def load_res_data(folder):
    folder = os.path.normpath(folder)
    paths = {
        "ds_raw":  os.path.join(folder, "ds_raw.h5"),
        "ds_fit":  os.path.join(folder, "ds_fit.h5"),
        "data_js": os.path.join(folder, "data.json"),
        "node_js": os.path.join(folder, "node.json"),
    }
    if not all(os.path.exists(p) for p in paths.values()):
        print(f"[load_res_data] missing file in {folder}")
        return None

    ds_raw = open_xr_dataset(paths["ds_raw"])
    ds_fit = open_xr_dataset(paths["ds_fit"])

    with open(paths["data_js"], "r", encoding="utf-8") as f:
        data_json = json.load(f)
    with open(paths["node_js"], "r", encoding="utf-8") as f:
        node_json = json.load(f)

    qubits       = ds_raw["qubit"].values
    detuning     = ds_raw["detuning"].values                # Hz
    det_mhz      = detuning / 1e6

    I            = ds_raw["I"].values
    Q            = ds_raw["Q"].values
    IQ_abs       = ds_raw["IQ_abs"].values * 1e3            # mV
    phase        = ds_raw["phase"].values

    success      = ds_fit["success"].values
    base_line    = ds_fit["base_line"].values
    pos          = ds_fit["position"].values
    width        = ds_fit["width"].values
    amp          = ds_fit["amplitude"].values
    res_freq     = ds_fit["res_freq"].values                # Hz
    fwhm         = ds_fit["fwhm"].values                    # Hz

    return dict(
        ds_raw=ds_raw, ds_fit=ds_fit, data_json=data_json, node_json=node_json,
        qubits=qubits, n=len(qubits), det_hz=detuning, det_mhz=det_mhz,
        I=I, Q=Q, IQ_abs=IQ_abs, phase=phase,
        success=success, base_line=base_line, pos=pos, width=width,
        amp=amp, res_freq=res_freq, fwhm=fwhm,
    )

# --------------------------------------------------------------------
# 2. Plot 생성
# --------------------------------------------------------------------
def lorentzian(x, x0, gamma, A, offset):
    return offset - A * (gamma / 2) ** 2 / ((x - x0) ** 2 + (gamma / 2) ** 2)

def create_res_plots(data, view="amplitude"):
    if not data:
        return go.Figure()

    n_q = data["n"]
    n_cols = 4
    n_rows = int(np.ceil(n_q / n_cols))
    fig = subplots.make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=[str(q) for q in data["qubits"]],
        vertical_spacing=0.07, horizontal_spacing=0.04,
    )

    for idx, q in enumerate(data["qubits"]):
        r, c = idx // n_cols + 1, idx % n_cols + 1
        x = data["det_mhz"]

        if view == "amplitude":
            y = data["IQ_abs"][idx]
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="blue", width=1), name="Data" if idx == 0 else None, showlegend=idx==0), row=r, col=c)

            # fit 곡선
            if data["success"][idx] and not np.isnan(data["res_freq"][idx]):
                x_fit = np.linspace(data["det_hz"].min(), data["det_hz"].max(), 500)
                offset   = np.interp(x_fit, data["det_hz"], data["base_line"][idx])  # baseline interpolate
                y_fit = lorentzian(x_fit, data["pos"][idx], data["width"][idx], data["amp"][idx], offset) * 1e3
                fig.add_trace(go.Scatter(x=x_fit/1e6, y=y_fit, mode="lines", line=dict(color="red", dash="dash"), name="Fit" if idx==0 else None, showlegend=idx==0), row=r, col=c)

            fig.update_yaxes(title_text="|IQ|  [mV]" if c==1 else None, row=r, col=c, showgrid=True)
        else:  # phase
            y = data["phase"][idx]
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="blue", width=1), showlegend=False), row=r, col=c)
            fig.update_yaxes(title_text="Phase [rad]" if c==1 else None, row=r, col=c, showgrid=True)

        fig.update_xaxes(range=[-3, 3], title_text="Detuning [MHz]" if r==n_rows else None, row=r, col=c, showgrid=True)

    ttl = "Resonator Spectroscopy – Amplitude + Fit" if view=="amplitude" else "Resonator Spectroscopy – Phase"
    fig.update_layout(title=ttl, height=280*n_rows, template="plotly_white", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

# --------------------------------------------------------------------
# 3. Summary Table
# --------------------------------------------------------------------
def create_summary_table(data):
    rows = []
    for i, q in enumerate(data["qubits"]):
        ok = bool(data["success"][i])
        rows.append(
            html.Tr(
                [
                    html.Td(q),
                    html.Td(f"{data['res_freq'][i]/1e9: .6f}" if ok else "—"),
                    html.Td(f"{data['fwhm'][i]/1e3: .1f}"      if ok else "—"),
                    html.Td("✓" if ok else "✗"),
                ],
                className="table-success" if ok else "table-warning",
            )
        )
    header = html.Thead(html.Tr([html.Th("Qubit"), html.Th("Res Freq [GHz]"), html.Th("FWHM [kHz]"), html.Th("Fit OK")]))
    return dbc.Table([header, html.Tbody(rows)], bordered=True, striped=True, size="sm", responsive=True)

# --------------------------------------------------------------------
# 4. 레이아웃 생성
# --------------------------------------------------------------------
def create_res_layout(folder):
    uid = folder.replace("\\", "_").replace("/", "_").replace(":", "")
    data = load_res_data(folder)
    if not data:
        return html.Div([dbc.Alert("데이터 로드 실패", color="danger"), html.Pre(folder)])

    init_fig = create_res_plots(data, "amplitude")

    return html.Div(
        [
            dcc.Store(id={"type": "res-data", "index": uid}, data={"folder": folder}),
            dbc.Row(dbc.Col(html.H3(f"Resonator Spectroscopy – {Path(folder).name}")), className="mb-3"),
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            dcc.RadioItems(
                                id={"type": "res-view", "index": uid},
                                options=[{"label": " Amplitude", "value": "amplitude"}, {"label": " Phase", "value": "phase"}],
                                value="amplitude",
                                inline=True,
                            )
                        )
                    ),
                    md=12,
                ),
                className="mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Loading(
                            children=[dcc.Graph(id={"type": "res-plot", "index": uid}, figure=init_fig, config={"displayModeBar": True})],
                            type="default",
                        ),
                        md=8,
                    ),
                    dbc.Col(
                        [
                            html.H5("Summary"),
                            create_summary_table(data),
                            html.Hr(),
                            html.H6("Debug"),
                            html.Pre(f"Folder: {folder}\nQubits: {data['n']}"),
                        ],
                        md=4,
                    ),
                ]
            ),
        ]
    )

# --------------------------------------------------------------------
# 5. 콜백
# --------------------------------------------------------------------
def register_res_callbacks(app):
    @app.callback(
        Output({"type": "res-plot", "index": MATCH}, "figure"),
        Input({"type": "res-view", "index": MATCH}, "value"),
        State({"type": "res-data", "index": MATCH}, "data"),
    )
    def update_plot(view_mode, store):
        if not store:
            return go.Figure()
        data = load_res_data(store["folder"])
        return create_res_plots(data, view_mode)
