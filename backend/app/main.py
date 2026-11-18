from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, export
from .diffing import compare
from .pipeline import MAX_ROWS, load_original, operation_catalog, preview, read_upload, replay
from .profiling import detect_issues, profile_dataframe, quality_report
from .transforms import OPERATIONS
from .utils import cell_label, jsonable

app = FastAPI(title="FixMyCSV", version="1.0.0")
db.init()

_cache: dict[str, tuple[str, object]] = {}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _dataset(ds_id: str) -> dict:
    ds = db.get_dataset(ds_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return ds


def _original(ds: dict) -> pd.DataFrame:
    hit = _cache.get("orig:" + ds["id"])
    if hit is None:
        df = load_original(ds)
        _cache["orig:" + ds["id"]] = ("", df)
        return df
    return hit[1]


def _state_key(ds_id: str, steps: list[dict]) -> str:
    sig = json.dumps([(s["id"], s["op"], s["params"], s["enabled"]) for s in steps], sort_keys=True, default=str)
    return hashlib.sha1(sig.encode()).hexdigest()


def _replayed(ds: dict):
    steps = db.list_steps(ds["id"])
    key = _state_key(ds["id"], steps)
    hit = _cache.get("replay:" + ds["id"])
    if hit and hit[0] == key:
        return hit[1]
    original = _original(ds)
    result = replay(ds, original, steps)
    issues = detect_issues(result.current)
    bundle = {"replay": result, "issues": issues, "quality": quality_report(result.current, issues)}
    _cache["replay:" + ds["id"]] = (key, bundle)
    return bundle


def _original_quality(ds: dict) -> dict:
    hit = _cache.get("oq:" + ds["id"])
    if hit:
        return hit[1]
    original = _original(ds)
    issues = detect_issues(original)
    q = {"quality": quality_report(original, issues), "issues": issues}
    _cache["oq:" + ds["id"]] = ("", q)
    return q


def _forget(ds_id: str):
    for k in [k for k in _cache if k.endswith(":" + ds_id)]:
        _cache.pop(k, None)


def _step_json(r) -> dict:
    s = r.step
    return {"id": s["id"], "position": s["position"], "op": s["op"], "label": OPERATIONS[s["op"]]["label"],
            "params": s["params"], "reason": s["reason"], "enabled": s["enabled"],
            "status": r.status, "error": r.error, "diff": r.diff}


def _meta(ds: dict) -> dict:
    return {k: ds[k] for k in ("id", "name", "filename", "kind", "sheet", "rows", "cols", "created_at")}


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #

@app.get("/api/operations")
def operations():
    return operation_catalog()


@app.get("/api/datasets")
def list_datasets():
    return [_meta(d) for d in db.list_datasets()]


@app.post("/api/datasets")
async def upload(file: UploadFile = File(...), sheet: str | None = Query(None)):
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "File is larger than 50 MB.")
    try:
        df, kind = read_upload(file.filename or "data.csv", raw, sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Could not read this file: {e}")
    if df.empty or df.shape[1] == 0:
        raise HTTPException(400, "The file has no rows or no columns.")
    if len(df) > MAX_ROWS:
        raise HTTPException(413, f"Files with more than {MAX_ROWS:,} rows are not supported.")
    ds_id = uuid.uuid4().hex[:10]
    suffix = Path(file.filename or "data.csv").suffix.lower() or ".csv"
    path = db.UPLOAD_DIR / f"{ds_id}{suffix}"
    path.write_bytes(raw)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(file.filename or "data").stem)
    db.add_dataset(ds_id, name, file.filename or "data.csv", path, kind, sheet, len(df), df.shape[1])
    # re-load from disk so every later read goes through exactly the same code path
    ds = db.get_dataset(ds_id)
    _cache["orig:" + ds_id] = ("", load_original(ds))
    return _meta(ds)


@app.delete("/api/datasets/{ds_id}", status_code=204)
def delete_dataset(ds_id: str):
    _dataset(ds_id)
    db.delete_dataset(ds_id)
    _forget(ds_id)


@app.get("/api/datasets/{ds_id}/state")
def state(ds_id: str):
    ds = _dataset(ds_id)
    bundle = _replayed(ds)
    orig = _original_quality(ds)
    r = bundle["replay"]
    return {
        "dataset": _meta(ds),
        "steps": [_step_json(x) for x in r.results],
        "issues": bundle["issues"],
        "quality_before": orig["quality"],
        "quality_after": bundle["quality"],
        "profile_before": profile_dataframe(r.original),
        "profile_after": profile_dataframe(r.current),
        "total_diff": compare(r.original, r.current),
    }


