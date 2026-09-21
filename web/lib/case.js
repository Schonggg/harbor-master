// Case-level derived text: one-line summaries, pilot reasons, ledger references.
import { FIELD_ORDER, fieldZh, strategyZh, failureZh } from "./copy.js";
import { shortId } from "./dom.js?v=65";
import { SEVEN_FIELDS, effectiveState, pairWritings, present } from "./field-display.js?v=65";

export function card(run) {
  return run?.payload?.card || {};
}

export function orderedFields(run) {
  const fvs = card(run).field_verdicts || [];
  const names = new Set(fvs.map((f) => f.field));
  const idx = (f) => { const i = FIELD_ORDER.indexOf(f.field); return i < 0 ? 99 : i; };
  return [...fvs]
    .filter((f) => !(f.field === "gross_weight" && names.has("gross_weight_kg")))
    .sort((a, b) => idx(a) - idx(b));
}

export function sevenFields(run) {
  const by = Object.fromEntries(orderedFields(run).map((f) => [f.field, f]));
  return SEVEN_FIELDS.map((name) => {
    if (name === "gross_weight_kg") return by.gross_weight_kg || by.gross_weight || null;
    return by[name] || null;
  }).filter(Boolean);
}

export function extraFields(run) {
  const seven = new Set(sevenFields(run).map((f) => f.field));
  return orderedFields(run).filter((f) => !seven.has(f.field) && f.field !== "gross_weight");
}

export function chargedFields(run) {
  return orderedFields(run).filter((f) => f.charge && effectiveState(f) !== "MATCH");
}

/** Fields worth putting in front of a judge: still disputed after format. */
export function courtFields(run) {
  return orderedFields(run).filter((f) => {
    if (effectiveState(f) === "MATCH" && !/^ledger/.test(f.rationale || "")) return false;
    return !!(f.charge || /^ledger/.test(f.rationale || ""));
  });
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
    const bad = fvs.filter((f) => effectiveState(f) === "MISMATCH");
    const f = bad[0];
    if (f) {
      const pair = pairWritings(f);
      const si = present(f.field, pair.si).text;
      const bl = present(f.field, pair.bl).text;
      const tries = (f.pleas || []).length;
      const more = bad.length > 1 ? `, plus ${bad.length - 1} more mismatch${bad.length > 2 ? "es" : ""}` : "";
      return `${fieldZh(f.field)} mismatch: SI "${si || pair.si}" vs BL "${bl || pair.bl}". ${tries} defences failed${more}`;
    }
    return "Held on the original court pass. After format the compared fields agree.";
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
  return "All compared fields agree.";
}

export function label(run) {
  return `#${shortId(run.run_id)}`;
}

export function fieldStateCounts(run) {
  const c = { MATCH: 0, MISMATCH: 0, UNCERTAIN: 0 };
  for (const f of orderedFields(run)) {
    const st = effectiveState(f);
    c[st] = (c[st] || 0) + 1;
  }
  return c;
}
