# ======================================================================
#  drag_dashboard.py   (FULL / NEW FILE)
# ======================================================================
"""
Dash module for **DRAG‑coefficient calibration** experiments
============================================================
* 2‑D sweep  : (#‑pulses , α‑prefactor)            → I‑quadrature  [mV]
* 1‑D view   : α‑prefactor                         → ⟨I⟩           [mV]
* Summary    : per‑qubit optimal α  +  fit‑success
* ≥10 qubits 지원, 2 열 × N 행 스크롤 레이아웃
--------------------------------------------------------------------
Author : (작성자 이름)
Date   : 2025‑06‑22
"""
from __future__ import annotations
import dash
from dash import dcc, html, Input, Output, State, MATCH
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.subplots as subplots
import xarray as xr
import numpy as np
import json, os
from pathlib import Path


# ────────────────────────────────────────────────────────────────────
# 안전한 xarray open_dataset
# ────────────────────────────────────────────────────────────────────
def open_xr_dataset(path, engines=("h5netcdf", "netcdf4", None)):
    last_err = None
    for eng in engines:
        try:
            return xr.open_dataset(path, engine=eng)
        except Exception as e:
            last_err = e
    raise last_err


# ────────────────────────────────────────────────────────────────────
# 1. 데이터 로딩
# ────────────────────────────────────────────────────────────────────
def load_drag_data(folder: str | Path) -> dict | None:
    """
    반환 dict
      qubits, n,
      alpha, nb_pulses,
      I_heat_mV (q, P, A)   – raw I [mV]
      I_avg_mV  (q, A)      – pulse‑averaged I [mV]
      opt_alpha, success,
      ds_raw, ds_fit, data_json, node_json
    """
    folder = os.path.normpath(str(folder))
    paths = {
        "ds_raw":  os.path.join(folder, "ds_raw.h5"),
        "ds_fit":  os.path.join(folder, "ds_fit.h5"),
        "data_js": os.path.join(folder, "data.json"),
        "node_js": os.path.join(folder, "node.json"),
    }
    if not all(os.path.exists(p) for p in paths.values()):
        print(f"[load_drag_data] missing files in {folder}")
        return None

    ds_raw = open_xr_dataset(paths["ds_raw"])
    ds_fit = open_xr_dataset(paths["ds_fit"])

    with open(paths["data_js"], "r", encoding="utf-8") as f:
        data_json = json.load(f)
    with open(paths["node_js"], "r", encoding="utf-8") as f:
        node_json = json.load(f)

    qubits = ds_raw["qubit"].values          # (q,)
    n_q    = len(qubits)

    # ── 축 / 좌표 ────────────────────────────────────────────────
    # α‑prefactor
    if "alpha" in ds_raw.coords:
        alpha = ds_raw["alpha"].values                     # (A,) 또는 (q,A)
    elif "alpha_prefactor" in ds_raw.coords:
        alpha = ds_raw["alpha_prefactor"].values
    else:
        raise KeyError("alpha or alpha_prefactor coordinate not found in ds_raw")

    # nb_of_pulses
    nb_pulses = ds_raw["nb_of_pulses"].values              # (P,)

    # ── I 데이터 (heat‑map) ─────────────────────────────────────
    if "I" not in ds_raw.data_vars:
        raise KeyError("'I' data variable missing in ds_raw")
    I_raw = ds_raw["I"].values * 1e3                       # → mV

    if I_raw.ndim == 3:                                    # (q, P, A)
        I_heat_mV = I_raw
    else:
        # (P,A) (single qubit) → add qubit dim
        I_heat_mV = I_raw[np.newaxis, ...]

    # ── pulse‑averaged (1‑D) 데이터 ─────────────────────────────
    if "averaged_data" in ds_raw:
        I_avg_mV = ds_raw["averaged_data"].values * 1e3    # (q, A)
    else:
        I_avg_mV = I_heat_mV.mean(axis=1)                  # 평균 over P

    # ── fit 결과 (JSON) ────────────────────────────────────────
    fit_results = data_json.get("fit_results", {})
    opt_alpha = np.full(n_q, np.nan, dtype=float)
    success   = np.full(n_q, False,  dtype=bool)
    for i, q in enumerate(qubits):
        qk = str(q)
        if qk in fit_results:
            opt_alpha[i] = fit_results[qk].get("alpha", np.nan)
            success[i]   = bool(fit_results[qk].get("success", False))

    return dict(
        qubits=qubits, n=n_q,
        alpha=alpha, nb_pulses=nb_pulses,
        I_heat_mV=I_heat_mV, I_avg_mV=I_avg_mV,
        opt_alpha=opt_alpha, success=success,
        ds_raw=ds_raw, ds_fit=ds_fit,
        data_json=data_json, node_json=node_json,
    )


