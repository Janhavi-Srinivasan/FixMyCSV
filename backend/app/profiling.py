"""Column profiling, type inference and rule-based issue detection."""
from __future__ import annotations

import re
import warnings
from difflib import SequenceMatcher

import numpy as np
import pandas as pd
from scipy import stats

from .transforms import MISSING_TOKENS, _clean_number
from .utils import cell_label, is_text, jsonable

_TOKENS = set(MISSING_TOKENS)
_DATE_LIKE = re.compile(
    r"(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})|(\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b)", re.I
)
_BOOL_TOKENS = {"true", "false", "yes", "no", "y", "n", "t", "f", "0", "1"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


# --------------------------------------------------------------------------- #
# basic helpers
# --------------------------------------------------------------------------- #

def _placeholder_mask(s: pd.Series) -> pd.Series:
    if not is_text(s):
        return pd.Series(False, index=s.index)
    return s.map(lambda v: isinstance(v, str) and v.strip().lower() in _TOKENS).astype(bool)


def _real_values(s: pd.Series) -> pd.Series:
    """Non-null values that are not missing-value placeholders."""
    return s[s.notna() & ~_placeholder_mask(s)]


def _numeric_parse(values: pd.Series):
    parsed = values.map(_clean_number)
    return parsed, parsed.notna()


def _date_parse(values: pd.Series):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    return parsed, parsed.notna()


def _date_like_share(values: pd.Series) -> float:
    if len(values) == 0:
        return 0.0
    return float(values.map(lambda v: bool(_DATE_LIKE.search(str(v)))).mean())


# --------------------------------------------------------------------------- #
# type inference
# --------------------------------------------------------------------------- #

def infer_type(s: pd.Series) -> dict:
    """Return {type, stored_as_text, parse_rate}. Types:
    empty, boolean, integer, float, datetime, categorical, text, identifier, constant."""
    n = len(s)
    vals = _real_values(s)
    if len(vals) == 0:
        return {"type": "empty", "stored_as_text": False, "parse_rate": 1.0}
    if pd.api.types.is_bool_dtype(s.dtype):
        return {"type": "boolean", "stored_as_text": False, "parse_rate": 1.0}
    if pd.api.types.is_datetime64_any_dtype(s.dtype):
        return {"type": "datetime", "stored_as_text": False, "parse_rate": 1.0}
    if pd.api.types.is_numeric_dtype(s.dtype):
        is_int = pd.api.types.is_integer_dtype(s.dtype) or bool((vals.dropna() % 1 == 0).all())
        t = "integer" if is_int else "float"
        looks_like_key = bool(re.search(r"(^|[_\s])(id|code|key|no|number|ref)$|^id", str(s.name).strip().lower()))
        sequential = (vals.max() - vals.min() + 1) <= 1.1 * len(vals)
        if is_int and len(vals) > 20 and vals.nunique() >= 0.95 * len(vals) and (looks_like_key or sequential):
            t = "identifier"
        return {"type": t, "stored_as_text": False, "parse_rate": 1.0}

    # text column: what does it *look* like?
    lowered = vals.astype(str).str.strip().str.lower()
    if lowered.isin(_BOOL_TOKENS).mean() >= 0.95 and lowered.nunique() <= 4 and lowered.nunique() >= 2:
        return {"type": "boolean", "stored_as_text": True, "parse_rate": 1.0}
    _, ok = _numeric_parse(vals)
    if ok.mean() >= 0.8:
        parsed = vals[ok].map(_clean_number)
        t = "integer" if bool((parsed % 1 == 0).all()) else "float"
        return {"type": t, "stored_as_text": True, "parse_rate": float(ok.mean())}
    if _date_like_share(vals) >= 0.6:
        _, dok = _date_parse(vals)
        if dok.mean() >= 0.8:
            return {"type": "datetime", "stored_as_text": True, "parse_rate": float(dok.mean())}
    unique = vals.nunique()
    if unique <= max(20, 0.05 * n) and unique / max(len(vals), 1) < 0.5:
        return {"type": "categorical", "stored_as_text": False, "parse_rate": 1.0}
    if unique == len(vals) and len(vals) > 20 and vals.astype(str).str.len().max() < 40:
        return {"type": "identifier", "stored_as_text": False, "parse_rate": 1.0}
    return {"type": "text", "stored_as_text": False, "parse_rate": 1.0}


# --------------------------------------------------------------------------- #
# per-column profile
# --------------------------------------------------------------------------- #

def _histogram(values: pd.Series, bins: int = 20):
    values = values.dropna().astype(float)
    if len(values) == 0:
        return None
    lo, hi = float(values.min()), float(values.max())
    if lo == hi:
        return {"edges": [lo - 0.5, hi + 0.5], "counts": [int(len(values))]}
    counts, edges = np.histogram(values, bins=min(bins, max(5, int(np.sqrt(len(values))))), range=(lo, hi))
    return {"edges": [float(e) for e in edges], "counts": [int(c) for c in counts]}


def profile_column(s: pd.Series) -> dict:
    n = len(s)
    placeholders = int(_placeholder_mask(s).sum())
    nulls = int(s.isna().sum())
    inferred = infer_type(s)
    real = _real_values(s)
    out = {
        "name": str(s.name),
        "dtype": str(s.dtype),
        "inferred_type": inferred["type"],
        "stored_as_text": inferred["stored_as_text"],
        "count": int(n),
        "missing": nulls,
        "placeholders": placeholders,
        "missing_effective": nulls + placeholders,
        "missing_pct": round(100 * (nulls + placeholders) / n, 2) if n else 0.0,
        "unique": int(real.nunique()),
        "samples": [cell_label(v) for v in real.head(5).tolist()],
    }
    numeric = None
    if pd.api.types.is_numeric_dtype(s.dtype) and not pd.api.types.is_bool_dtype(s.dtype):
        numeric = s.dropna().astype(float)
    elif inferred["stored_as_text"] and inferred["type"] in ("integer", "float"):
        numeric = real.map(_clean_number).dropna().astype(float)
    if numeric is not None and len(numeric):
        out["stats"] = {
            "min": jsonable(numeric.min()), "max": jsonable(numeric.max()),
            "mean": jsonable(numeric.mean()), "median": jsonable(numeric.median()),
            "std": jsonable(numeric.std()),
        }
        out["histogram"] = _histogram(numeric)
    if pd.api.types.is_datetime64_any_dtype(s.dtype) and s.notna().any():
        out["stats"] = {"min": cell_label(s.min()), "max": cell_label(s.max())}
    if numeric is None and len(real):
        top = real.astype(str).value_counts().head(8)
        out["top_values"] = [{"value": k, "count": int(v)} for k, v in top.items()]
    return out


def profile_dataframe(df: pd.DataFrame) -> dict:
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "column_profiles": [profile_column(df[c]) for c in df.columns],
    }


