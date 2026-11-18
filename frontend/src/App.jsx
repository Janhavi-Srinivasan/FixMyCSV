import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import Upload from "./components/Upload.jsx";
import IssuesPanel from "./components/IssuesPanel.jsx";
import PipelinePanel from "./components/PipelinePanel.jsx";
import DraftPanel from "./components/DraftPanel.jsx";
import ColumnsView from "./components/ColumnsView.jsx";
import DataTable from "./components/DataTable.jsx";
import ScriptView from "./components/ScriptView.jsx";
import QualityStrip from "./components/QualityStrip.jsx";

export default function App() {
  const [catalog, setCatalog] = useState([]);
  const [recent, setRecent] = useState([]);
  const [dsId, setDsId] = useState(() => localStorage.getItem("fixmycsv.ds"));
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState(null);
  const [tab, setTab] = useState("columns");
  const [error, setError] = useState(null);

  useEffect(() => { api.operations().then(setCatalog); api.datasets().then(setRecent).catch(() => {}); }, []);

  const refresh = useCallback(async (id = dsId) => {
    if (!id) return;
    try { setState(await api.state(id)); setError(null); }
    catch (e) { setError(e.message); localStorage.removeItem("fixmycsv.ds"); setDsId(null); setState(null); }
  }, [dsId]);

  useEffect(() => { if (dsId) { localStorage.setItem("fixmycsv.ds", dsId); refresh(dsId); } }, [dsId]);

  const columns = useMemo(() => state?.profile_after.column_profiles.map((c) => c.name) ?? [], [state]);
  const version = useMemo(() => (state ? state.steps.map((s) => `${s.id}${s.enabled}`).join(",") : ""), [state]);

  function suggest(s) {
    setDraft({ op: s.op, params: structuredClone(s.params), reason: s.reason, pool: s.params.mapping ? { ...s.params.mapping } : null });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function manual() {
    const first = catalog[0];
    setDraft({ op: first.op, params: {}, reason: "", pool: null, manual: true });
  }
  async function apply(d) {
    try {
      await api.addStep(dsId, d.op, d.params, d.reason);
      setDraft(null);
      await refresh();
    } catch (e) { setError(e.message); }
  }
  const mutate = (fn) => async (...a) => { try { await fn(...a); await refresh(); } catch (e) { setError(e.message); } };
  const toggle = mutate((s) => api.toggleStep(dsId, s.id, !s.enabled));
  const del = mutate((s) => api.deleteStep(dsId, s.id));

  if (!dsId || !state) {
    return (
      <>
        {error && <p className="error banner" role="alert">{error}</p>}
        <Upload recent={recent} onLoaded={(d) => { setDsId(d.id); setTab("columns"); }} onOpen={setDsId} />
      </>
    );
  }

  const ds = state.dataset;
  const d = state.total_diff;
  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <strong>FixMyCSV</strong>
          <span className="file">{ds.filename}</span>
          <span className="muted small">{d.shape_before[0]} × {d.shape_before[1]} → {d.shape_after[0]} × {d.shape_after[1]}</span>
        </div>
        <div className="exports">
          <a className="btn ghost" href={api.exportUrl(dsId, "csv")}>Cleaned CSV</a>
          <a className="btn ghost" href={api.exportUrl(dsId, "script")}>Python script</a>
          <a className="btn primary" href={api.exportUrl(dsId, "bundle")}>Download all (zip)</a>
          <button className="ghost" onClick={() => { localStorage.removeItem("fixmycsv.ds"); api.datasets().then(setRecent); setDsId(null); setState(null); setDraft(null); }}>Open another file</button>
        </div>
      </header>
      {error && <p className="error banner" role="alert">{error} <button className="link" onClick={() => setError(null)}>Dismiss</button></p>}
      <QualityStrip before={state.quality_before} after={state.quality_after} />
      <div className="layout">
        <IssuesPanel issues={state.issues} onSuggest={suggest} draft={draft} />
        <main className="center">
          {draft && catalog.length > 0 && (
            <DraftPanel dsId={dsId} draft={draft} setDraft={(nd) => {
              // switching op in manual mode resets params
              setDraft(nd);
            }} catalog={catalog} columns={columns} onApply={apply} onCancel={() => setDraft(null)} />
          )}
          {draft?.manual && (
            <div className="op-picker">
              <label className="field"><span>Operation</span>
                <select value={draft.op} onChange={(e) => setDraft({ ...draft, op: e.target.value, params: {} })}>
                  {catalog.map((c) => <option key={c.op} value={c.op}>{c.label}</option>)}
                </select>
              </label>
            </div>
          )}
          <nav className="tabs" role="tablist">
            {[["columns", "Columns"], ["data", "Rows"], ["script", "Script"]].map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
            ))}
          </nav>
          {tab === "columns" && <ColumnsView before={state.profile_before} after={state.profile_after} />}
          {tab === "data" && <DataTable dsId={dsId} version={version} />}
          {tab === "script" && <ScriptView dsId={dsId} version={version} />}
        </main>
        <PipelinePanel steps={state.steps} onToggle={toggle} onDelete={del} onAddManual={manual} />
      </div>
    </div>
  );
}
