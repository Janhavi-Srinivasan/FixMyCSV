import { useRef, useState } from "react";
import { api } from "../api.js";

export default function Upload({ onLoaded, recent, onOpen }) {
  const input = useRef();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [over, setOver] = useState(false);

  async function send(file) {
    if (!file) return;
    setBusy(true); setError(null);
    try { onLoaded(await api.upload(file)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  return (
    <main className="landing">
      <h1>FixMyCSV</h1>
      <p className="lede">Find what’s wrong with a spreadsheet, fix it one step at a time, and take home a script that repeats every fix.</p>
      <div
        className={`drop ${over ? "over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); send(e.dataTransfer.files[0]); }}
        onClick={() => input.current.click()}
        role="button" tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current.click()}
      >
        <input ref={input} type="file" hidden accept=".csv,.tsv,.txt,.xlsx,.xls" onChange={(e) => send(e.target.files[0])} />
        <strong>{busy ? "Reading your file…" : "Drop a CSV or Excel file here"}</strong>
        <span>or click to choose one (up to 50 MB)</span>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {recent.length > 0 && (
        <section className="recent">
          <h2>Pick up where you left off</h2>
          <ul>
            {recent.map((d) => (
              <li key={d.id}>
                <button className="link" onClick={() => onOpen(d.id)}>{d.filename}</button>
                <span className="muted">{d.rows} rows × {d.cols} columns</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