# ────────────────────────────────────────────────────────────────────
# 2‑A. Summary Figure  (bar + success)
# ────────────────────────────────────────────────────────────────────
def create_summary_figure(d: dict) -> go.Figure:
    qbs = d["qubits"]; n_q = d["n"]
    fig = subplots.make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.02,
    )

    # row‑1 : optimal α
    colors = ["seagreen" if ok else "firebrick" for ok in d["success"]]
    fig.add_trace(
        go.Bar(x=qbs, y=d["opt_alpha"], marker_color=colors,
               name="optimal α"),
        row=1, col=1,
    )
    fig.add_hline(y=0, line=dict(color="black", dash="dash"), row=1, col=1)

    # row‑2 : success (0/1)
    fig.add_trace(
        go.Bar(x=qbs, y=d["success"].astype(int),
               marker_color=colors, name="fit OK"),
        row=2, col=1,
    )
    fig.update_yaxes(range=[-0.1, 1.1], row=2, col=1)

    fig.update_layout(
        title="DRAG Calibration Results by Qubit",
        height=400,
        template="plotly_white",
        showlegend=False,
    )
    return fig


# ────────────────────────────────────────────────────────────────────
# 2‑B. 상세 Plot  (mode = 'avg' | 'heat')
# ────────────────────────────────────────────────────────────────────
def create_drag_plot(d: dict, mode: str = "avg") -> go.Figure:
    qbs      = d["qubits"]; n_q = d["n"]
    alpha    = d["alpha"]
    nb_puls  = d["nb_pulses"]
    I_avg    = d["I_avg_mV"]
    I_heat   = d["I_heat_mV"]
    optα     = d["opt_alpha"]
    success  = d["success"]

    n_cols = 2
    n_rows = int(np.ceil(n_q / n_cols))

    fig = subplots.make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=[str(q) for q in qbs],
        vertical_spacing=0.08, horizontal_spacing=0.07,
    )

    show_cbar = True
    for i, q in enumerate(qbs):
        r, c = divmod(i, n_cols)
        row, col = r + 1, c + 1

        if mode == "avg":
            x = alpha if alpha.ndim == 1 else alpha[i]
            y = I_avg[i]
            fig.add_trace(
                go.Scatter(
                    x=x, y=y, mode="lines",
                    line=dict(color="blue", width=1),
                    name="Data" if i == 0 else None,
                    showlegend=(i == 0),
                ),
                row=row, col=col,
            )
            # optimal α
            if success[i] and not np.isnan(optα[i]):
                fig.add_vline(
                    x=optα[i], line=dict(color="red", dash="dash", width=1),
                    row=row, col=col,
                )
                if i == 0:
                    fig.add_trace(
                        go.Scatter(x=[None], y=[None], mode="lines",
                                   line=dict(color="red", dash="dash"),
                                   name="optimal α"),
                        row=row, col=col,
                    )
        else:  # heat‑map
            x = alpha if alpha.ndim == 1 else alpha[i]
            z = I_heat[i]                         # (P, A)
            fig.add_trace(
                go.Heatmap(
                    x=x, y=nb_puls, z=z,
                    coloraxis="coloraxis",
                    showscale=show_cbar,
                ),
                row=row, col=col,
            )
            show_cbar = False
            # optimal α
            if success[i] and not np.isnan(optα[i]):
                fig.add_vline(
                    x=optα[i], line=dict(color="white", dash="dash", width=1),
                    row=row, col=col,
                )

            fig.update_yaxes(title_text="# pulses" if col == 1 else None,
                             autorange="reversed", row=row, col=col)

        # 공통 labels
        if row == n_rows:
            fig.update_xaxes(title_text="DRAG coefficient α", row=row, col=col)
        if col == 1 and mode == "avg":
            fig.update_yaxes(title_text="⟨I⟩ [mV]", row=row, col=col)

    ttl = "Averaged I quadrature" if mode == "avg" else "I quadrature heat‑map"
    fig.update_layout(
        title=f"DRAG Calibration – {ttl}",
        height=280 * n_rows,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        coloraxis=dict(colorbar=dict(title="I [mV]")) if mode == "heat" else None,
    )
    return fig


