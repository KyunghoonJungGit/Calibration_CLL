# QUAlibrate Dashboard

A **Dash + Plotly** web application for **interactive visualization of quantum‑hardware calibration experiments**.
It lets you explore *Time‑of‑Flight*, *Resonator & Qubit spectroscopy*, *Rabi / DRAG / T1 / T2 calibrations*, *single‑qubit RB*, and more, all from one browser tab.

---

## 1 · What this repository is about

| Topic              | Details                                                                                                                                                                                                                                                                      |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**        | Provide a uniform, low‑friction UI for *analysts, experimentalists and operators* to inspect the raw data, fitted curves, and summary tables that come out of daily calibration runs on a superconducting‑qubit platform.                                                    |
| **Input data**     | Each experiment folder contains four required files produced by the data‑acquisition back‑end: `ds_raw.h5`, `ds_fit.h5`, `data.json`, `node.json`  *(plus optional extras such as `ds_iq_blobs.h5`)*.                                                                        |
| **Core idea**      | **One experiment = one lightweight Dash module** living under `experiments/<name>_dashboard.py`.  The top‑level `main_dashboard.py` automatically discovers experiment folders, loads the correct module, and injects its *layout* and *callbacks* into the main Dash `app`. |
| **Why it matters** | You get publication‑quality plots with dark‑mode styling, “choose‑your‑metric” radio buttons, pagination for 100+ qubits, and **zero** copy‑and‑paste between notebooks.  Plus it is trivial to bolt on new experiment types (see § 4).                                      |

---

## 2 · Build the Python environment

> **TL;DR – conda users**

```bash
conda create -n qualib_dash python=3.12
conda activate qualib_dash
pip install -r requirements.txt
```

### 2.1 Prerequisites

| Tool                    | Version    | Why                         |
| ----------------------- | ---------- | --------------------------- |
| Python                  | 3.9 – 3.12 | Tested on 3.12              |

> **Note**
>
> * If you prefer **Mambaforge**, replace the `pip install` step with
>   `mamba env create -f environment.yml` (not supplied, but you can export one with `pip‑compile`).

---

## 3 · Use the dashboard from scratch

1. **Clone** the repository

   ```bash
   git clone https://github.com/your‑org/qualibrate‑dashboard.git
   cd qualibrate‑dashboard
   ```

2. **Prepare** the environment (see § 2).

3. **Point** the app at your experiment archive

   * The default base folder is `../QPU_project` (**Note** relative path to `main_dashboard.py`).
   * Adjust it by **either**:
     Editing the line,

     ```python
     EXPERIMENT_BASE_PATH = "../QPU_project"
     ```

     in `main_dashboard.py`.

    * ★ Data Folder Structure
      Your calibration data should live under a top-level folder (configured via `EXPERIMENT_BASE_PATH`) with the following layout:

        EXPERIMENT_BASE_PATH/
        ├── 2025-06-23/ ← date folder: YYYY-MM-DD
        │ ├── #1093_00_hello_qua_112953/ ← experiment folder: #<runID>_<type>_<timestamp>
        │ │ ├── ds_raw.h5
        │ │ ├── ds_fit.h5
        │ │ ├── data.json
        │ │ └── node.json

    - **Date folders** (`YYYY-MM-DD`) group all experiments run on that day.  
    - **Experiment folders** begin with `#<numeric_id>`, contain a slug describing the calibration type, and end with a 6-digit time stamp.  
    - **Within each experiment folder** you **must** have exactly these four files:  
    1. `ds_raw.h5`  
    2. `ds_fit.h5`  
    3. `data.json`  
    4. `node.json`  

    Dash will only show folders matching that pattern and containing all four files.  


4. **Launch** the server

   ```bash
   python main_dashboard.py
   ```

   By default the server is started on `http://127.0.0.1:7700/` with live‑reload (`debug=True`).
   Open the URL and:

   1. Choose an **experiment type** from the first dropdown (Time‑of‑Flight, T1, RB, …).
   2. Pick a **date/time‑stamped run** from the second dropdown.
   3. Enjoy the reactive plots, summary tables, pagination and dark theme.

