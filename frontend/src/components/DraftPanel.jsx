import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import DiffView from "./DiffView.jsx";
import ParamForm from "./ParamForm.jsx";

/** Preview of a not-yet-applied step: editable params + live diff + quality effect. */
export default function DraftPanel({ dsId, draft, setDraft, catalog, columns, onApply, onCancel }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const spec = catalog.find((c) => c.op === draft.op);
  const timer = useRef();
  const seq = useRef(0);

  useEffect(() => {
    const ready = spec.params.every((p) => !p.required || draft.params[p.name] !== undefined && draft.params[p.name] !== "" || p.default != null);
    if (!ready) { setResult(null); setError(null); return; }
    clearTimeout(timer.current);
    const mine = ++seq.current;
    timer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await api.preview(dsId, draft.op, draft.params);
        if (mine === seq.current) { setResult(r); setError(null); }
      } catch (e) { if (mine === seq.current) { setResult(null); setError(e.message); } }
      finally { if (mine === seq.current) setLoading(false); }
    }, 250);
    return () => clearTimeout(timer.current);
  }, [dsId, draft.op, JSON.stringify(draft.params)]);

  const qb = result?.quality_before.overall, qa = result?.quality_after.overall;
  return (
    <section className="draft" aria-live="polite">
      <header>
        <div>
          <h2>{spec.label}</h2>
          <p className="muted">{draft.reason || spec.description}</p>
        </div>
        <button className="ghost small" onClick={onCancel}>Discard preview</button>
      </header>
      <ParamForm spec={spec} params={draft.params} columns={columns} pool={draft.pool}
        onChange={(params) => setDraft({ ...draft, params })} />
      {error && <p className="error" role="alert">{error}</p>}
      {loading && !result && <p className="muted">Calculating the effect…</p>}
      {result && (
        <div className={loading ? "stale" : ""}>
          <DiffView diff={result.diff} />
          <p className="qdelta">
            Data quality score <b>{qb}</b> → <b className={qa >= qb ? "up" : "down"}>{qa}</b>
            <span className="muted"> · {result.issues_after} problem{result.issues_after !== 1 && "s"} would remain</span>
          </p>
        </div>
      )}
      <footer>
        <button className="primary" disabled={!result || result.diff.no_effect}
          onClick={() => onApply(draft)}>Add to pipeline</button>
        <span className="muted small">Nothing changes until you add it. You can undo it later.</span>
      </footer>
    </section>
  );
}