# ────────────────────────────────────────────────────────────────────
# 3. Summary Table
# ────────────────────────────────────────────────────────────────────
def create_summary_table(d: dict):
    rows = []
    for i, q in enumerate(d["qubits"]):
        ok = bool(d["success"][i])
        rows.append(
            html.Tr(
                [
                    html.Td(q),
                    html.Td(f"{d['opt_alpha'][i]: .3f}" if ok else "—"),
                    html.Td("✓" if ok else "✗"),
                ],
                className="table-success" if ok else "table-warning",
            )
        )
    thead = html.Thead(html.Tr([html.Th("Qubit"),
                                html.Th("optimal α"),
                                html.Th("Fit")]))
    return dbc.Table([thead, html.Tbody(rows)],
                     bordered=True, striped=True, size="sm", responsive=True)


# ────────────────────────────────────────────────────────────────────
# 4. 레이아웃
# ────────────────────────────────────────────────────────────────────
def create_drag_layout(folder: str | Path):
    uid = str(folder).replace("\\", "_").replace("/", "_").replace(":", "")
    data = load_drag_data(folder)
    if not data:
        return html.Div([dbc.Alert("데이터 로드 실패", color="danger"),
                         html.Pre(str(folder))])

    init_mode = "avg"
    summary_fig = create_summary_figure(data)
    detail_fig  = create_drag_plot(data, init_mode)

    return html.Div(
        [
            dcc.Store(id={"type": "drag-data", "index": uid},
                      data={"folder": str(folder)}),

            # ── 제목 ----------------------------------------------------------------
            dbc.Row(dbc.Col(html.H3(f"DRAG Calibration – {Path(folder).name}")),
                    className="mb-3"),

            # ── Summary figure (최상단) --------------------------------------------
            dbc.Row(dbc.Col(
                dcc.Graph(figure=summary_fig, config={"displayModeBar": True}),
                md=12), className="mb-4"),

            # ── View selector -------------------------------------------------------
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            dcc.RadioItems(
                                id={"type": "drag-view", "index": uid},
                                options=[
                                    {"label": " Averaged I", "value": "avg"},
                                    {"label": " Heat‑map",   "value": "heat"},
                                ],
                                value=init_mode,
                                inline=True,
                            )
                        )
                    ), md=12
                ), className="mb-3"
            ),

            # ── 상세 plot + summary table -------------------------------------------
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Loading(
                            children=[dcc.Graph(
                                id={"type": "drag-plot", "index": uid},
                                figure=detail_fig,
                                config={"displayModeBar": True})],
                            type="default",
                        ), md=8),
                    dbc.Col(
                        [
                            html.H5("Summary"),
                            create_summary_table(data),
                            html.Hr(),
                            html.H6("Debug"),
                            html.Pre(f"Folder: {folder}\nQubits: {data['n']}"),
                        ], md=4),
                ]
            ),
        ]
    )


# ────────────────────────────────────────────────────────────────────
# 5. 콜백
# ────────────────────────────────────────────────────────────────────
def register_drag_callbacks(app: dash.Dash):
    @app.callback(
        Output({"type": "drag-plot", "index": MATCH}, "figure"),
        Input({"type": "drag-view", "index": MATCH}, "value"),
        State({"type": "drag-data", "index": MATCH}, "data"),
    )
    def _update_plot(view_mode, store):
        if not store:
            return go.Figure()
        d = load_drag_data(store["folder"])
        return create_drag_plot(d, view_mode)