class Op(BaseModel):
    op: str
    params: dict = Field(default_factory=dict)
    reason: str = ""


@app.post("/api/datasets/{ds_id}/preview")
def preview_step(ds_id: str, body: Op):
    ds = _dataset(ds_id)
    current = _replayed(ds)["replay"].current
    try:
        nxt, diff = preview(current, body.op, body.params)
    except Exception as e:
        raise HTTPException(422, f"{type(e).__name__}: {e}" if not isinstance(e, (ValueError, KeyError)) else str(e))
    before_q = _replayed(ds)["quality"]
    after_issues = detect_issues(nxt)
    return {"diff": diff, "quality_before": before_q, "quality_after": quality_report(nxt, after_issues),
            "issues_after": len(after_issues)}


@app.post("/api/datasets/{ds_id}/steps", status_code=201)
def add_step(ds_id: str, body: Op):
    ds = _dataset(ds_id)
    current = _replayed(ds)["replay"].current
    try:
        preview(current, body.op, body.params)  # validate before saving
    except Exception as e:
        raise HTTPException(422, str(e))
    step_id = db.add_step(ds_id, body.op, body.params, body.reason)
    return {"id": step_id}


class Toggle(BaseModel):
    enabled: bool


@app.patch("/api/datasets/{ds_id}/steps/{step_id}")
def toggle_step(ds_id: str, step_id: int, body: Toggle):
    _dataset(ds_id)
    if not db.set_step_enabled(ds_id, step_id, body.enabled):
        raise HTTPException(404, "Step not found")
    return {"ok": True}


@app.delete("/api/datasets/{ds_id}/steps/{step_id}", status_code=204)
def remove_step(ds_id: str, step_id: int):
    _dataset(ds_id)
    if not db.delete_step(ds_id, step_id):
        raise HTTPException(404, "Step not found")


@app.get("/api/datasets/{ds_id}/data")
def data(ds_id: str, stage: str = "current", offset: int = 0, limit: int = Query(100, le=500)):
    ds = _dataset(ds_id)
    r = _replayed(ds)["replay"]
    df = r.current if stage == "current" else r.original
    page = df.iloc[offset: offset + limit]
    changed: dict[str, list[str]] = {}
    if stage == "current":
        # cells in this page that differ from the original
        from .diffing import _changed_mask
        common = [c for c in page.columns if c in r.original.columns]
        idx = page.index.intersection(r.original.index)
        for c in common:
            m = _changed_mask(r.original.loc[idx, c], page.loc[idx, c])
            for i in m[m].index:
                changed.setdefault(str(jsonable(i)), []).append(c)
    return {
        "columns": [str(c) for c in page.columns],
        "total": int(len(df)),
        "rows": [{"_row": jsonable(i), **{str(c): cell_label(v) for c, v in row.items()}} for i, row in page.iterrows()],
        "changed": changed,
    }


@app.get("/api/datasets/{ds_id}/export/{kind}")
def export_files(ds_id: str, kind: str):
    ds = _dataset(ds_id)
    bundle = _replayed(ds)
    r = bundle["replay"]
    csv_bytes = r.current.to_csv(index=False).encode("utf-8")
    script = export.build_script(ds, r.effective_steps)
    if kind == "csv":
        return Response(csv_bytes, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="cleaned_{ds["name"]}.csv"'})
    if kind == "script":
        return Response(script, media_type="text/x-python",
                        headers={"Content-Disposition": 'attachment; filename="clean_data.py"'})
    if kind == "bundle":
        report = export.build_changelog(ds, r.results, _original_quality(ds)["quality"], bundle["quality"])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"cleaned_{ds['name']}.csv", csv_bytes)
            z.writestr("clean_data.py", script)
            z.writestr("CHANGELOG.md", report)
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="fixmycsv_{ds["name"]}.zip"'})
    raise HTTPException(404, "Unknown export type")


@app.get("/api/datasets/{ds_id}/export-preview/script")
def script_preview(ds_id: str):
    ds = _dataset(ds_id)
    return {"script": export.build_script(ds, _replayed(ds)["replay"].effective_steps)}


# --- serve the built React app in production --------------------------------
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = _DIST / path
        return FileResponse(f if f.is_file() else _DIST / "index.html")
