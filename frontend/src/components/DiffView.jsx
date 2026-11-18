import Distribution from "./Plot.jsx";

const Cell = ({ v }) => (v === null || v === undefined ? <span className="null">empty</span> : <>{v === "" ? <span className="null">""</span> : v}</>);

export function Delta({ before, after, unit = "" }) {
  if (before === after) return <span>{after}{unit}</span>;
  return <span><s>{before}{unit}</s> <b>{after}{unit}</b></span>;
}

/** Shows exactly what one operation did: counts, concrete cell changes, removed rows, distribution. */
export default function DiffView({ diff, compact = false }) {
  if (!diff) return null;
  if (diff.no_effect) return <p className="muted">This step doesn’t change anything at this point in the pipeline.</p>;
  const [rb] = diff.shape_before, [ra] = diff.shape_after;
  return (
    <div className="diff">
      <div className="chips">
        {diff.rows_removed > 0 && <span className="chip del">{diff.rows_removed} row{diff.rows_removed !== 1 && "s"} removed ({rb} → {ra})</span>}
        {diff.cells_changed > 0 && <span className="chip mod">{diff.cells_changed} cell{diff.cells_changed !== 1 && "s"} changed</span>}
        {diff.columns_dropped.length > 0 && <span className="chip del">dropped {diff.columns_dropped.join(", ")}</span>}
        {diff.columns_renamed && <span className="chip mod">{Object.keys(diff.columns_renamed).length} columns renamed</span>}
        {diff.missing_before !== diff.missing_after && (
          <span className="chip">missing cells <Delta before={diff.missing_before} after={diff.missing_after} /></span>
        )}
      </div>

      {diff.per_column.length > 0 && (
        <ul className="percol">
          {diff.per_column.slice(0, compact ? 3 : 8).map((p) => (
            <li key={p.column}>
              <code>{p.was ? `${p.was} → ${p.column}` : p.column}</code>
              {p.cells_changed > 0 && <span>{p.cells_changed} changed</span>}
              {p.dtype_after && <span className="type">{p.dtype_before} → {p.dtype_after}</span>}
            </li>
          ))}
        </ul>
      )}

      {diff.samples.length > 0 && (
        <table className="changes">
          <thead><tr><th>Row</th><th>Column</th><th>Before</th><th>After</th></tr></thead>
          <tbody>
            {diff.samples.slice(0, compact ? 5 : 12).map((s, i) => (
              <tr key={i}>
                <td className="mono">{s.row}</td>
                <td>{s.column}</td>
                <td><span className="was"><Cell v={s.before} /></span></td>
                <td><span className="now"><Cell v={s.after} /></span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {diff.cells_changed > diff.samples.length && <p className="muted small">Showing {Math.min(diff.samples.length, compact ? 5 : 12)} of {diff.cells_changed} changed cells.</p>}

      {diff.removed_sample.length > 0 && (
        <div className="removed">
          <div className="small muted">Removed rows (first {Math.min(diff.removed_sample.length, compact ? 3 : 8)})</div>
          {diff.removed_sample.slice(0, compact ? 3 : 8).map((r) => (
            <div key={r.row} className="removed-row">
              <span className="mono">#{r.row}</span>
              {Object.entries(r.values).map(([k, v]) => <span key={k}><em>{k}</em> <Cell v={v} /></span>)}
            </div>
          ))}
        </div>
      )}
      {!compact && <Distribution dist={diff.distribution} />}
    </div>
  );
}
