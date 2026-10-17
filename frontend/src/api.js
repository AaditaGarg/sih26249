const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
export async function api(path, body) {
  const r = await fetch(BASE + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  if (!r.ok) throw new Error(`${path} failed (${r.status})`);
  return r.json();
}
