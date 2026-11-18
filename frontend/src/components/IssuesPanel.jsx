import { useState } from "react";

const LABEL = { high: "Needs fixing", medium: "Worth fixing", low: "Minor", info: "For review" };

function Issue({ issue, onSuggest, active }) {
  const [open, setOpen] = useState(false);
  const s = issue.suggestion;
  return (
    <li className={`issue sev-${issue.severity} ${active ? "active" : ""}`}>
      <div className="issue-head">
        <span className="sev" title={LABEL[issue.severity]} />
        <h3>{issue.title}</h3>
      </div>
      <p>{issue.detail}</p>
      {issue.examples.length > 0 && issue.type !== "duplicates" && (
        <p className="examples">{issue.examples.map((e, i) => <code key={i}>{e}</code>)}</p>
      )}
      <div className="issue-actions">
        <button className="primary small" onClick={() => onSuggest(s)}>Preview: {s.label}</button>
        {issue.alternatives.length > 0 && (
          <button className="ghost small" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Hide options" : `${issue.alternatives.length} other option${issue.alternatives.length > 1 ? "s" : ""}`}
          </button>
        )}
      </div>
      {open && (
        <div className="alts">
          {issue.alternatives.map((a, i) => (
            <button key={i} className="ghost small" onClick={() => onSuggest(a)}>{a.label}</button>
          ))}
        </div>
      )}
    </li>
  );
}

export default function IssuesPanel({ issues, onSuggest, draft }) {
  return (
    <aside className="panel issues">
      <header>
        <h2>Problems found</h2>
        <span className="count">{issues.length}</span>
      </header>
      {issues.length === 0 ? (
        <p className="empty">No problems detected. Export your cleaned file, or add a step by hand.</p>
      ) : (
        <ul>
          {issues.map((i) => (
            <Issue key={i.id} issue={i} onSuggest={onSuggest}
              active={draft && draft.op === i.suggestion.op && JSON.stringify(draft.params) === JSON.stringify(i.suggestion.params)} />
          ))}
        </ul>
      )}
    </aside>
  );
}
