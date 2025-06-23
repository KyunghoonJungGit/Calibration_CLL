# ======================================================================
#  rb1q_dashboard.py   (FULL / REVISED)
# ======================================================================
"""
Dash module for **1Q Randomized‑Benchmarking** experiments
==========================================================
* 1‑D    : circuit‑depth  →  averaged qubit‑state  (± fit)
* Layout : >=10 qubits 지원, 2 열 × N 행 + 페이지네이션(8 qubits/page)
--------------------------------------------------------------------
Author : (작성자 이름)
Rev.   : 2025‑06‑22
"""
from __future__ import annotations

import os, json
from pathlib import Path
from typing import Any

import dash
from dash import dcc, html, Input, Output, State, MATCH
import dash_bootstrap_components as dbc
import numpy as np
import xarray as xr
import plotly.graph_objs as go
import plotly.subplots as subplots


# ────────────────────────────────────────────────────────────────────
# 0. 공용 유틸
# ────────────────────────────────────────────────────────────────────
PER_PAGE = 8            # qubits per page
N_COLS   = 2            # subplot columns


def open_xr_dataset(path: str, engines=("h5netcdf", "netcdf4", None)) -> xr.Dataset:
    """엔진 자동 변경을 시도하며 xarray Dataset을 연다."""
    last_exc: Exception | None = None
    for eng in engines:
        try:
            return xr.open_dataset(path, engine=eng)
        except Exception as e:  # pragma: no cover
            last_exc = e
    raise last_exc if last_exc else RuntimeError(f"Cannot open dataset: {path}")


def decay_exp(x: np.ndarray, a: float, offset: float, decay: float) -> np.ndarray:
    """RB decay 모델 – offset + a·exp(decay·x)"""
    return offset + a * np.exp(decay * x)


# ────────────────────────────────────────────────────────────────────
# 1. 데이터 로더
# ────────────────────────────────────────────────────────────────────
def load_rb_data(folder: str | Path) -> dict[str, Any] | None:
    """
    폴더(또는 절대 경로) 내의 RB 결과 파일 4종(ds_raw.h5, ds_fit.h5,
    data.json, node.json)을 불러와 Dash 프런트엔드에서 바로 사용할 수
    있는 dict 형태로 반환한다.

    반환 필드
    ----------
    qubits          ndarray[str]   (q)
    n               int            qubit 개수
    depths          ndarray[float] (d)
    y_data          ndarray        (q, d)  • averaged qubit state
    success         ndarray[bool]  (q)     • fit 성공 여부
    rb_fidelity     ndarray        (q)     • 100 × (1 – error_per_gate)
    fit_a/offset/decay             (q)     • fit 파라미터
    ds_raw, ds_fit                원본 데이터셋 (필요 시 활용)
    data_json, node_json          메타 정보
    """
    folder = Path(folder).expanduser().resolve()
    paths = {
        "ds_raw":  folder / "ds_raw.h5",
        "ds_fit":  folder / "ds_fit.h5",
        "data_js": folder / "data.json",
        "node_js": folder / "node.json",
    }
    if not all(p.exists() for p in paths.values()):
        print(f"[load_rb_data] Required files not found in {folder}")
        return None

    # ── 파일 로드 ─────────────────────────────────────────────────
    ds_raw  = open_xr_dataset(str(paths["ds_raw"]))
    ds_fit  = open_xr_dataset(str(paths["ds_fit"]))
    data_js = json.loads(paths["data_js"].read_text(encoding="utf-8"))
    node_js = json.loads(paths["node_js"].read_text(encoding="utf-8"))

    qubits = ds_fit.get("qubit", ds_raw["qubit"]).values.astype(str)
    n_q    = len(qubits)

    # ── depth 축 ────────────────────────────────────────────────
    depths = (
        ds_fit.coords["depths"]
        if "depths" in ds_fit.coords
        else ds_fit.coords.get("circuit_depth", None)
    )
    if depths is None:
        raise KeyError("'depths' coordinate가 ds_fit에 없습니다.")
    depths = depths.values.astype(float)

    # ── 평균 상태 데이터 (y축) ────────────────────────────────────
    if "averaged_data" in ds_fit:
        y_data = ds_fit["averaged_data"].values                      # (q, d)
    elif "averaged_data" in ds_raw:
        y_data = ds_raw["averaged_data"].values                      # (q, d)
    elif "state" in ds_fit:                                          # (q, seq, d)
        y_data = ds_fit["state"].mean(dim="nb_of_sequences").values
    else:
        raise KeyError("averaged_data/state 변수를 찾을 수 없습니다.")

    # ── 피팅 파라미터 ────────────────────────────────────────────
    def _param_from(name: str) -> np.ndarray:
        if "fit_data" in ds_fit:
            return ds_fit["fit_data"].sel(fit_vals=name).values
        return ds_fit.get(name, np.full(n_q, np.nan)).values  # type: ignore

    fit_a      = _param_from("a")
    fit_offset = _param_from("offset")
    fit_decay  = _param_from("decay")

    # ── 성공 여부 ───────────────────────────────────────────────
    if "success" in ds_fit:
        success = ds_fit["success"].values.astype(bool)
    else:
        # 없으면 error_per_gate 유효성으로 대체
        success = ~np.isnan(_param_from("decay"))

    # ── RB fidelity (error_per_gate 사용) ─────────────────────────
    rb_fid = np.full(n_q, np.nan)
    for i, q in enumerate(qubits):
        res = data_js.get("fit_results", {}).get(str(q), {})
        if "error_per_gate" in res and res["error_per_gate"] is not None:
            rb_fid[i] = 100.0 * (1.0 - float(res["error_per_gate"]))

    return dict(
        qubits=qubits, n=n_q,
        depths=depths, y_data=y_data,
        success=success, rb_fidelity=rb_fid,
        fit_a=fit_a, fit_offset=fit_offset, fit_decay=fit_decay,
        ds_raw=ds_raw, ds_fit=ds_fit,
        data_json=data_js, node_json=node_js,
    )


