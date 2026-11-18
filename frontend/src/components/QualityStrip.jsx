const NAMES = { completeness: "Completeness", uniqueness: "Uniqueness", validity: "Valid types", consistency: "Consistency", plausibility: "Plausible values" };
const HELP = {
  completeness: "Share of cells that hold a real value (not empty or a placeholder)",
  uniqueness: "Share of rows that aren’t duplicates", validity: "Numbers and dates stored as proper types",
  consistency: "Matching spellings, no stray spaces", plausibility: "Values inside the expected range",
};

export default function QualityStrip({ before, after }) {
  return (
    <section className="quality" aria-label="Data quality before and after">
      <div className="overall">
        <span className="label">Quality score</span>
        <div className="score">
          {after.overall !== before.overall && <><span className="from">{before.overall}</span>
          <span aria-hidden className="arrow">→</span></>}
          <span className={`to ${after.overall > before.overall ? "up" : ""}`}>{after.overall}</span>
        </div>
        <span className="muted small">{before.issue_count} → {after.issue_count} problems</span>
      </div>
      {Object.keys(NAMES).map((k) => (
        <div key={k} className="dim" title={HELP[k]}>
          <span className="label">{NAMES[k]}</span>
          <div className="bar"><i className="b" style={{ width: `${before.dimensions[k]}%` }} /><i className="a" style={{ width: `${after.dimensions[k]}%` }} /></div>
          <span className="small">{before.dimensions[k] === after.dimensions[k] ? after.dimensions[k] : <><s>{before.dimensions[k]}</s> <b>{after.dimensions[k]}</b></>}</span>
        </div>
      ))}
    </section>
  );
}
