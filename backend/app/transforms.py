"""
Cleaning transforms.

Every public transform is a *pure* function: ``f(df, **params) -> new_df``.
They are deliberately self-contained (only pandas / numpy / scipy / sklearn)
because the exported Python script is built by copying the *source code* of the
transforms that were used (see ``export.py``). What the app previews and what
the script does are therefore the same code, not two implementations that can
drift apart.

Rules for transforms:
* never mutate the input frame
* never reset the index (the diff engine aligns before/after on the index)
* keep any helper they need listed in ``HELPERS`` below
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# helpers (copied into exported scripts when a transform needs them)
# --------------------------------------------------------------------------- #

MISSING_TOKENS = ["", "na", "n/a", "#n/a", "nan", "null", "none", "nil", "-", "--", "?", "missing"]


def _is_text(s):
    return s.dtype == object or isinstance(s.dtype, pd.StringDtype)


def _clean_number(value):
    """'$1,234.50' -> 1234.5, '(12)' -> -12, '45%' -> 45.0, else NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[\s$€£¥₹,%()]", "", text)
    if negative:
        text = "-" + text
    try:
        return float(text)
    except ValueError:
        return np.nan


# --------------------------------------------------------------------------- #
# transforms
# --------------------------------------------------------------------------- #

def standardize_missing(df, columns=None, tokens=("", "na", "n/a", "#n/a", "nan", "null", "none", "nil", "-", "--", "?", "missing")):
    out = df.copy()
    token_set = {t.strip().lower() for t in tokens}
    cols = columns or [c for c in out.columns if _is_text(out[c])]
    for c in cols:
        s = out[c]
        mask = s.map(lambda v: isinstance(v, str) and v.strip().lower() in token_set).astype(bool)
        if mask.any():
            out[c] = s.mask(mask, np.nan)
    return out


def trim_whitespace(df, columns=None):
    out = df.copy()
    cols = columns or [c for c in out.columns if _is_text(out[c])]
    for c in cols:
        out[c] = out[c].map(lambda v: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v)
    return out


def standardize_case(df, column, case="lower"):
    out = df.copy()
    fn = {"lower": str.lower, "upper": str.upper, "title": str.title}[case]
    out[column] = out[column].map(lambda v: fn(v) if isinstance(v, str) else v)
    return out


def map_values(df, column, mapping):
    out = df.copy()
    out[column] = out[column].map(lambda v: mapping.get(v, v) if isinstance(v, str) else v)
    return out


def convert_numeric(df, column):
    out = df.copy()
    out[column] = out[column].map(_clean_number).astype("float64")
    if out[column].dropna().map(float.is_integer).all():
        out[column] = out[column].astype("Int64")
    return out


def parse_dates(df, column, dayfirst=False):
    out = df.copy()
    out[column] = pd.to_datetime(out[column], errors="coerce", format="mixed", dayfirst=dayfirst)
    return out


def fill_missing(df, column, strategy="median", value=None):
    out = df.copy()
    s = out[column]
    if strategy == "mean":
        fill = s.mean()
    elif strategy == "median":
        fill = s.median()
    elif strategy == "mode":
        modes = s.mode(dropna=True)
        fill = modes.iloc[0] if len(modes) else None
    elif strategy == "constant":
        fill = value
    elif strategy == "ffill":
        out[column] = s.ffill()
        return out
    elif strategy == "bfill":
        out[column] = s.bfill()
        return out
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    if fill is None or (isinstance(fill, float) and np.isnan(fill)):
        return out
    if pd.api.types.is_integer_dtype(s.dtype) and strategy in ("mean", "median"):
        fill = int(round(float(fill)))
    elif pd.api.types.is_numeric_dtype(s.dtype) and strategy == "constant":
        fill = float(fill)
    out[column] = s.fillna(fill)
    return out


def drop_missing_rows(df, columns=None, how="any"):
    return df.dropna(subset=columns or None, how=how)


def drop_duplicates(df, subset=None, keep="first"):
    keep = False if keep == "none" else keep
    return df.drop_duplicates(subset=subset or None, keep=keep)


