import dash
from dash import dcc, html, Input, Output, State, MATCH, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.subplots as subplots
import xarray as xr
import numpy as np
import json
import os
import glob
from pathlib import Path

def load_tof_data(folder_path):
    """TOF 실험 데이터 로드"""
    try:
        # Windows 경로 정규화
        folder_path = os.path.normpath(folder_path)
        
        # 데이터 파일 경로
        ds_raw_path = os.path.join(folder_path, 'ds_raw.h5')
        ds_fit_path = os.path.join(folder_path, 'ds_fit.h5')
        data_json_path = os.path.join(folder_path, 'data.json')
        node_json_path = os.path.join(folder_path, 'node.json')
        
        # 파일 존재 확인
        print(f"\nChecking files in: {folder_path}")
        print(f"ds_raw.h5 exists: {os.path.exists(ds_raw_path)}")
        print(f"ds_fit.h5 exists: {os.path.exists(ds_fit_path)}")
        print(f"data.json exists: {os.path.exists(data_json_path)}")
        print(f"node.json exists: {os.path.exists(node_json_path)}")
        
        if not all([os.path.exists(ds_raw_path), os.path.exists(ds_fit_path), 
                   os.path.exists(data_json_path), os.path.exists(node_json_path)]):
            print(f"Missing required files in {folder_path}")
            return None
        
        # 데이터 로드
        print(f"Loading data from {folder_path}")
        ds_raw = xr.open_dataset(ds_raw_path, engine='h5netcdf')
        ds_fit = xr.open_dataset(ds_fit_path, engine='h5netcdf')
        
        with open(data_json_path, 'r', encoding='utf-8') as f:
            data_json = json.load(f)
        
        with open(node_json_path, 'r', encoding='utf-8') as f:
            node_json = json.load(f)
        
        # 데이터 추출
        qubits = ds_raw['qubit'].values
        n_qubits = len(qubits)
        
        # 주요 파라미터 추출
        success = ds_fit['success'].values
        delays = ds_fit['delay'].values
        thresholds = ds_fit['threshold'].values
        readout_time = ds_raw['readout_time'].values
        
        print(f"Successfully loaded data for {n_qubits} qubits")
        
        return {
            'ds_raw': ds_raw,
            'ds_fit': ds_fit,
            'data_json': data_json,
            'node_json': node_json,
            'qubits': qubits,
            'n_qubits': n_qubits,
            'success': success,
            'delays': delays,
            'thresholds': thresholds,
            'readout_time': readout_time
        }
    except Exception as e:
        print(f"Error loading data from {folder_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def create_tof_plots(data, view_mode='averaged'):
    """TOF 플롯 생성"""
    if not data:
        return go.Figure()
    
    try:
        qubits = data['qubits']
        n_qubits = data['n_qubits']
        readout_time = data['readout_time']
        delays = data['delays']
        thresholds = data['thresholds']
        success = data['success']
        ds_raw = data['ds_raw']
        
        print(f"Creating plots for {n_qubits} qubits, view_mode={view_mode}")
        
        # 서브플롯 생성 (2열)
        n_cols = 2
        n_rows = int(np.ceil(n_qubits / n_cols))
        
        fig = subplots.make_subplots(
            rows=n_rows, 
            cols=n_cols,
            subplot_titles=[f'{q}' for q in qubits],
            vertical_spacing=0.08,
            horizontal_spacing=0.1
        )
        
        # 색상 정의
        color_I = 'blue'
        color_Q = 'red'
        color_tof = 'black'
        
        for idx, qubit in enumerate(qubits):
            row = idx // n_cols + 1
            col = idx % n_cols + 1
            
            try:
                # 데이터 추출
                if view_mode == 'averaged':
                    adcI = ds_raw['adcI'].sel(qubit=qubit).values * 1e3  # mV 변환
                    adcQ = ds_raw['adcQ'].sel(qubit=qubit).values * 1e3
                else:  # single run
                    adcI = ds_raw['adc_single_runI'].sel(qubit=qubit).values * 1e3
                    adcQ = ds_raw['adc_single_runQ'].sel(qubit=qubit).values * 1e3
                
                print(f"  Qubit {qubit}: I shape={adcI.shape}, Q shape={adcQ.shape}")
                
                # ADC 범위 계산 (matplotlib 코드와 동일하게)
                adc_range = 0.5  # mV (matplotlib 코드에서 0.5e-3 * 1e3)
                
                # ADC 범위 표시 (회색 배경)
                fig.add_trace(
                    go.Scatter(
                        x=[readout_time[0], readout_time[-1], readout_time[-1], readout_time[0], readout_time[0]],
                        y=[-adc_range, -adc_range, adc_range, adc_range, -adc_range],
                        fill='toself',
                        fillcolor='lightgray',
                        line=dict(width=0),
                        opacity=0.3,
                        showlegend=False,
                        hoverinfo='skip',
                        name='ADC Range'
                    ),
                    row=row, col=col
                )
                
                # I 채널 플롯
                fig.add_trace(
                    go.Scatter(
                        x=readout_time,
                        y=adcI,
                        mode='lines',
                        name='I' if idx == 0 else None,
                        line=dict(color=color_I, width=1),
                        showlegend=(idx == 0),
                        legendgroup='I'
                    ),
                    row=row, col=col
                )
                
                # Q 채널 플롯
                fig.add_trace(
                    go.Scatter(
                        x=readout_time,
                        y=adcQ,
                        mode='lines',
                        name='Q' if idx == 0 else None,
                        line=dict(color=color_Q, width=1),
                        showlegend=(idx == 0),
                        legendgroup='Q'
                    ),
                    row=row, col=col
                )
                
                # TOF 라인 추가 (피팅 성공시)
                if success[idx]:
                    fig.add_vline(
                        x=delays[idx],
                        line=dict(color=color_tof, dash='dash', width=1),
                        row=row, col=col
                    )
                    
                    # 첫 번째 서브플롯에만 TOF 범례 추가
                    if idx == 0:
                        fig.add_trace(
                            go.Scatter(
                                x=[None],
                                y=[None],
                                mode='lines',
                                name='TOF',
                                line=dict(color=color_tof, dash='dash', width=1),
                                showlegend=True
                            ),
                            row=row, col=col
                        )
                
                # ADC Range 텍스트 추가
                fig.add_annotation(
                    text="ADC Range",
                    xref=f"x{idx+1}",
                    yref=f"y{idx+1}",
                    x=readout_time[0] + 20,
                    y=adc_range * 0.9,
                    showarrow=False,
                    font=dict(size=8, color="gray"),
                    row=row, col=col
                )
                
                # 축 설정 (matplotlib과 동일하게)
                fig.update_xaxes(
                    title_text='Time [ns]' if row == n_rows else None,
                    range=[0, 1000],
                    row=row, col=col,
                    showgrid=True,
                    gridcolor='rgba(0,0,0,0.1)'
                )
                
                y_range = 0.6 if view_mode == 'averaged' else 3
                fig.update_yaxes(
                    title_text='Readout amplitude [mV]' if col == 1 else None,
                    range=[-y_range, y_range],
                    row=row, col=col,
                    showgrid=True,
                    gridcolor='rgba(0,0,0,0.1)'
                )
                
            except Exception as e:
                print(f"  Error plotting qubit {qubit}: {str(e)}")
        
        # 레이아웃 업데이트
        title = f'Time of Flight Calibration - {"Averaged Run" if view_mode == "averaged" else "Single Run"}'
        fig.update_layout(
            title=title,
            height=300 * n_rows,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            template="plotly_white"
        )
        
        return fig
        
    except Exception as e:
        print(f"Error in create_tof_plots: {str(e)}")
        import traceback
        traceback.print_exc()
        return go.Figure()

def create_summary_table(data):
    """요약 테이블 생성"""
    if not data:
        return html.Div("데이터 없음")
    
    qubits = data['qubits']
    delays = data['delays']
    thresholds = data['thresholds']
    success = data['success']
    
    # 테이블 헤더
    table_header = [
        html.Thead([
            html.Tr([
                html.Th("Qubit"),
                html.Th("Delay (ns)"),
                html.Th("Threshold (mV)"),
                html.Th("Fitting Success")
            ])
        ])
    ]
    
    # 테이블 바디
    rows = []
    for i, qubit in enumerate(qubits):
        row_class = "table-success" if success[i] else "table-warning"
        rows.append(
            html.Tr([
                html.Td(qubit),
                html.Td(f"{delays[i]:.1f}"),
                html.Td(f"{thresholds[i]*1e3:.2f}"),
                html.Td("✓" if success[i] else "✗")
            ], className=row_class)
        )
    
    table_body = [html.Tbody(rows)]
    
    return dbc.Table(
        table_header + table_body,
        bordered=True,
        hover=True,
        responsive=True,
        striped=True,
        size="sm"
    )

def create_tof_layout(folder_path):
    """TOF 대시보드 레이아웃 생성"""
    # 고유한 ID 생성 (폴더 경로 기반)
    unique_id = folder_path.replace('/', '_').replace('\\', '_').replace('.', '').replace(':', '')
    
    # 데이터 로드 시도
    try:
        data = load_tof_data(folder_path)
        
        if not data:
            return html.Div([
                dbc.Alert("데이터 로드 실패 - 파일을 찾을 수 없거나 읽을 수 없습니다.", color="danger"),
                html.Pre(f"Folder path: {folder_path}")
            ])
        
        # 초기 플롯 생성
        initial_fig = create_tof_plots(data, 'averaged')
        
        # 레이아웃 생성
        layout = html.Div([
            dcc.Store(id={'type': 'tof-data', 'index': unique_id}, data={
                'folder_path': folder_path,
                'n_qubits': data['n_qubits']
            }),
            
            dbc.Row([
                dbc.Col([
                    html.H3(f"TOF Calibration - {os.path.basename(folder_path)}")
                ])
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    html.Label("View Mode:"),
                                    dcc.RadioItems(
                                        id={'type': 'tof-view-mode', 'index': unique_id},
                                        options=[
                                            {'label': ' Averaged Run', 'value': 'averaged'},
                                            {'label': ' Single Run', 'value': 'single'}
                                        ],
                                        value='averaged',
                                        inline=True,
                                        className="ms-2"
                                    )
                                ], md=6),
                                dbc.Col([
                                    html.Div(f"Total Qubits: {data['n_qubits']}", 
                                           className="text-end mt-2")
                                ], md=6)
                            ])
                        ])
                    ])
                ])
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    dcc.Loading(
                        id="loading-tof-plot",
                        type="default",
                        children=[
                            dcc.Graph(
                                id={'type': 'tof-plot', 'index': unique_id},
                                figure=initial_fig,
                                config={'displayModeBar': True}
                            )
                        ]
                    )
                ], md=8),
                dbc.Col([
                    html.H5("Summary Statistics"),
                    html.Div(id='tof-summary-table', children=create_summary_table(data)),
                    html.Hr(),
                    html.H6("Debug Info"),
                    html.Pre(f"Folder: {folder_path}\nQubits: {len(data['qubits'])}\nSuccess: {sum(data['success'])}/{len(data['success'])}")
                ], md=4)
            ])
        ])
        
        return layout
        
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        return html.Div([
            dbc.Alert("Error creating TOF layout", color="danger"),
            html.Pre(error_msg)
        ])

def register_tof_callbacks(app):
    """TOF 관련 콜백 등록"""
    
    @app.callback(
        Output({'type': 'tof-plot', 'index': MATCH}, 'figure'),
        [Input({'type': 'tof-view-mode', 'index': MATCH}, 'value')],
        [State({'type': 'tof-data', 'index': MATCH}, 'data')]
    )
    def update_tof_plot(view_mode, tof_data):
        if not tof_data or not view_mode:
            return go.Figure()
        
        # 데이터 다시 로드
        data = load_tof_data(tof_data['folder_path'])
        return create_tof_plots(data, view_mode)