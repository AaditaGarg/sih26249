export const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
export const ORIGIN = BASE.replace(/\/api\/v1$/, "");
async function go(path, opts) {
  const r = await fetch(BASE + path, opts);
  if (!r.ok) { let m = `${path} failed (${r.status})`; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  return r.json();
}
export const api = (path, body) => go(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
export const upload = (path, formData) => go(path, { method: "POST", body: formData });
