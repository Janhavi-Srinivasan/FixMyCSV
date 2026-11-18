import { useState } from "react";
import DiffView from "./DiffView.jsx";

function paramSummary(params) {
  return Object.entries(params)
    .filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]) => {
      if (k === "mapping") return `${Object.keys(v).length} replacements`;
      return `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`;
    }).join(" · ");
}

function Step({ step, index, onToggle, onDelete }) {
  const [open, setOpen] = useState(false);
  const d = step.diff;
  const effect = step.status === "applied" && d
    ? [d.rows_removed && `−${d.rows_removed} rows`, d.cells_changed && `${d.cells_changed} cells`,
       d.columns_dropped.length && `−${d.columns_dropped.length} col`].filter(Boolean).join(", ") || "no effect"
    : null;
  return (
    <li className={`step ${step.status}`}>
      <div className="step-head">
        <span className="step-n">{index}</span>
        <div className="step-main">
          <h3>{step.label}</h3>
          <p className="params-line mono">{paramSummary(step.params) || "no parameters"}</p>
        </div>
        <label className="switch" title={step.enabled ? "Undo this step" : "Redo this step"}>
          <input type="checkbox" checked={step.enabled} onChange={() => onToggle(step)} aria-label={`${step.enabled ? "Undo" : "Redo"} ${step.label}`} />
          <span />
        </label>
      </div>
      {step.reason && <p className="reason">{step.reason}</p>}
      {step.status === "error" && <p className="error small">Skipped: {step.error}</p>}
      {step.status === "disabled" && <p className="muted small">Undone. Later steps run as if this never happened.</p>}
      <div className="step-foot">
        {effect && <button className="link small" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide changes" : `What changed (${effect})`}</button>}
        <button className="link small danger" onClick={() => onDelete(step)}>Delete</button>
      </div>
      {open && <DiffView diff={d} compact />}
    </li>
  );
}

export default function PipelinePanel({ steps, onToggle, onDelete, onAddManual }) {
  const active = steps.filter((s) => s.status === "applied").length;
  return (
    <aside className="panel pipeline">
      <header>
        <h2>Cleaning steps</h2>
        <span className="count">{active}</span>
      </header>
      {steps.length === 0 ? (
        <p className="empty">No steps yet. Preview a suggestion on the left and add it here. Steps run top to bottom on your original file.</p>
      ) : (
        <ol>{steps.map((s, i) => <Step key={s.id} step={s} index={i + 1} onToggle={onToggle} onDelete={onDelete} />)}</ol>
      )}
      <button className="ghost" onClick={onAddManual}>Add a step by hand</button>
    </aside>
  );
}
