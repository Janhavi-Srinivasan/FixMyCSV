/** Renders the parameter inputs for any operation from the catalog spec. */
export default function ParamForm({ spec, params, columns, pool, onChange }) {
  const set = (name, value) => onChange({ ...params, [name]: value });

  return (
    <div className="params">
      {spec.params.map((p) => {
        const v = params[p.name];
        return (
          <label key={p.name} className="field">
            <span>{p.label}</span>
            {p.type === "column" && (
              <select value={v ?? ""} onChange={(e) => set(p.name, e.target.value)}>
                <option value="" disabled>Choose a column…</option>
                {columns.map((c) => <option key={c}>{c}</option>)}
              </select>
            )}
            {p.type === "columns" && (
              <div className="multi">
                {columns.map((c) => {
                  const on = (v || []).includes(c);
                  return (
                    <button type="button" key={c} className={`tag ${on ? "on" : ""}`} aria-pressed={on}
                      onClick={() => set(p.name, on ? v.filter((x) => x !== c) : [...(v || []), c])}>{c}</button>
                  );
                })}
              </div>
            )}
            {p.type === "select" && (
              <select value={v ?? p.default} onChange={(e) => set(p.name, e.target.value)}>
                {p.options.map((o) => <option key={o}>{o}</option>)}
              </select>
            )}
            {p.type === "bool" && <input type="checkbox" checked={!!v} onChange={(e) => set(p.name, e.target.checked)} />}
            {p.type === "number" && (
              <input type="number" step="any" value={v ?? p.default ?? ""} onChange={(e) => set(p.name, e.target.value === "" ? null : Number(e.target.value))} />
            )}
            {p.type === "text" && <input type="text" value={v ?? ""} onChange={(e) => set(p.name, e.target.value)} />}
            {p.type === "list" && (
              <input type="text" value={(v ?? p.default ?? []).join(", ")}
                onChange={(e) => set(p.name, e.target.value.split(",").map((x) => x.trim()))} />
            )}
            {p.type === "mapping" && (
              <MappingEditor mapping={v || {}} pool={pool || v || {}} onChange={(m) => set(p.name, m)} />
            )}
          </label>
        );
      })}
    </div>
  );
}

function MappingEditor({ mapping, pool, onChange }) {
  return (
    <div className="mapping">
      {Object.keys(pool).map((from) => {
        const on = from in mapping;
        return (
          <div key={from} className={`map-row ${on ? "" : "off"}`}>
            <input type="checkbox" checked={on} aria-label={`Replace ${from}`}
              onChange={() => { const m = { ...mapping }; on ? delete m[from] : (m[from] = pool[from]); onChange(m); }} />
            <code>{from}</code>
            <span aria-hidden>→</span>
            <input type="text" value={mapping[from] ?? pool[from]} disabled={!on}
              onChange={(e) => onChange({ ...mapping, [from]: e.target.value })} />
          </div>
        );
      })}
    </div>
  );
}
