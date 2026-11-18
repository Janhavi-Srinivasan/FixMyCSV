import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function DataTable({ dsId, version }) {
  const [stage, setStage] = useState("current");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const limit = 100;

  useEffect(() => { setOffset(0); }, [stage, dsId]);
  useEffect(() => {
    let live = true;
    api.data(dsId, stage, offset, limit).then((d) => live && setData(d));
    return () => { live = false; };
  }, [dsId, stage, offset, version]);

  if (!data) return <p className="muted">Loading rows…</p>;
  return (
    <div className="data">
      <div className="data-bar">
        <div className="seg" role="tablist">
          <button role="tab" aria-selected={stage === "current"} className={stage === "current" ? "on" : ""} onClick={() => setStage("current")}>Cleaned</button>
          <button role="tab" aria-selected={stage === "original"} className={stage === "original" ? "on" : ""} onClick={() => setStage("original")}>Original</button>
        </div>
        {stage === "current" && <span className="legend"><i className="swatch" /> changed from original</span>}
        <span className="muted small pager">
          Rows {data.total ? offset + 1 : 0}–{Math.min(offset + limit, data.total)} of {data.total}
          <button className="ghost small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</button>
          <button className="ghost small" disabled={offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>Next</button>
        </span>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th className="rownum">#</th>{data.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r._row}>
                <td className="rownum">{r._row}</td>
                {data.columns.map((c) => {
                  const hit = (data.changed[String(r._row)] || []).includes(c);
                  return <td key={c} className={hit ? "changed" : ""}>{r[c] === null ? <span className="null">empty</span> : r[c]}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
