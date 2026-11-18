import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function ScriptView({ dsId, version }) {
  const [script, setScript] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => { api.script(dsId).then((r) => setScript(r.script)); }, [dsId, version]);
  return (
    <div className="script">
      <div className="data-bar">
        <p className="muted small">This is what gets exported. It uses the same functions the app just ran, so it produces the same file.</p>
        <button className="ghost small" onClick={() => { navigator.clipboard.writeText(script); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre><code>{script}</code></pre>
    </div>
  );
}