def handle_outliers(df, column, method="iqr", threshold=1.5, action="clip"):
    out = df.copy()
    s = pd.to_numeric(out[column], errors="coerce")
    valid = s.dropna()
    if len(valid) < 4:
        return out
    if method == "iqr":
        q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
        spread = q3 - q1
        low, high = q1 - threshold * spread, q3 + threshold * spread
    elif method == "zscore":
        mean, std = valid.mean(), valid.std(ddof=0)
        low, high = mean - threshold * std, mean + threshold * std
    else:
        raise ValueError(f"Unknown method: {method}")
    is_out = (s < low) | (s > high)
    if action == "remove":
        return out.loc[~is_out.fillna(False)]
    if action == "null":
        out[column] = out[column].mask(is_out)
        return out
    if action == "clip":
        clipped = s.clip(lower=low, upper=high)
        if pd.api.types.is_integer_dtype(out[column].dtype):
            clipped = clipped.round().astype(out[column].dtype)
        out[column] = clipped
        return out
    raise ValueError(f"Unknown action: {action}")


def drop_anomalous_rows(df, columns=None, contamination=0.02):
    from sklearn.ensemble import IsolationForest

    cols = columns or [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    if len(cols) < 2 or len(df) < 30:
        return df.copy()
    X = df[cols].apply(pd.to_numeric, errors="coerce").astype("float64")
    X = X.fillna(X.median()).fillna(0.0)
    labels = IsolationForest(contamination=contamination, random_state=0).fit_predict(X.to_numpy())
    return df.loc[labels == 1]


def drop_column(df, column):
    return df.drop(columns=[column])


def snake_case_columns(df):
    out = df.copy()
    names, seen = [], {}
    for c in out.columns:
        n = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(c).strip())
        n = re.sub(r"[^0-9a-zA-Z]+", "_", n).strip("_").lower() or "column"
        seen[n] = seen.get(n, 0) + 1
        names.append(n if seen[n] == 1 else f"{n}_{seen[n]}")
    out.columns = names
    return out


# --------------------------------------------------------------------------- #
# registry: what the UI shows, and what the script generator needs
# --------------------------------------------------------------------------- #

def _p(name, type_, label, required=False, default=None, options=None):
    return {"name": name, "type": type_, "label": label, "required": required, "default": default, "options": options}


