# FixMyCSV

Upload a messy CSV/Excel file, see what's wrong, preview each fix, build a pipeline of cleaning steps,
undo any step individually, and export the cleaned data plus a Python script that reproduces it.

**Stack:** React + Vite, FastAPI, pandas, SciPy, scikit-learn, SQLite, Plotly. No external API calls.

## Run it

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (dev server with API proxy)
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Production: `npm run build` in `frontend/`, then run only the backend. It serves `frontend/dist` on port 8000.

Try it with `sample_data/messy_customers.csv` (regenerate with `python sample_data/make_sample.py`).
Run tests: `cd backend && pytest`.

## How it works

| Piece | File | What it does |
|---|---|---|
| Type inference and profiling | `app/profiling.py` | Infers real column types (numbers or dates stored as text, booleans, IDs, categories) and profiles each column. |
| Rule-based detection | `app/profiling.py` | Finds duplicates, placeholder text (`N/A`, `-`), missing values, stray whitespace, inconsistent category spellings (normalised keys and fuzzy matching), unparseable numbers and dates, IQR and z-score (SciPy) outliers, multivariate anomalies (Isolation Forest), awkward column names. |
| Transforms | `app/transforms.py` | Pure functions: `f(df, **params) -> df`. |
| Pipeline | `app/pipeline.py` | Steps live in SQLite. The current dataset is always **replayed from the untouched original**, so undoing any step is just re-running without it. A step that depended on an undone one is reported as skipped, not crashed. |
| Diff engine | `app/diffing.py` | For each step: rows removed, cells changed (before → after samples), dtype changes, missing counts, and before/after distributions. |
| Quality score | `app/profiling.py` | Five dimensions (completeness, uniqueness, valid types, consistency, plausible values) computed before and after. |
| Export | `app/export.py` | The script is built from the **source code of the transforms that were used** (`inspect.getsource`), so it can't drift from what the app ran. Tests run the exported script and compare its CSV byte-for-byte with the app's output. |

## API

`POST /api/datasets` · `GET /api/datasets/{id}/state` · `POST …/preview` · `POST …/steps` ·
`PATCH …/steps/{step}` (`{"enabled": false}` = undo) · `DELETE …/steps/{step}` · `GET …/data` ·
`GET …/export/{csv|script|bundle}`

## Adding a cleaning operation

1. Write a pure function in `transforms.py` (never reset the index).
2. Register it in `OPERATIONS` with its parameter spec. The UI form and the exported script pick it up automatically.
3. Optionally teach `detect_issues` to suggest it.