# --------------------------------------------------------------------------- #
# category variants
# --------------------------------------------------------------------------- #

def _norm_key(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", v.lower())


def find_category_variants(values: pd.Series) -> dict[str, str]:
    """Group spellings that probably mean the same thing. Returns {variant: canonical}."""
    counts = values.astype(str).str.strip().value_counts()
    # exact-ish match on normalised key (case, spaces, punctuation)
    groups: dict[str, list[str]] = {}
    for v in counts.index:
        groups.setdefault(_norm_key(v), []).append(v)
    keys = list(groups)
    parent = {k: k for k in keys}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    # fuzzy merge for typos ("Chenai" ~ "Chennai"); never merge keys that contain digits
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if len(a) < 4 or len(b) < 4 or abs(len(a) - len(b)) > 2:
                continue
            if re.search(r"\d", a) or re.search(r"\d", b):
                continue
            if SequenceMatcher(None, a, b).ratio() >= 0.88:
                parent[find(a)] = find(b)
    merged: dict[str, list[str]] = {}
    for k in keys:
        merged.setdefault(find(k), []).extend(groups[k])
    mapping = {}
    for members in merged.values():
        if len(members) < 2:
            continue
        canonical = max(members, key=lambda m: (counts[m], -len(m), m))
        for m in members:
            if m != canonical:
                mapping[m] = canonical
    return mapping


# --------------------------------------------------------------------------- #
# issue detection
# --------------------------------------------------------------------------- #

def _issue(type_, column, severity, title, detail, affected, cells, dimension, examples, suggestion, alternatives=None):
    return {
        "id": f"{type_}:{column if column is not None else '*'}",
        "type": type_, "column": column, "severity": severity, "title": title, "detail": detail,
        "rows_affected": int(affected), "cells_affected": int(cells), "dimension": dimension,
        "examples": examples, "suggestion": suggestion, "alternatives": alternatives or [],
    }


def _sug(op, params, label, reason):
    return {"op": op, "params": params, "label": label, "reason": reason}


def detect_issues(df: pd.DataFrame) -> list[dict]:
    issues: list[dict] = []
    n = len(df)
    if n == 0:
        return issues

    # whole-frame: duplicate rows
    dup = int(df.duplicated().sum())
    if dup:
        issues.append(_issue(
            "duplicates", None, "high", "Duplicate rows",
            f"{dup} row{'s' if dup != 1 else ''} repeat an earlier row exactly ({100 * dup / n:.1f}% of the data).",
            dup, dup * df.shape[1], "uniqueness",
            [cell_label(v) for v in df[df.duplicated()].head(3).iloc[:, 0].tolist()],
            _sug("drop_duplicates", {"keep": "first"}, "Remove duplicates, keep first",
                 f"{dup} rows were exact copies of an earlier row."),
        ))

    # column names
    bad_names = [c for c in df.columns if str(c) != re.sub(r"[^0-9a-z_]+", "_", str(c).strip().lower()).strip("_")]
    if bad_names:
        issues.append(_issue(
            "column_names", None, "low", "Column names are hard to code against",
            f"{len(bad_names)} name{'s' if len(bad_names) != 1 else ''} contain spaces, capitals or symbols: "
            + ", ".join(f"'{c}'" for c in bad_names[:4]) + ("…" if len(bad_names) > 4 else "") + ".",
            0, 0, "consistency", [str(c) for c in bad_names[:4]],
            _sug("snake_case_columns", {}, "Rename to snake_case",
                 "Names with spaces or capitals are awkward in code and SQL."),
        ))

    for col in df.columns:
        s = df[col]
        placeholder = _placeholder_mask(s)
        real = _real_values(s)
        inferred = infer_type(s)
        t = inferred["type"]

        if int(placeholder.sum()):
            k = int(placeholder.sum())
            toks = sorted({str(v).strip() for v in s[placeholder].unique()})[:5]
            issues.append(_issue(
                "missing_tokens", col, "high", f"Placeholder text used for missing values in '{col}'",
                f"{k} cell{'s' if k != 1 else ''} contain " + ", ".join(f"'{x}'" for x in toks)
                + " instead of a real empty value, so tools count them as data.",
                k, k, "completeness", toks,
                _sug("standardize_missing", {"columns": [col]}, "Convert to missing",
                     f"{k} cells in '{col}' held placeholder text such as {', '.join(repr(x) for x in toks[:3])}."),
            ))

        if t == "empty":
            issues.append(_issue(
                "constant_column", col, "medium", f"'{col}' is empty", "Every value is missing.",
                n, n, "completeness", [],
                _sug("drop_column", {"column": col}, "Drop column", f"'{col}' has no values at all.")))
            continue

        # missing values (real NaN)
        nulls = int(s.isna().sum())
        if nulls:
            pct = 100 * nulls / n
            numeric_dtype = pd.api.types.is_numeric_dtype(s.dtype) and not pd.api.types.is_bool_dtype(s.dtype)
            if t in ("integer", "float") or numeric_dtype:
                primary = _sug("fill_missing", {"column": col, "strategy": "median"}, "Fill with median",
                               f"{nulls} values were missing in '{col}'; the median is robust to outliers.")
            elif t == "datetime":
                primary = _sug("drop_missing_rows", {"columns": [col]}, "Drop those rows",
                               f"Dates can't be guessed; {nulls} rows had no '{col}'.")
            else:
                primary = _sug("fill_missing", {"column": col, "strategy": "constant", "value": "Unknown"},
                               "Fill with 'Unknown'", f"{nulls} values were missing in '{col}'.")
            alts = [_sug("drop_missing_rows", {"columns": [col]}, "Drop rows instead",
                         f"Remove the {nulls} rows with no '{col}'.")]
            if t in ("integer", "float") or numeric_dtype:
                alts.insert(0, _sug("fill_missing", {"column": col, "strategy": "mean"}, "Fill with mean",
                                    f"Replace {nulls} missing values with the average."))
            if t in ("categorical", "boolean"):
                alts.insert(0, _sug("fill_missing", {"column": col, "strategy": "mode"}, "Fill with most common",
                                    f"Replace {nulls} missing values with the most frequent value."))
            if pct >= 60:
                alts.insert(0, _sug("drop_column", {"column": col}, "Drop column",
                                    f"'{col}' is {pct:.0f}% empty, so it carries little information."))
            issues.append(_issue(
                "missing_values", col, "high" if pct >= 20 else "medium" if pct >= 5 else "low",
                f"Missing values in '{col}'",
                f"{nulls} of {n} values are empty ({pct:.1f}%).", nulls, nulls, "completeness",
                [], primary, alts))

        if len(real) == 0:
            continue

        # constant column
        if real.nunique() == 1 and len(real) == len(s) and n > 1 and t != "boolean":
            issues.append(_issue(
                "constant_column", col, "low", f"'{col}' never changes",
                f"Every row has the value '{cell_label(real.iloc[0])}'.", 0, 0, "consistency", [],
                _sug("drop_column", {"column": col}, "Drop column", f"'{col}' holds a single value, which adds nothing to analysis.")))

        if is_text(s):
            # whitespace
            sv = real.astype(str)
            ws_mask = (sv != sv.str.strip()) | sv.str.contains(r"\s{2,}", regex=True)
            ws = int(ws_mask.sum())
            if ws:
                ex = [repr(v) for v in sv[ws_mask].head(3).tolist()]
                issues.append(_issue(
                    "whitespace", col, "medium", f"Stray spaces in '{col}'",
                    f"{ws} value{'s' if ws != 1 else ''} start or end with spaces or contain double spaces, "
                    "so 'Paris' and 'Paris ' count as different values.",
                    ws, ws, "consistency", ex,
                    _sug("trim_whitespace", {"columns": [col]}, "Trim whitespace",
                         f"{ws} values in '{col}' had extra spaces.")))

            # numbers / dates stored as text
            if inferred["stored_as_text"] and t in ("integer", "float"):
                _, ok = _numeric_parse(real)
                bad = real[~ok]
                clean_target = "whole numbers" if t == "integer" else "decimals"
                issues.append(_issue(
                    "numeric_as_text", col, "high", f"'{col}' holds numbers stored as text",
                    f"{int(ok.sum())} values look like {clean_target}"
                    + (f" and {len(bad)} cannot be read as a number ({', '.join(repr(x) for x in bad.head(3))})" if len(bad) else "")
                    + ". Sorting, averages and charts won't work until converted.",
                    int(len(real)), int(len(real)), "validity",
                    [cell_label(v) for v in real.head(3)],
                    _sug("convert_numeric", {"column": col}, "Convert to numbers",
                         f"'{col}' was text but {100 * ok.mean():.0f}% of its values are numbers"
                         + (f"; {len(bad)} invalid value(s) become missing." if len(bad) else "."))))
            elif inferred["stored_as_text"] and t == "datetime":
                parsed, ok = _date_parse(real)
                bad = real[~ok]
                issues.append(_issue(
                    "dates_as_text", col, "high" if len(bad) else "medium",
                    f"'{col}' holds dates stored as text" + (" and some are invalid" if len(bad) else ""),
                    f"{int(ok.sum())} values parse as dates"
                    + (f"; {len(bad)} do not ({', '.join(repr(x) for x in bad.head(3))})" if len(bad) else "") + ".",
                    int(len(real)), int(len(real)), "validity",
                    [cell_label(v) for v in real.head(3)],
                    _sug("parse_dates", {"column": col}, "Parse as dates",
                         f"'{col}' was text, but {100 * ok.mean():.0f}% of values are recognisable dates"
                         + (f"; {len(bad)} invalid date(s) become missing." if len(bad) else ".")),
                    [_sug("parse_dates", {"column": col, "dayfirst": True}, "Parse day-first",
                          "Treat 03/04/2024 as 3 April rather than March 4.")]))

            # inconsistent categories
            if t in ("categorical", "boolean") and real.nunique() <= 60:
                mapping = find_category_variants(real)
                if mapping:
                    stripped = real.astype(str).str.strip()
                    affected = int(stripped.isin(mapping.keys()).sum())
                    groups: dict[str, list[str]] = {}
                    for v, c in mapping.items():
                        groups.setdefault(c, []).append(v)
                    ex = [f"{', '.join(v)} → {c}" for c, v in list(groups.items())[:3]]
                    issues.append(_issue(
                        "inconsistent_categories", col, "high" if affected / n > 0.05 else "medium",
                        f"Inconsistent spellings in '{col}'",
                        f"{len(mapping)} variant{'s' if len(mapping) != 1 else ''} of {len(groups)} value"
                        f"{'s' if len(groups) != 1 else ''} differ by case, punctuation or typos "
                        f"({affected} cells), so groupings and counts are split.",
                        affected, affected, "consistency", ex,
                        _sug("map_values", {"column": col, "mapping": mapping}, "Merge variants",
                             f"Merged {len(mapping)} spelling variants into their most common form in '{col}'.")))

        # numeric outliers
        numeric = None
        if pd.api.types.is_numeric_dtype(s.dtype) and not pd.api.types.is_bool_dtype(s.dtype) and t != "identifier":
            numeric = s.dropna().astype(float)
        if numeric is not None and len(numeric) >= 8 and numeric.nunique() > 5:
            q1, q3 = numeric.quantile([0.25, 0.75])
            spread = q3 - q1
            if spread > 0:
                low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
                # small tolerance so values already clipped to a bound don't re-trigger the issue
                tol = 0.1 * spread
                out_mask = (numeric < low - tol) | (numeric > high + tol)
                k = int(out_mask.sum())
                if k:
                    z = np.abs(stats.zscore(numeric, ddof=0))
                    z_k = int((z > 3).sum())
                    ex = [cell_label(v) for v in numeric[out_mask].sort_values(key=lambda x: -abs(x - numeric.median())).head(3)]
                    issues.append(_issue(
                        "outliers", col, "medium" if k / len(numeric) < 0.05 else "low",
                        f"Outliers in '{col}'",
                        f"{k} value{'s' if k != 1 else ''} fall outside {cell_label(low)} to {cell_label(high)} "
                        f"(1.5 × IQR); {z_k} also exceed 3 standard deviations. Check whether they are errors or real.",
                        k, k, "plausibility", ex,
                        _sug("handle_outliers", {"column": col, "method": "iqr", "threshold": 1.5, "action": "clip"},
                             "Clip to IQR bounds",
                             f"{k} values in '{col}' were beyond 1.5 × IQR; clipping keeps the rows but limits their influence."),
                        [_sug("handle_outliers", {"column": col, "method": "iqr", "threshold": 1.5, "action": "null"},
                              "Blank them out", f"Mark the {k} outliers as missing so they can be filled separately."),
                         _sug("handle_outliers", {"column": col, "method": "iqr", "threshold": 1.5, "action": "remove"},
                              "Remove those rows", f"Drop the {k} rows whose '{col}' is an outlier.")]))

    # multivariate anomalies
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
                and infer_type(df[c])["type"] in ("integer", "float")]
    if len(num_cols) >= 2 and n >= 30:
        from sklearn.ensemble import IsolationForest
        X = df[num_cols].astype("float64")
        X = X.fillna(X.median()).fillna(0.0)
        labels = IsolationForest(contamination=0.02, random_state=0).fit_predict(X.to_numpy())
        k = int((labels == -1).sum())
        if k:
            issues.append(_issue(
                "anomalous_rows", None, "info", "Rows that are unusual across several columns",
                f"An Isolation Forest flags {k} rows ({100 * k / n:.1f}%) whose combination of "
                f"{', '.join(num_cols[:3])}{'…' if len(num_cols) > 3 else ''} is rare. Review before dropping.",
                k, 0, "plausibility", [],
                _sug("drop_anomalous_rows", {"contamination": 0.02}, "Drop flagged rows",
                     f"Isolation Forest flagged {k} rows as multivariate anomalies.")))

    issues.sort(key=lambda i: (SEVERITY_ORDER[i["severity"]], -i["cells_affected"]))
    return issues


