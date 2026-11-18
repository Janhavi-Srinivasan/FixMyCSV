from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd


def jsonable(v):
    """Convert pandas/numpy scalars to plain JSON-safe values."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    return str(v)


def is_text(s: pd.Series) -> bool:
    return s.dtype == object or isinstance(s.dtype, pd.StringDtype)


def cell_label(v) -> str | None:
    """Display value for a cell; None means missing."""
    if v is None or v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat(sep=" ")
    if isinstance(v, (np.floating, float)):
        return format(float(v), "g") if abs(v) < 1e15 else str(v)
    return str(v)
