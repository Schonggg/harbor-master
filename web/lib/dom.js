export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/** Build an element from an HTML string (first element only). */
export function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

export function $(sel, root = document) {
  return root.querySelector(sel);
}
export function $$(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

export function on(root, event, selector, handler) {
  root.addEventListener(event, (e) => {
    const target = e.target.closest(selector);
    if (target && root.contains(target)) handler(e, target);
  });
}

export function shortId(id) {
  return String(id || "").slice(0, 8);
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export function fmtUsd(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${Math.round(v / 1_000)}k`;
  return usd.format(v);
}

export function fmtPct(n, digits = 1) {
  return `${(Number(n) || 0).toFixed(digits)}%`;
}

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function clamp(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Character-level diff via LCS. Returns two arrays of {ch, same} so both
 * sides can highlight exactly where they diverge (e.g. "0NE HAN0I" vs "ONE HANOI").
 */
export function diffChars(a, b) {
  a = String(a ?? "");
  b = String(b ?? "");
  const n = a.length;
  const m = b.length;
  if (n * m > 40000) {
    return [a.split("").map((ch) => ({ ch, same: a === b })), b.split("").map((ch) => ({ ch, same: a === b }))];
  }
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const left = [];
  const right = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      left.push({ ch: a[i], same: true });
      right.push({ ch: b[j], same: true });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      left.push({ ch: a[i], same: false });
      i++;
    } else {
      right.push({ ch: b[j], same: false });
      j++;
    }
  }
  while (i < n) left.push({ ch: a[i++], same: false });
  while (j < m) right.push({ ch: b[j++], same: false });
  return [left, right];
}

export function renderDiff(parts) {
  let out = "";
  let buf = "";
  let mode = null;
  const flush = () => {
    if (!buf) return;
    out += mode ? esc(buf) : `<mark>${esc(buf)}</mark>`;
    buf = "";
  };
  for (const p of parts) {
    if (mode !== p.same) {
      flush();
      mode = p.same;
    }
    buf += p.ch;
  }
  flush();
  return out;
}

/** Escape a string for use inside a RegExp. */
export function reEscape(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Indeterminate wait for /api/emails/{id}. `slow` after ~5s of waiting. */
export function sourceWaitHtml({ slow = false } = {}) {
  return `<div class="source-wait" role="status" aria-live="polite">
    <i class="source-wait-bar" aria-hidden="true"></i>
    <span>Reading the original</span>
    ${slow ? `<small>Still reading — the backend may be waking from sleep.</small>` : ""}
  </div>`;
}
