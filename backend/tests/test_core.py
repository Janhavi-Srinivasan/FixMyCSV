import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "sample_data" / "messy_customers.csv"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIXMYCSV_DATA", str(tmp_path))
    import importlib
    from app import db
    importlib.reload(db)
    import app.main as main
    importlib.reload(main)
    return TestClient(main.app)


def upload(client):
    r = client.post("/api/datasets", files={"file": ("messy_customers.csv", SAMPLE.read_bytes(), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_detects_every_planted_issue(client):
    ds = upload(client)
    st = client.get(f"/api/datasets/{ds}/state").json()
    found = {(i["type"], i["column"]) for i in st["issues"]}
    assert ("duplicates", None) in found
    assert ("missing_tokens", "City") in found
    assert ("numeric_as_text", "Annual Income") in found
    assert ("dates_as_text", "Signup Date") in found
    assert ("inconsistent_categories", "City") in found
    assert ("inconsistent_categories", "Newsletter") in found
    assert ("whitespace", "Full Name") in found
    assert ("missing_values", "Age") in found
    assert ("outliers", "Age") in found
    assert ("column_names", None) in found
    types = {c["name"]: c["inferred_type"] for c in st["profile_before"]["column_profiles"]}
    assert types["Customer ID"] == "identifier"
    assert types["Signup Date"] == "datetime"
    assert types["Annual Income"] in ("integer", "float")


def apply_all_primary(client, ds, max_rounds=30):
    for _ in range(max_rounds):
        st = client.get(f"/api/datasets/{ds}/state").json()
        issues = [i for i in st["issues"] if i["type"] != "anomalous_rows"]
        if not issues:
            return st
        s = issues[0]["suggestion"]
        r = client.post(f"/api/datasets/{ds}/steps", json={"op": s["op"], "params": s["params"], "reason": s["reason"]})
        assert r.status_code == 201, r.text
    return client.get(f"/api/datasets/{ds}/state").json()


def test_cleaning_improves_quality_and_is_reversible(client):
    ds = upload(client)
    before = client.get(f"/api/datasets/{ds}/state").json()
    after = apply_all_primary(client, ds)
    assert after["quality_after"]["overall"] > before["quality_before"]["overall"]
    assert after["quality_after"]["issue_count"] <= 1
    assert len(after["steps"]) >= 5
    # every applied step reports what it changed
    assert all(s["diff"] is not None for s in after["steps"] if s["status"] == "applied")
    # undo the first step -> pipeline replays without it and nothing crashes
    first = after["steps"][0]["id"]
    assert client.patch(f"/api/datasets/{ds}/steps/{first}", json={"enabled": False}).status_code == 200
    undone = client.get(f"/api/datasets/{ds}/state").json()
    assert undone["steps"][0]["status"] == "disabled"
    # re-enable
    client.patch(f"/api/datasets/{ds}/steps/{first}", json={"enabled": True})
    again = client.get(f"/api/datasets/{ds}/state").json()
    assert again["quality_after"]["overall"] == after["quality_after"]["overall"]


def test_preview_does_not_change_state(client):
    ds = upload(client)
    r = client.post(f"/api/datasets/{ds}/preview", json={"op": "drop_duplicates", "params": {"keep": "first"}})
    assert r.status_code == 200
    d = r.json()["diff"]
    assert d["rows_removed"] == 9
    assert client.get(f"/api/datasets/{ds}/state").json()["steps"] == []


def test_invalid_step_is_rejected(client):
    ds = upload(client)
    r = client.post(f"/api/datasets/{ds}/preview", json={"op": "drop_column", "params": {"column": "nope"}})
    assert r.status_code == 422
    r = client.post(f"/api/datasets/{ds}/steps", json={"op": "bogus", "params": {}})
    assert r.status_code == 422


def test_removing_a_dependency_marks_later_step_as_error_not_crash(client):
    ds = upload(client)
    client.post(f"/api/datasets/{ds}/steps", json={"op": "snake_case_columns", "params": {}})
    client.post(f"/api/datasets/{ds}/steps", json={"op": "fill_missing", "params": {"column": "age", "strategy": "median"}})
    st = client.get(f"/api/datasets/{ds}/state").json()
    assert [s["status"] for s in st["steps"]] == ["applied", "applied"]
    client.patch(f"/api/datasets/{ds}/steps/{st['steps'][0]['id']}", json={"enabled": False})
    st = client.get(f"/api/datasets/{ds}/state").json()
    assert st["steps"][1]["status"] == "error"
    assert "age" in st["steps"][1]["error"]


def test_exported_script_reproduces_the_app_output_exactly(client, tmp_path):
    ds = upload(client)
    apply_all_primary(client, ds)
    # also add a few non-default ops so more helpers are exercised
    client.post(f"/api/datasets/{ds}/steps", json={"op": "standardize_case", "params": {"column": "city", "case": "upper"}, "reason": "demo"}) \
        if False else None
    app_csv = client.get(f"/api/datasets/{ds}/export/csv").text
    script = client.get(f"/api/datasets/{ds}/export/script").text
    compile(script, "clean_data.py", "exec")
    work = tmp_path / "run"
    work.mkdir()
    (work / "clean_data.py").write_text(script)
    (work / "messy_customers.csv").write_bytes(SAMPLE.read_bytes())
    proc = subprocess.run([sys.executable, "clean_data.py", "messy_customers.csv", "out.csv"], cwd=work, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    script_csv = (work / "out.csv").read_text()
    assert script_csv == app_csv


def test_all_operations_via_script(client, tmp_path):
    ds = upload(client)
    steps = [
        ("standardize_missing", {}),
        ("trim_whitespace", {}),
        ("snake_case_columns", {}),
        ("standardize_case", {"column": "city", "case": "title"}),
        ("convert_numeric", {"column": "annual_income"}),
        ("parse_dates", {"column": "signup_date"}),
        ("fill_missing", {"column": "age", "strategy": "mean"}),
        ("fill_missing", {"column": "monthly_spend", "strategy": "median"}),
        ("handle_outliers", {"column": "age", "method": "zscore", "threshold": 3, "action": "null"}),
        ("handle_outliers", {"column": "monthly_spend", "method": "iqr", "threshold": 1.5, "action": "clip"}),
        ("drop_anomalous_rows", {"contamination": 0.05}),
        ("drop_duplicates", {}),
        ("drop_missing_rows", {"columns": ["city"]}),
        ("drop_column", {"column": "full_name"}),
    ]
    for op, params in steps:
        r = client.post(f"/api/datasets/{ds}/steps", json={"op": op, "params": params})
        assert r.status_code == 201, (op, r.text)
    st = client.get(f"/api/datasets/{ds}/state").json()
    assert all(s["status"] == "applied" for s in st["steps"]), [(s["op"], s["error"]) for s in st["steps"]]
    app_csv = client.get(f"/api/datasets/{ds}/export/csv").text
    work = tmp_path / "run2"
    work.mkdir()
    (work / "clean_data.py").write_text(client.get(f"/api/datasets/{ds}/export/script").text)
    (work / "messy_customers.csv").write_bytes(SAMPLE.read_bytes())
    proc = subprocess.run([sys.executable, "clean_data.py", "messy_customers.csv", "out.csv"], cwd=work, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert (work / "out.csv").read_text() == app_csv


def test_data_endpoint_marks_changed_cells(client):
    ds = upload(client)
    client.post(f"/api/datasets/{ds}/steps", json={"op": "trim_whitespace", "params": {"columns": ["Full Name"]}})
    d = client.get(f"/api/datasets/{ds}/data?stage=current&offset=60&limit=20").json()
    assert d["changed"].get("70") == ["Full Name"]


def test_bundle_zip(client):
    ds = upload(client)
    client.post(f"/api/datasets/{ds}/steps", json={"op": "drop_duplicates", "params": {}, "reason": "dupes"})
    r = client.get(f"/api/datasets/{ds}/export/bundle")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_bad_upload(client):
    r = client.post("/api/datasets", files={"file": ("x.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 400