# ────────────────────────────────────────────────────────────────────
# 1‑B. Pagination helper
# ────────────────────────────────────────────────────────────────────
def slice_page(data: dict[str, Any], page: int) -> dict[str, Any]:
    """qubit 차원(q)만 슬라이싱해 서브‑dict 반환 (depth·메타 유지)."""
    if not data:
        return data
    start = (page - 1) * PER_PAGE
    stop  = min(page * PER_PAGE, data["n"])
    s_qub = slice(start, stop)

    sliced = data.copy()
    for key in ("qubits", "y_data", "success",
                "rb_fidelity", "fit_a", "fit_offset", "fit_decay"):
        sliced[key] = data[key][s_qub]
    sliced["n"] = len(sliced["qubits"])
    return sliced


# ────────────────────────────────────────────────────────────────────
# 2. Plot 생성
# ────────────────────────────────────────────────────────────────────
def create_rb_plot(d: dict[str, Any]) -> go.Figure:
    """Plotly subplots Figure 반환 (Data + Fit)."""
    if not d:
        return go.Figure()

    qbs, n_q      = d["qubits"], d["n"]
    depths        = d["depths"]
    y_data        = d["y_data"]
    success       = d["success"]
    fit_a, fit_o, fit_d = d["fit_a"], d["fit_offset"], d["fit_decay"]

    n_rows = int(np.ceil(n_q / N_COLS))
    fig = subplots.make_subplots(
        rows=n_rows, cols=N_COLS,
        subplot_titles=[str(q) for q in qbs],
        vertical_spacing=0.08, horizontal_spacing=0.07,
    )

    for i, q in enumerate(qbs):
        r, c = divmod(i, N_COLS)
        row, col = r + 1, c + 1

        # ── Raw data (markers) ────────────────────────────────────
        fig.add_trace(
            go.Scatter(
                x=depths,
                y=y_data[i],
                mode="markers",
                marker=dict(size=6, color="royalblue"),
                name="Data" if i == 0 else None,
                showlegend=(i == 0),
            ),
            row=row, col=col,
        )

        # ── Fit curve ─────────────────────────────────────────────
        if bool(success[i]) and not np.isnan(fit_d[i]):
            y_fit = decay_exp(depths, fit_a[i], fit_o[i], fit_d[i])
            fig.add_trace(
                go.Scatter(
                    x=depths, y=y_fit,
                    mode="lines",
                    line=dict(color="firebrick", dash="dash"),
                    name="Fit" if i == 0 else None,
                    showlegend=(i == 0),
                ),
                row=row, col=col,
            )

        # 축 레이블 (가장 아래/왼쪽에만)
        if row == n_rows:
            fig.update_xaxes(title_text="Circuit depth", row=row, col=col)
        if col == 1:
            fig.update_yaxes(title_text="Qubit state", row=row, col=col)

    fig.update_layout(
        title="Single‑qubit Randomized‑Benchmarking",
        height=max(250, 270 * n_rows),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        margin=dict(t=60, l=50, r=30, b=50),
    )
    return fig


