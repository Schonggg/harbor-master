// Case-level derived text: one-line summaries, pilot reasons, ledger references.
import { FIELD_ORDER, fieldZh, strategyZh, failureZh } from "./copy.js";
import { shortId } from "./dom.js";

export function card(run) {
  return run?.payload?.card || {};
}

export function orderedFields(run) {
  const fvs = card(run).field_verdicts || [];
  const idx = (f) => { const i = FIELD_ORDER.indexOf(f.field); return i < 0 ? 99 : i; };
  return [...fvs].sort((a, b) => idx(a) - idx(b));
}

export function chargedFields(run) {
  return orderedFields(run).filter((f) => f.charge);
}

/** Fields worth putting in front of a judge: charged, or ledger-decided. */
export function courtFields(run) {
  return orderedFields(run).filter((f) => f.charge || /^ledger/.test(f.rationale || ""));
}

export function ledgerRef(fv) {
  const m = /^ledger(?: replay)?:([0-9a-f]+)/.exec(fv?.rationale || "");
  return m ? { ruleId: m[1], replayed: /replay/.test(fv.rationale) } : null;
}

export function confidenceOf(fv) {
  if (!fv?.charge) return null;
  return Math.min(fv.charge.left?.confidence ?? 1, fv.charge.right?.confidence ?? 1);
}

/** Why is this case on the pilot's desk? Returns [{code, text}]. */
export function pilotReasons(run) {
  const c = card(run);
  const out = [];
  for (const code of c.failure_codes || []) {
    if (code === "CHAOS_INJECTED") continue;
    out.push({ code, text: failureZh(code) });
  }
  for (const fv of orderedFields(run)) {
    if (fv.state !== "UNCERTAIN") continue;
    const conf = confidenceOf(fv);
    const src = fv.charge?.left?.evidence?.source || fv.charge?.right?.evidence?.source;
    let why = "similarity sits in the grey band";
    if (conf != null && conf < 0.75) why = `extract confidence ${Math.round(conf * 100)}% is too low`;
    else if (conf != null) why = `confidence ${Math.round(conf * 100)}% sits in the grey band`;
    if (src === "ocr") why = `OCR source · ${why}`;
    const confLabel = conf != null ? `${Math.round(conf * 100)}%` : "grey";
    out.push({
      code: fv.field,
      text: `${fieldZh(fv.field)}: ${why}`,
      short: `${fieldZh(fv.field)} · ${confLabel}`,
    });
  }
  if (!out.length && c.verdict === "PILOT") out.push({ code: "UNKNOWN", text: "Evidence is thin. The system raised a hand." });
  return out;
}

/** One sentence for the board card. */
export function summarize(run) {
  const c = card(run);
  const v = c.verdict || run.verdict;
  const fvs = orderedFields(run);
  if (v === "HOLD") {
    const bad = fvs.filter((f) => f.state === "MISMATCH");
    const f = bad[0];
    if (f?.charge) {
      const tries = (f.pleas || []).length;
      const more = bad.length > 1 ? `, plus ${bad.length - 1} more mismatch${bad.length > 2 ? "es" : ""}` : "";
      return `${fieldZh(f.field)} mismatch: SI "${f.charge.left?.raw_value}" vs BL "${f.charge.right?.raw_value}". ${tries} defences failed${more}`;
    }
    return `${bad.map((b) => fieldZh(b.field)).join(", ")}: real discrepancy`;
  }
  if (v === "PILOT") {
    const r = pilotReasons(run);
    return r.length ? `${r[0].text}${r.length > 1 ? ` (+${r.length - 1} more)` : ""}. Handed to a pilot.` : "Handed to a pilot";
  }
  const defended = fvs.filter((f) => f.state === "MATCH" && f.winning_strategy);
  const n = fvs.length;
  if (!n) return "Not an SI/BL check. Filed on classification only.";
  if (defended.length) {
    const names = [...new Set(defended.map((f) => strategyZh(f.winning_strategy)))].slice(0, 3).join(", ");
    return `${n} fields agree; ${defended.length} held after defence (${names})`;
  }
  return `${n} fields match character for character. No defence needed.`;
}

export function label(run) {
  return `#${shortId(run.run_id)}`;
}

export function fieldStateCounts(run) {
  const c = { MATCH: 0, MISMATCH: 0, UNCERTAIN: 0 };
  for (const f of orderedFields(run)) c[f.state] = (c[f.state] || 0) + 1;
  return c;
}
