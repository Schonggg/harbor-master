/** Docket finder: exact email numbers plus keyword match on the compact card. */

export function tokensOf(q) {
  return String(q || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
}

export function idAliases(token) {
  const t = String(token || "").trim().toLowerCase();
  const out = new Set([t]);
  const m = /^(?:email[_-])?0*(\d+)$/.exec(t);
  if (!m) return out;
  const n = m[1];
  const pad = n.padStart(3, "0");
  out.add(n);
  out.add(pad);
  out.add(`email_${n}`);
  out.add(`email_${pad}`);
  out.add(`email-${pad}`);
  return out;
}

function haystack(run) {
  const c = run?.payload?.card || {};
  const bits = [
    run.email_id,
    run.run_id,
    run.verdict,
    run.subject,
    run.from_addr,
    c.subject,
    c.verdict,
    c.email_id,
    c.scout?.label,
    c.scout?.category,
    c.degraded ? "degraded" : "",
    ...(c.failure_codes || []),
  ];
  for (const fv of c.field_verdicts || []) {
    bits.push(fv.field, fv.state, fv.charge?.left?.raw_value, fv.charge?.right?.raw_value, fv.left_value, fv.right_value);
  }
  return bits.filter((x) => x != null && x !== "").join("\n").toLowerCase();
}

function idHits(token, emailId) {
  const id = String(emailId || "").toLowerCase();
  if (!id) return false;
  const aliases = idAliases(token);
  if (aliases.has(id)) return true;
  const m = /^(?:email[_-])?0*(\d+)$/.exec(token);
  if (m) {
    const n = m[1];
    return id === `email_${n}` || id === `email_${n.padStart(3, "0")}`;
  }
  return id.includes(token);
}

export function matchesRun(run, q) {
  const tokens = tokensOf(q);
  if (!tokens.length) return true;
  const hay = haystack(run);
  const emailId = run.email_id || run.payload?.card?.email_id;
  return tokens.every((tok) => {
    if (/^(?:email[_-])?0*\d+$/.test(tok)) return idHits(tok, emailId);
    return idHits(tok, emailId) || hay.includes(tok);
  });
}

export function rankRun(run, q) {
  const tokens = tokensOf(q);
  if (!tokens.length) return 2;
  const id = String(run.email_id || "").toLowerCase();
  if (tokens.some((tok) => idAliases(tok).has(id))) return 0;
  if (tokens.some((tok) => id.includes(tok))) return 1;
  return 2;
}

export function highlightText(text, q) {
  const raw = String(text ?? "");
  const tokens = [...new Set(tokensOf(q))].sort((a, b) => b.length - a.length);
  if (!raw || !tokens.length) return raw;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
  const pattern = tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  if (!pattern) return esc(raw);
  const re = new RegExp(`(${pattern})`, "gi");
  return esc(raw).replace(re, "<mark class=\"hit\">$1</mark>");
}