OPERATIONS = {
    "standardize_missing": {
        "fn": standardize_missing, "label": "Convert placeholders to missing",
        "description": "Treat values like N/A, null, '-' or empty strings as real missing values.",
        "helpers": ["_is_text"], "imports": [],
        "params": [_p("columns", "columns", "Columns (blank = all text columns)"),
                   _p("tokens", "list", "Placeholder tokens", default=MISSING_TOKENS)],
    },
    "trim_whitespace": {
        "fn": trim_whitespace, "label": "Trim whitespace",
        "description": "Remove leading/trailing spaces and collapse repeated spaces.",
        "helpers": ["_is_text"], "imports": ["re"],
        "params": [_p("columns", "columns", "Columns (blank = all text columns)")],
    },
    "standardize_case": {
        "fn": standardize_case, "label": "Standardize letter case",
        "description": "Convert a text column to lower, upper or title case.",
        "helpers": [], "imports": [],
        "params": [_p("column", "column", "Column", True),
                   _p("case", "select", "Case", True, "lower", ["lower", "upper", "title"])],
    },
    "map_values": {
        "fn": map_values, "label": "Merge category variants",
        "description": "Replace inconsistent spellings with one canonical value.",
        "helpers": [], "imports": [],
        "params": [_p("column", "column", "Column", True), _p("mapping", "mapping", "Replace → with", True)],
    },
    "convert_numeric": {
        "fn": convert_numeric, "label": "Convert text to numbers",
        "description": "Strip currency symbols, commas and % signs, then convert to a numeric column. Unparseable values become missing.",
        "helpers": ["_clean_number"], "imports": ["re"],
        "params": [_p("column", "column", "Column", True)],
    },
    "parse_dates": {
        "fn": parse_dates, "label": "Parse dates",
        "description": "Convert text to real dates. Invalid dates become missing (NaT).",
        "helpers": [], "imports": [],
        "params": [_p("column", "column", "Column", True),
                   _p("dayfirst", "bool", "Day comes first (31/12/2024)", False, False)],
    },
    "fill_missing": {
        "fn": fill_missing, "label": "Fill missing values",
        "description": "Fill empty cells with a statistic, a constant, or neighbouring values.",
        "helpers": [], "imports": [],
        "params": [_p("column", "column", "Column", True),
                   _p("strategy", "select", "Strategy", True, "median", ["mean", "median", "mode", "constant", "ffill", "bfill"]),
                   _p("value", "text", "Constant value (when strategy = constant)")],
    },
    "drop_missing_rows": {
        "fn": drop_missing_rows, "label": "Drop rows with missing values",
        "description": "Remove rows that have missing values in the chosen columns.",
        "helpers": [], "imports": [],
        "params": [_p("columns", "columns", "Columns (blank = all)"),
                   _p("how", "select", "Drop when", True, "any", ["any", "all"])],
    },
    "drop_duplicates": {
        "fn": drop_duplicates, "label": "Remove duplicate rows",
        "description": "Keep one copy of rows that repeat.",
        "helpers": [], "imports": [],
        "params": [_p("subset", "columns", "Compare on columns (blank = entire row)"),
                   _p("keep", "select", "Keep", True, "first", ["first", "last", "none"])],
    },
    "handle_outliers": {
        "fn": handle_outliers, "label": "Handle outliers",
        "description": "Clip, blank out or remove values far from the rest of the column.",
        "helpers": [], "imports": [],
        "params": [_p("column", "column", "Column", True),
                   _p("method", "select", "Method", True, "iqr", ["iqr", "zscore"]),
                   _p("threshold", "number", "Threshold (IQR multiplier or z-score)", True, 1.5),
                   _p("action", "select", "Action", True, "clip", ["clip", "null", "remove"])],
    },
    "drop_anomalous_rows": {
        "fn": drop_anomalous_rows, "label": "Drop multivariate anomalies",
        "description": "Use an Isolation Forest to drop rows that are unusual across several numeric columns together.",
        "helpers": [], "imports": [],
        "params": [_p("columns", "columns", "Numeric columns (blank = all)"),
                   _p("contamination", "number", "Expected share of anomalies", True, 0.02)],
    },
    "drop_column": {
        "fn": drop_column, "label": "Drop column",
        "description": "Remove a column entirely.",
        "helpers": [], "imports": [],
        "params": [_p("column", "column", "Column", True)],
    },
    "snake_case_columns": {
        "fn": snake_case_columns, "label": "Rename columns to snake_case",
        "description": "Make column names lowercase with underscores. Later steps must use the new names.",
        "helpers": [], "imports": ["re"],
        "params": [],
    },
}


def apply_operation(df: pd.DataFrame, op: str, params: dict) -> pd.DataFrame:
    if op not in OPERATIONS:
        raise ValueError(f"Unknown operation: {op}")
    spec = OPERATIONS[op]
    clean = {k: v for k, v in (params or {}).items() if v is not None and v != "" and v != []}
    allowed = {p["name"] for p in spec["params"]}
    unknown = set(clean) - allowed
    if unknown:
        raise ValueError(f"Unknown parameter(s) for {op}: {', '.join(sorted(unknown))}")
    for p in spec["params"]:
        if p["required"] and p["name"] not in clean and p["default"] is None:
            raise ValueError(f"Missing required parameter: {p['name']}")
    for col_param in ("column",):
        if col_param in clean and clean[col_param] not in df.columns:
            raise ValueError(f"Column '{clean[col_param]}' does not exist at this point in the pipeline")
    for list_param in ("columns", "subset"):
        for c in clean.get(list_param, []) or []:
            if c not in df.columns:
                raise ValueError(f"Column '{c}' does not exist at this point in the pipeline")
    return spec["fn"](df, **clean)
