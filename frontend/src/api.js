async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    let msg = res.statusText;
    try { const body = await res.json(); msg = body.detail || msg; } catch { /* not json */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.status === 204 ? null : res.json();
}
const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  operations: () => request("/operations"),
  upload: (file, sheet) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/datasets${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ""}`, { method: "POST", body: fd });
  },
  datasets: () => request("/datasets"),
  remove: (id) => request(`/datasets/${id}`, { method: "DELETE" }),
  state: (id) => request(`/datasets/${id}/state`),
  preview: (id, op, params) => request(`/datasets/${id}/preview`, json("POST", { op, params })),
  addStep: (id, op, params, reason) => request(`/datasets/${id}/steps`, json("POST", { op, params, reason })),
  toggleStep: (id, stepId, enabled) => request(`/datasets/${id}/steps/${stepId}`, json("PATCH", { enabled })),
  deleteStep: (id, stepId) => request(`/datasets/${id}/steps/${stepId}`, { method: "DELETE" }),
  data: (id, stage, offset, limit = 100) => request(`/datasets/${id}/data?stage=${stage}&offset=${offset}&limit=${limit}`),
  script: (id) => request(`/datasets/${id}/export-preview/script`),
  exportUrl: (id, kind) => `/api/datasets/${id}/export/${kind}`,
};
