// API base: `?api=https://host:port` pins a remote backend (persisted).
// Service key: `?key=` persists X-API-Key for commercial / cross-origin deploys.
// Live Server (e.g. :5500) has no API — we probe local FastAPI ports automatically.
const params = new URLSearchParams(location.search);
if (params.has("api")) {
  const v = (params.get("api") || "").trim().replace(/\/+$/, "");
  if (v) localStorage.setItem("hm.apiBase", v);
  else localStorage.removeItem("hm.apiBase");
}
if (params.has("key")) {
  const v = (params.get("key") || "").trim();
  if (v) localStorage.setItem("hm.apiKey", v);
  else localStorage.removeItem("hm.apiKey");
}

export let API_BASE = (window.HM_API_BASE ?? localStorage.getItem("hm.apiBase") ?? "").replace(/\/+$/, "");
export const API_KEY = (window.HM_API_KEY ?? localStorage.getItem("hm.apiKey") ?? "").trim();

if (/:(8010|8020|8030|8040)$/.test(API_BASE)) {
  API_BASE = "";
  localStorage.removeItem("hm.apiBase");
}

const LOCAL_BACKENDS = [
  "http://127.0.0.1:8000",
  "http://localhost:8000",
];

export function setApiBase(url) {
  API_BASE = String(url || "").replace(/\/+$/, "");
  if (API_BASE) localStorage.setItem("hm.apiBase", API_BASE);
  else localStorage.removeItem("hm.apiBase");
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** One-email body fetch. Vercel functions cap at 60s; this is display-only. */
export const EMAIL_GET_TIMEOUT_MS = 15000;

export async function request(path, { method = "GET", body, timeout = 120000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (API_KEY) headers["X-API-Key"] = API_KEY;
  try {
    const res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    if (!res.ok) {
      let detail = "";
      try {
        const j = await res.json();
        detail = typeof j?.detail === "string" ? j.detail : JSON.stringify(j?.detail ?? j);
      } catch {
        detail = await res.text().catch(() => "");
      }
      throw new ApiError(`HTTP ${res.status}${detail ? ` · ${detail}` : ""}`, res.status, detail);
    }
    if (res.status === 204) return null;
    return await res.json();
  } catch (err) {
    if (err?.name === "AbortError") throw new ApiError("Request timed out", 0, "timeout");
    if (err instanceof ApiError) throw err;
    throw new ApiError(err?.message || "Network error", 0, "network");
  } finally {
    clearTimeout(timer);
  }
}

export async function markReviewed(emailIds, reviewed = true) {
  return request("/api/board/reviewed", {
    method: "POST",
    body: { email_ids: emailIds, reviewed },
    timeout: 15000,
  });
}

export async function discoverApiBase() {
  const order = [];
  order.push("");
  const host = location.hostname;
  const hosted = /\.vercel\.app$/i.test(host);
  if (!hosted && (host === "localhost" || host === "127.0.0.1" || host === "[::1]")) {
    order.push("http://127.0.0.1:8000");
    order.push("http://localhost:8000");
  }
  if (API_BASE) order.push(API_BASE);
  const tried = new Set();
  const rounds = hosted ? 5 : 1;
  for (let round = 0; round < rounds; round++) {
    for (const base of order) {
      const key = base || `same:${location.origin}`;
      if (round === 0 && tried.has(key)) continue;
      tried.add(key);
      const hit = await probeHealth(base);
      if (hit) {
        setApiBase(hit.base);
        return hit.body;
      }
    }
    if (round < rounds - 1) await new Promise((r) => setTimeout(r, 800 * (round + 1)));
  }
  return null;
}

function probeHealth(base) {
  const priority =
    base === "http://127.0.0.1:8000" || base === "http://localhost:8000" ? 0
    : base === "" ? 1
    : 5;
  return new Promise((resolve) => {
    const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), base === "" ? 45000 : 8000);
    fetch(`${base}/health`, { signal: ctrl.signal })
      .then(async (res) => {
        if (!res.ok) return resolve(null);
        const body = await res.json();
        if (!body || !body.status) return resolve(null);
        resolve({ base, body, priority });
      })
      .catch(() => resolve(null))
      .finally(() => clearTimeout(timer));
  });
}