# ────────────────────────────────────────────────────────────────────
# 3. Summary Table
# ────────────────────────────────────────────────────────────────────
def create_summary_table(d: dict[str, Any]) -> dbc.Table:
    rows: list[html.Tr] = []
    for i, q in enumerate(d["qubits"]):
        
        ok = bool(d["success"][i])
        fid_txt = (
            f"{d['rb_fidelity'][i]:.3f} %" if not np.isnan(d["rb_fidelity"][i]) else "—"
        )
        rows.append(
            html.Tr(
                [
                    html.Td(q),
                    html.Td(fid_txt),
                    html.Td("✓" if ok else "✗"),
                ],
                className="table-success" if ok else "table-warning",
            )
        )

    thead = html.Thead(
        html.Tr([html.Th("Qubit"),
                 html.Th("1Q RB fidelity"),
                 html.Th("Fit")])
    )
    return dbc.Table([thead, html.Tbody(rows)],
                     bordered=True, striped=True, size="sm", responsive=True)


# ────────────────────────────────────────────────────────────────────
# 4. 레이아웃 생성
# ────────────────────────────────────────────────────────────────────
def create_rb_layout(folder: str | Path) -> html.Div:
    """
    외부에서 `app.layout = create_rb_layout(<실험폴더>)` 처럼 호출.
    """
    uid = str(folder).replace("\\", "_").replace("/", "_").replace(":", "")
    data = load_rb_data(folder)
    if not data:
        return html.Div([dbc.Alert("데이터 로드 실패", color="danger"),
                         html.Pre(str(folder))])

    n_pages = int(np.ceil(data["n"] / PER_PAGE))
    init_fig = create_rb_plot(slice_page(data, 1))

    # ── Pagination 컴포넌트 ─────────────────────────────────────────
    page_selector = dbc.Pagination(
        id={"type": "rb-page", "index": uid},
        active_page=1,
        max_value=n_pages,
        first_last=True,
        fully_expanded=False,
        size="lg",
        className="my-2",
        style=None if n_pages > 1 else {"display": "none"},
    )

    # ── 레이아웃 ----------------------------------------------------
    return html.Div(
        [
            # 데이터 캐싱
            dcc.Store(id={"type": "rb-data", "index": uid},
                      data={"folder": str(folder)}),

            # 제목
            dbc.Row(
                dbc.Col(html.H3(f"1Q Randomized Benchmark – {Path(folder).name}")),
                className="mb-3",
            ),

            # 페이지네이션
            dbc.Row(dbc.Col(page_selector), className="mb-2"),

            # 그래프 + Summary
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Loading(
                            id={"type": "rb-load", "index": uid},
                            type="default",
                            children=dcc.Graph(
                                id={"type": "rb-plot", "index": uid},
                                figure=init_fig,
                                config={"displayModeBar": True},
                            ),
                        ),
                        md=8,
                    ),
                    dbc.Col(
                        [
                            html.H5("Summary"),
                            create_summary_table(data),
                            html.Hr(),
                            html.Small(f"Folder: {folder}"),
                        ],
                        md=4,
                    ),
                ]
            ),
        ],
        className="p-3",
    )


# ────────────────────────────────────────────────────────────────────
# 5. 콜백 등록
# ────────────────────────────────────────────────────────────────────
def register_rb_callbacks(app: dash.Dash):
    """
    Dash 앱 인스턴스에 콜백을 등록한다.
    반드시 앱 생성 후 `register_rb_callbacks(app)` 호출.
    """

    @app.callback(
        Output({"type": "rb-plot", "index": MATCH}, "figure"),
        Input({"type": "rb-page", "index": MATCH}, "active_page"),
        State({"type": "rb-data", "index": MATCH}, "data"),
        prevent_initial_call=True,
    )
    def _update_rb_plot(active_page: int, store: dict[str, str]) -> go.Figure:
        folder = store.get("folder")
        if not folder:
            return go.Figure()
        data = load_rb_data(folder)
        return create_rb_plot(slice_page(data, active_page or 1))


# ────────────────────────────────────────────────────────────────────
# 6. Stand‑alone 실행 (테스트용)
# ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    SAMPLE_PATH = "./"           # ← RB 결과 파일이 있는 폴더로 변경
    app = dash.Dash(__name__,
                    external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.layout = create_rb_layout(SAMPLE_PATH)
    register_rb_callbacks(app)

    app.run_server(debug=True, port=8073)