# --------------------------------------------------------------------------- #
# quality score
# --------------------------------------------------------------------------- #

DIMENSIONS = ["completeness", "uniqueness", "validity", "consistency", "plausibility"]


def quality_report(df: pd.DataFrame, issues: list[dict] | None = None) -> dict:
    issues = detect_issues(df) if issues is None else issues
    rows, cols = df.shape
    cells = max(rows * cols, 1)
    totals = {d: 0 for d in DIMENSIONS}
    denominators = {
        "completeness": cells, "uniqueness": cells, "validity": cells,
        "consistency": cells, "plausibility": cells,
    }
    for i in issues:
        if i["type"] == "missing_values":
            totals["completeness"] += i["cells_affected"]
        else:
            totals[i["dimension"]] += i["cells_affected"]
    scores = {d: round(100 * max(0.0, 1 - totals[d] / denominators[d]), 1) for d in DIMENSIONS}
    # An issue that exists should never round to a perfect 100 for its dimension
    for i in issues:
        if scores[i["dimension"]] >= 100 and i["cells_affected"] > 0:
            scores[i["dimension"]] = 99.9
    overall = round(sum(scores.values()) / len(scores) - min(5.0, 0.5 * len(issues)), 1)
    return {
        "overall": max(0.0, min(100.0, overall)),
        "dimensions": scores,
        "issue_count": len(issues),
        "rows": int(rows), "columns": int(cols),
        "missing_cells": int(sum(profile_column(df[c])["missing_effective"] for c in df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
    }
