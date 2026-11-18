"""Replay a dataset's steps from the untouched original, recording what each one did."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import db
from .diffing import compare
from .transforms import OPERATIONS, apply_operation

MAX_ROWS = 500_000


def load_original(ds: dict) -> pd.DataFrame:
    path = Path(ds["file_path"])
    if ds["kind"] == "excel":
        return pd.read_excel(path, sheet_name=ds["sheet"] or 0)
    return pd.read_csv(path)


def read_upload(filename: str, raw: bytes, sheet: str | None = None):
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(raw), sheet_name=sheet or 0)
        return df, "excel"
    if name.endswith((".csv", ".tsv", ".txt")):
        sep = "\t" if name.endswith(".tsv") else None
        for enc in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(raw), sep=sep, engine="python" if sep is None else "c", encoding=enc)
                return df, "csv"
            except UnicodeDecodeError:
                continue
    raise ValueError("Unsupported file type. Upload a .csv, .tsv or .xlsx file.")


@dataclass
class StepResult:
    step: dict
    status: str                      # applied | disabled | error
    error: str | None = None
    diff: dict | None = None


@dataclass
class Replay:
    original: pd.DataFrame
    current: pd.DataFrame
    results: list[StepResult] = field(default_factory=list)

    @property
    def effective_steps(self) -> list[dict]:
        return [r.step for r in self.results if r.status == "applied"]


def replay(ds: dict, original: pd.DataFrame, steps: list[dict] | None = None, with_diffs: bool = True) -> Replay:
    steps = db.list_steps(ds["id"]) if steps is None else steps
    df = original
    out = Replay(original=original, current=original)
    for st in steps:
        if not st["enabled"]:
            out.results.append(StepResult(st, "disabled"))
            continue
        try:
            nxt = apply_operation(df, st["op"], st["params"])
        except Exception as e:  # a step can break if an earlier step it depended on was undone
            out.results.append(StepResult(st, "error", error=_friendly(e)))
            continue
        diff = compare(df, nxt, _focus(st["params"])) if with_diffs else None
        out.results.append(StepResult(st, "applied", diff=diff))
        df = nxt
    out.current = df
    return out


def preview(df: pd.DataFrame, op: str, params: dict):
    nxt = apply_operation(df, op, params)
    return nxt, compare(df, nxt, _focus(params))


def _focus(params):
    cols = []
    if params.get("column"):
        cols.append(params["column"])
    cols += params.get("columns") or []
    return cols


def _friendly(e: Exception) -> str:
    if isinstance(e, KeyError):
        return f"Column {e} is not available at this point in the pipeline."
    return str(e)


def operation_catalog():
    return [{"op": k, "label": v["label"], "description": v["description"], "params": v["params"]}
            for k, v in OPERATIONS.items()]
