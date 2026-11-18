function Bars({ histogram, top }) {
  const vals = histogram ? histogram.counts : top ? top.map((t) => t.count) : [];
  if (!vals.length) return null;
  const max = Math.max(...vals, 1);
  const w = 100 / vals.length;
  return (
    <svg viewBox="0 0 100 28" preserveAspectRatio="none" className="spark" aria-hidden>
      {vals.map((v, i) => <rect key={i} x={i * w + 0.5} width={Math.max(w - 1, 0.5)} y={28 - (v / max) * 26} height={(v / max) * 26} />)}
    </svg>
  );
}

const TYPE_LABEL = { integer: "whole number", float: "decimal", datetime: "date", categorical: "category", text: "free text", identifier: "identifier", boolean: "yes/no", empty: "empty" };

export default function ColumnsView({ before, after }) {
  const prev = Object.fromEntries(before.column_profiles.map((c) => [c.name, c]));
  return (
    <div className="columns-grid">
      {after.column_profiles.map((c) => {
        const b = prev[c.name];
        const changed = b && (b.missing_effective !== c.missing_effective || b.inferred_type !== c.inferred_type || b.dtype !== c.dtype);
        return (
          <article key={c.name} className="col-card">
            <header>
              <h3 title={c.name}>{c.name}</h3>
              <span className="type">{TYPE_LABEL[c.inferred_type] || c.inferred_type}{c.stored_as_text ? ", stored as text" : ""}</span>
            </header>
            <Bars histogram={c.histogram} top={c.top_values} />
            <dl>
              <div><dt>Missing</dt><dd>{b && b.missing_effective !== c.missing_effective ? <><s>{b.missing_effective}</s> <b>{c.missing_effective}</b></> : c.missing_effective} <span className="muted">({c.missing_pct}%)</span></dd></div>
              <div><dt>Distinct</dt><dd>{c.unique}</dd></div>
              {c.stats && c.stats.mean !== undefined && <div><dt>Range</dt><dd>{fmt(c.stats.min)} – {fmt(c.stats.max)}</dd></div>}
              {c.stats && c.stats.mean !== undefined && <div><dt>Mean</dt><dd>{fmt(c.stats.mean)}</dd></div>}
              {c.stats && c.stats.mean === undefined && <div><dt>Span</dt><dd>{c.stats.min} → {c.stats.max}</dd></div>}
              {c.top_values && <div><dt>Most common</dt><dd>{c.top_values[0]?.value}</dd></div>}
            </dl>
            {changed && b.dtype !== c.dtype && <p className="small was-now"><s>{b.dtype}</s> → <b>{c.dtype}</b></p>}
          </article>
        );
      })}
    </div>
  );
}

const fmt = (n) => (n === null || n === undefined ? "—" : Math.abs(n) >= 1000 ? Math.round(n).toLocaleString() : Number(n.toPrecision(4)));
