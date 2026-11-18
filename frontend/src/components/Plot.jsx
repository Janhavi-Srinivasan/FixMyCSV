import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-basic-dist-min";

const factory = createPlotlyComponent.default || createPlotlyComponent;
const Plot = factory(Plotly);

const BEFORE = "#C9533F";
const AFTER = "#168A58";

/** Before/after distribution of one column, drawn from the diff payload. */
export default function Distribution({ dist }) {
  if (!dist) return null;
  let data = [];
  const layout = {
    height: 190, margin: { l: 36, r: 8, t: 6, b: 34 }, barmode: "overlay", bargap: 0.08,
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Hanken Grotesk, system-ui, sans-serif", size: 11, color: "#5A6B80" },
    legend: { orientation: "h", y: 1.18, x: 0 }, xaxis: { gridcolor: "#E3E9F0" }, yaxis: { gridcolor: "#E3E9F0" },
  };
  if (dist.kind === "numeric") {
    const mid = dist.edges.slice(0, -1).map((e, i) => (e + dist.edges[i + 1]) / 2);
    const width = (dist.edges[1] - dist.edges[0]) * 0.95;
    data = [
      { x: mid, y: dist.before, width, type: "bar", name: "Before", marker: { color: BEFORE, opacity: 0.55 } },
      { x: mid, y: dist.after, width, type: "bar", name: "After", marker: { color: AFTER, opacity: 0.6 } },
    ];
  } else if (dist.kind === "categorical") {
    layout.barmode = "group";
    layout.xaxis = { ...layout.xaxis, tickangle: -30, automargin: true };
    data = [
      { x: dist.labels, y: dist.before, type: "bar", name: "Before", marker: { color: BEFORE, opacity: 0.7 } },
      { x: dist.labels, y: dist.after, type: "bar", name: "After", marker: { color: AFTER, opacity: 0.8 } },
    ];
    layout.height = 220;
  } else {
    layout.barmode = "group";
    const keys = Object.keys(dist.before);
    data = [
      { x: keys, y: keys.map((k) => dist.before[k]), type: "bar", name: "Before", marker: { color: BEFORE, opacity: 0.7 } },
      { x: keys, y: keys.map((k) => dist.after[k]), type: "bar", name: "After", marker: { color: AFTER, opacity: 0.8 } },
    ];
  }
  return (
    <div className="plot">
      <div className="plot-title">Distribution of <code>{dist.column}</code></div>
      <Plot data={data} layout={layout} config={{ displayModeBar: false, responsive: true }} style={{ width: "100%" }} useResizeHandler />
    </div>
  );
}
