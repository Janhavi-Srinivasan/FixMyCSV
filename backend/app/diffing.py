"""Before/after comparison of two DataFrames that share an index."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import cell_label, is_text, jsonable
from .profiling import _histogram

MAX_SAMPLES = 12


def _changed_mask(before: pd.Series, after: pd.Series) -> pd.Series:
    """True where a cell differs. Missing == missing; 1 == 1.0; tolerant of dtype changes."""
    b_na, a_na = before.isna(), after.isna()
    both_num = pd.api.types.is_numeric_dtype(before.dtype) and pd.api.types.is_numeric_dtype(after.dtype) \
        and not pd.api.types.is_bool_dtype(before.dtype)
    if both_num:
        bf = before.astype("float64")
        af = after.astype("float64")
        same = np.isclose(bf.fillna(0).to_numpy(), af.fillna(0).to_numpy(), rtol=1e-9, atol=1e-12)
        same = pd.Series(same, index=before.index)
    else:
        same = before.map(cell_label).fillna("\0").eq(after.map(cell_label).fillna("\0"))
    return ~((b_na & a_na) | (same & ~b_na & ~a_na))


def compare(before: pd.DataFrame, after: pd.DataFrame, focus_columns: list[str] | None = None) -> dict:
    removed_idx = before.index.difference(after.index)
    kept_idx = before.index.intersection(after.index)
    added_cols = [c for c in after.columns if c not in before.columns]
    dropped_cols = [c for c in before.columns if c not in after.columns]
    renamed = None
    if added_cols and dropped_cols and len(added_cols) == len(dropped_cols) and len(before.columns) == len(after.columns):
        # a pure rename keeps column positions
        renamed = {b: a for b, a in zip(before.columns, after.columns) if b != a}
        if len(renamed) != len(added_cols):
            renamed = None

    common = [c for c in before.columns if c in after.columns]
    pairs = [(c, c) for c in common]
    if renamed:
        pairs = [(b, a) for b, a in zip(before.columns, after.columns)]
        added_cols, dropped_cols = [], []

    per_column, samples, changed_total = [], [], 0
    for b_col, a_col in pairs:
        b = before.loc[kept_idx, b_col]
        a = after.loc[kept_idx, a_col]
        mask = _changed_mask(b, a)
        k = int(mask.sum())
        dtype_changed = str(before[b_col].dtype) != str(after[a_col].dtype)
        if k or dtype_changed or b_col != a_col:
            per_column.append({
                "column": a_col, "was": b_col if b_col != a_col else None, "cells_changed": k,
                "dtype_before": str(before[b_col].dtype), "dtype_after": str(after[a_col].dtype) if dtype_changed else None,
            })
        changed_total += k
        if k and len(samples) < MAX_SAMPLES * 3:
            for idx in b[mask].index[:MAX_SAMPLES]:
                samples.append({"row": jsonable(idx), "column": a_col, "before": cell_label(b[idx]), "after": cell_label(a[idx])})
    per_column.sort(key=lambda d: -d["cells_changed"])

    # spread samples across columns so one noisy column doesn't hide others
    by_col: dict[str, list] = {}
    for smp in samples:
        by_col.setdefault(smp["column"], []).append(smp)
    balanced: list = []
    while len(balanced) < MAX_SAMPLES and any(by_col.values()):
        for col in list(by_col):
            if by_col[col] and len(balanced) < MAX_SAMPLES:
                balanced.append(by_col[col].pop(0))

    removed_rows = []
    for idx in removed_idx[:8]:
        removed_rows.append({"row": jsonable(idx), "values": {c: cell_label(before.loc[idx, c]) for c in list(before.columns)[:6]}})

    result = {
        "shape_before": [int(before.shape[0]), int(before.shape[1])],
        "shape_after": [int(after.shape[0]), int(after.shape[1])],
        "rows_removed": int(len(removed_idx)),
        "removed_sample": removed_rows,
        "cells_changed": changed_total,
        "columns_added": added_cols,
        "columns_dropped": dropped_cols,
        "columns_renamed": renamed,
        "per_column": per_column[:12],
        "samples": balanced,
        "missing_before": int(before.isna().sum().sum()),
        "missing_after": int(after.isna().sum().sum()),
        "distribution": None,
        "no_effect": not (len(removed_idx) or changed_total or added_cols or dropped_cols or renamed
                          or any(p["dtype_after"] for p in per_column)),
    }

    # distribution before/after for the most affected column (or a requested one)
    focus = None
    if focus_columns:
        focus = next((c for c in focus_columns if c in after.columns and c in before.columns), None)
    if focus is None and per_column:
        focus = next((p["column"] for p in per_column if p["column"] in before.columns and p["column"] in after.columns), None)
    if focus:
        result["distribution"] = _distribution(before[focus], after[focus], focus)
    return result


def _distribution(b: pd.Series, a: pd.Series, name: str) -> dict | None:
    def as_num(s):
        if pd.api.types.is_numeric_dtype(s.dtype) and not pd.api.types.is_bool_dtype(s.dtype):
            return s.dropna().astype(float)
        return None

    bn, an = as_num(b), as_num(a)
    if bn is not None and an is not None and len(bn) and len(an):
        lo, hi = float(min(bn.min(), an.min())), float(max(bn.max(), an.max()))
        if lo == hi:
            hi = lo + 1
        edges = np.linspace(lo, hi, 21)
        bc, _ = np.histogram(bn, bins=edges)
        ac, _ = np.histogram(an, bins=edges)
        return {"column": name, "kind": "numeric", "edges": [float(e) for e in edges],
                "before": [int(x) for x in bc], "after": [int(x) for x in ac]}
    if pd.api.types.is_datetime64_any_dtype(b.dtype) or pd.api.types.is_datetime64_any_dtype(a.dtype):
        return {"column": name, "kind": "missing",
                "before": {"Missing": int(b.isna().sum()), "Present": int(b.notna().sum())},
                "after": {"Missing": int(a.isna().sum()), "Present": int(a.notna().sum())}}
    if is_text(b) or is_text(a):
        bv = b.dropna().astype(str).value_counts()
        av = a.dropna().astype(str).value_counts()
        top = list(dict.fromkeys(list(bv.head(12).index) + list(av.head(12).index)))[:14]
        return {"column": name, "kind": "categorical", "labels": top,
                "before": [int(bv.get(k, 0)) for k in top], "after": [int(av.get(k, 0)) for k in top],
                "missing_before": int(b.isna().sum()), "missing_after": int(a.isna().sum())}
    return None
