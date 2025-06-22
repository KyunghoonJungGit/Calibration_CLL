import xarray as xr
import numpy as np
import json
import os
import glob
from pathlib import Path

def test_data_loading(folder_path):
    """데이터 로딩을 단계별로 테스트"""
    print("="*60)
    print(f"Testing data loading for: {folder_path}")
    print("="*60)
    
    # 1. 폴더 존재 확인
    if not os.path.exists(folder_path):
        print(f"ERROR: Folder does not exist: {folder_path}")
        return
    
    print(f"✓ Folder exists: {folder_path}")
    
    # 2. 파일 목록 확인
    files = os.listdir(folder_path)
    print(f"\nFiles in folder: {files}")
    
    # 3. 필수 파일 확인
    required_files = ['ds_raw.h5', 'ds_fit.h5', 'data.json', 'node.json']
    for req_file in required_files:
        file_path = os.path.join(folder_path, req_file)
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path) / 1024  # KB
            print(f"✓ {req_file} exists ({file_size:.1f} KB)")
        else:
            print(f"✗ {req_file} NOT FOUND")
    
    # 4. H5 파일 로딩 테스트
    print("\n" + "-"*40)
    print("Testing H5 file loading...")
    
    try:
        # ds_raw.h5 테스트
        ds_raw_path = os.path.join(folder_path, 'ds_raw.h5')
        print(f"\nLoading {ds_raw_path}...")
        
        # 다양한 엔진으로 시도
        engines = ['h5netcdf', 'netcdf4', None]
        ds_raw = None
        
        for engine in engines:
            try:
                print(f"  Trying engine: {engine}")
                ds_raw = xr.open_dataset(ds_raw_path, engine=engine)
                print(f"  ✓ Success with engine: {engine}")
                break
            except Exception as e:
                print(f"  ✗ Failed with engine {engine}: {str(e)}")
        
        if ds_raw is not None:
            print(f"\nds_raw loaded successfully!")
            print(f"Variables: {list(ds_raw.variables)}")
            print(f"Dimensions: {dict(ds_raw.dims)}")
            
            # 주요 변수 확인
            if 'qubit' in ds_raw:
                qubits = ds_raw['qubit'].values
                print(f"Qubits: {qubits}")
                print(f"Number of qubits: {len(qubits)}")
            
            if 'readout_time' in ds_raw:
                readout_time = ds_raw['readout_time'].values
                print(f"Readout time shape: {readout_time.shape}")
                print(f"Readout time range: {readout_time[0]:.1f} - {readout_time[-1]:.1f} ns")
            
            # 데이터 변수 확인
            for var in ['adcI', 'adcQ', 'adc_single_runI', 'adc_single_runQ']:
                if var in ds_raw:
                    data = ds_raw[var]
                    print(f"{var}: shape={data.shape}, dtype={data.dtype}")
                    # 첫 번째 큐빗의 데이터 샘플
                    if len(qubits) > 0:
                        sample_data = data.sel(qubit=qubits[0]).values
                        print(f"  Sample data range: {np.min(sample_data):.6f} to {np.max(sample_data):.6f}")
        
        # ds_fit.h5 테스트
        ds_fit_path = os.path.join(folder_path, 'ds_fit.h5')
        print(f"\n\nLoading {ds_fit_path}...")
        
        ds_fit = None
        for engine in engines:
            try:
                print(f"  Trying engine: {engine}")
                ds_fit = xr.open_dataset(ds_fit_path, engine=engine)
                print(f"  ✓ Success with engine: {engine}")
                break
            except Exception as e:
                print(f"  ✗ Failed with engine {engine}: {str(e)}")
        
        if ds_fit is not None:
            print(f"\nds_fit loaded successfully!")
            print(f"Variables: {list(ds_fit.variables)}")
            
            # 주요 변수 확인
            for var in ['success', 'delay', 'threshold']:
                if var in ds_fit:
                    data = ds_fit[var].values
                    print(f"{var}: shape={data.shape}, values={data[:5]}...")
    
    except Exception as e:
        print(f"\nERROR loading H5 files: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 5. JSON 파일 로딩 테스트
    print("\n" + "-"*40)
    print("Testing JSON file loading...")
    
    try:
        # data.json
        data_json_path = os.path.join(folder_path, 'data.json')
        with open(data_json_path, 'r', encoding='utf-8') as f:
            data_json = json.load(f)
        print(f"✓ data.json loaded successfully")
        print(f"  Keys: {list(data_json.keys())[:10]}...")
        
        # node.json
        node_json_path = os.path.join(folder_path, 'node.json')
        with open(node_json_path, 'r', encoding='utf-8') as f:
            node_json = json.load(f)
        print(f"✓ node.json loaded successfully")
        print(f"  Keys: {list(node_json.keys())[:10]}...")
        
    except Exception as e:
        print(f"\nERROR loading JSON files: {str(e)}")
        import traceback
        traceback.print_exc()

def find_all_experiments(base_path='./dashboard_data'):
    """모든 실험 폴더 찾기"""
    print("\n" + "="*60)
    print(f"Searching for experiments in: {base_path}")
    print("="*60)
    
    if not os.path.exists(base_path):
        print(f"ERROR: Base path does not exist: {base_path}")
        return []
    
    experiments = []
    
    # 날짜 폴더 찾기
    date_folders = glob.glob(os.path.join(base_path, '*_*_*'))
    print(f"Found {len(date_folders)} date folders")
    
    for date_folder in date_folders:
        if not os.path.isdir(date_folder):
            continue
        
        date_name = os.path.basename(date_folder)
        print(f"\nDate folder: {date_name}")
        
        # 실험 폴더 찾기
        exp_folders = glob.glob(os.path.join(date_folder, 'tof_*'))
        print(f"  Found {len(exp_folders)} TOF experiments")
        
        for exp_folder in exp_folders:
            exp_name = os.path.basename(exp_folder)
            print(f"    - {exp_name}")
            experiments.append(exp_folder)
    
    return experiments

if __name__ == "__main__":
    # 모든 실험 찾기
    experiments = find_all_experiments()
    
    if experiments:
        # 첫 번째 실험 테스트
        print(f"\nTesting first experiment...")
        test_data_loading(experiments[0])
    else:
        print("\nNo experiments found!")
        
    # 특정 폴더 직접 테스트 (필요시)
    # test_data_loading('./dashboard_data/2025_06_20/tof_064557')