5. **Troubleshooting**

   *“Files not found”* alerts mean the required quartet (`ds_raw.h5`, `ds_fit.h5`, 2× \*.json) is missing.
   *90 % of display problems* are wrong `plotly.io.templates.default` – run `python -m pip install --upgrade plotly` first.

---

## 4 · Adding another experiment module

> The framework is deliberately minimal – you only implement three things and the rest is auto‑wired.

```text
experiments/
├─ myexperiment_dashboard.py      ◀─ your new file
```

### 4.1 Skeleton to copy‑paste

```python
# experiments/myexperiment_dashboard.py
import dash
from dash import dcc, html, Input, Output, State, MATCH
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.subplots as subplots
import xarray as xr
import numpy as np
import json, os
from pathlib import Path

# 1. ------------- Data loader ---------------------------------
def load_myexp_data(folder: str | Path) -> dict | None:
    """Read ds_raw.h5 etc. and return a tidy dict used by plotting
       • MUST return at least 'qubits' and 'n'."""
    ...
    return {...}

# 2‑A. ------------- Plot creators ------------------------------
def create_myexp_plot(data: dict, *args, **kwargs) -> go.Figure:
    ...

# 2‑B. (optional) summary table, helpers, etc.

# 3. ------------- Layout factory -------------------------------
def create_myexp_layout(folder: str | Path):
    uid = str(folder).replace("\\", "_").replace("/", "_").replace(":", "")
    data = load_myexp_data(folder)
    if not data:
        return html.Div(dbc.Alert("Failed to load", color="danger"))
    init_fig = create_myexp_plot(data, ...)
    return html.Div([
        dcc.Store(id={"type": "myexp-data", "index": uid},
                  data={"folder": str(folder)}),
        dcc.Graph(id={"type": "myexp-plot", "index": uid},
                  figure=init_fig),
        ...
    ])

# 4. ------------- Callback registration -----------------------
def register_myexp_callbacks(app: dash.Dash):
    @app.callback(
        Output({"type": "myexp-plot", "index": MATCH}, "figure"),
        Input (...),
        State(...),
    )
    def _update_plot(...):
        data = load_myexp_data(store["folder"])
        return create_myexp_plot(data, ...)
```

### 4.2 Hook it into the main app

1. **Import** and **register** in `main_dashboard.py`

   ```python
   from experiments.myexperiment_dashboard \
       import create_myexp_layout, register_myexp_callbacks
   ```

2. **Extend** the `experiment_modules` dict

   ```python
   "myexp": dict(
       layout_func   = create_myexp_layout,
       register_func = register_myexp_callbacks,
       title         = "My Cool Experiment",
       patterns      = ["myexp", "cool_exp", "whatever_in_folder_name"],
   ),
   ```

3. **Add** the callback registration line near the bottom:

   ```python
   register_myexp_callbacks(app)
   ```

Done – the dashboard will now auto‑detect any folder whose name contains one of your `patterns` tokens and supplies the expected data files.

---

## 5 · Repository overview

```
├─ main_dashboard.py         ← entry point / routing / folder polling
├─ assets/                   ← CSS & image assets (dark theme, logo …)
├─ experiments/              ← one module per calibration
│   ├─ t1_dashboard.py
│   ├─ ramsey_dashboard.py
│   ├─ ...                   (11 modules today)
│   └─ myexperiment_dashboard.py   ← your new one
├─ theme.py                  ← Plotly template registration
├─ requirements.txt
└─ README.md                 ← you are here
```

---

## 6 · FAQ

* **Hot‑reloading** – Dash already reloads Python & CSS on file save when `debug=True`.
* **Deployment** – Any WSGI container (Gunicorn/uvicorn) works.  Remember to set `debug=False` and adjust `host='0.0.0.0'`.
* **Large data files** – If `ds_raw.h5` exceeds 200 MB use *indexed* `zarr` or supply a down‑sampled version for the dashboard.

---

### Happy calibrating & plotting! 🎉
