// Case drawer: verdict hero, seven-field comparison, evidence with in-place
// highlighting of the original message, and hand-offs to court / pilot.
import { store as bridgeStore } from "../lib/store.js?v=42";
import { esc, $, $$, on, shortId, fmtUsd, diffChars, renderDiff, reEscape } from "../lib/dom.js";
import { enter } from "../lib/motion.js";
import { fieldZh, fieldEn, scoutZh, VERDICT, STATE, RISK, strategyZh, failureZh } from "../lib/copy.js";
import { card, orderedFields, ledgerRef, confidenceOf, pilotReasons } from "../lib/case.js";

export function renderDetail(root, runId, ctx) {
  const store = ctx.store || bridgeStore;
  const run = store.runById(runId);
  if (!run) {
    root.innerHTML = `<div class="drawer-inner"><button type="button" class="btn btn-sm drawer-close" data-close>Close</button><div class="empty"><h3>Case not found</h3><p>It may already have been cleared by a reset.</p></div></div>`;
    return;
  }
  const c = card(run);
  const v = c.verdict || run.verdict;
  const fields = orderedFields(run);
  const charged = fields.filter((f) => f.charge);
  const reasons = v === "PILOT" ? pilotReasons(run) : [];

  root.innerHTML = `
    <div class="drawer-inner v-${v}" data-run="${esc(run.run_id)}">
      <button type="button" class="btn btn-sm drawer-close" data-close aria-label="Close">Esc · Close</button>
      <header class="detail-head">
        <div class="verdict-hero"><i></i><b>${v}</b><span>${esc(VERDICT[v]?.zh || "")} · ${esc(VERDICT[v]?.desc || "")}</span></div>
        <h2>${esc(c.subject || run.email_id)}</h2>
        <div class="meta-row">
          <span class="chip">${esc(scoutZh(c.scout?.label))}${c.scout?.confidence != null ? ` · ${Math.round(c.scout.confidence * 100)}%` : ""}${c.scout?.route ? ` · ${esc(c.scout.route)}` : ""}</span>
          <span class="chip mono">${esc(run.email_id)}</span>
          <span class="chip mono">#${shortId(run.run_id)}</span>
          ${c.total_exposure_usd ? `<span class="chip danger">Exposure ${fmtUsd(c.total_exposure_usd)}</span>` : ""}
          ${c.degraded ? `<span class="degraded">DEGRADED · rules only</span>` : ""}
          ${(c.failure_codes || []).map((f) => `<span class="chip warn">${esc(failureZh(f))}</span>`).join("")}
        </div>
        ${reasons.length ? `<div class="reason-line"><span class="muted">Why the hand went up</span>${reasons.map((r) => `<span class="chip warn">${esc(r.text)}</span>`).join("")}</div>` : ""}
        <div class="decide-row">
          ${v === "PILOT" ? `
            <button type="button" class="btn btn-lg btn-clear" data-case-verdict="CLEAR">Release · CLEAR</button>
            <button type="button" class="btn btn-lg btn-hold" data-case-verdict="HOLD">Stop · HOLD</button>` : ""}
          ${charged.length ? `<button type="button" class="btn btn-primary" data-go-court>Open court, full argument <span class="arrow">→</span></button>` : ""}
          ${v === "PILOT" ? `<button type="button" class="btn btn-pilot" data-go-pilot>Open on Pilot <span class="arrow">→</span></button>` : ""}
        </div>
      </header>

      <section>
        <div class="section-title"><h3>Seven-field compare</h3><small>SI · BL · STATE</small></div>
        ${fields.length ? `
        <div class="ftable">
          <div class="frow head"><span>Field</span><span>SI shipping instruction</span><span>BL bill of lading</span><span>State</span><span></span></div>
          ${fields.map((fv) => frow(fv)).join("")}
        </div>` : `<div class="empty"><p>This mail is not an SI/BL check, so there are no fields to compare. Scout labelled it “${esc(scoutZh(c.scout?.label))}” and filed it.</p></div>`}
      </section>

      <section id="source">
        <div class="section-title"><h3>Source mail</h3><small>EVIDENCE IN PLACE</small></div>
        <div class="source-text" id="source-text"><span class="muted">Reading the original…</span></div>
      </section>

      ${c.reply_draft || v !== "PILOT" ? `<section><div class="section-title"><h3>Outbox reply</h3><small>DRAFT · never auto-sent</small></div><div class="reply-draft">${esc(c.reply_draft || "Close this mail as CLEAR or HOLD on Pilot to generate a sendable draft.")}</div></section>` : ""}
    </div>`;

  enter($$(".frow:not(.head)", root), { stagger: 0.03, y: 10 });

  on(root, "click", "[data-go-court]", () => { ctx.closeDetail(); ctx.navigate("court", { run: run.run_id, field: charged[0]?.field }); });
  on(root, "click", "[data-go-pilot]", () => { ctx.closeDetail(); ctx.navigate("pilot", { run: run.run_id }); });
  on(root, "click", "[data-case-verdict]", async (_, el) => {
    const verdict = el.dataset.caseVerdict;
    try {
      el.disabled = true;
      await store.setVerdict({ caseId: run.case_id || run.run_id, verdict });
      ctx.toast(`Mail → ${verdict}`, "ok");
      ctx.closeDetail();
      ctx.navigate("pilot");
    } catch (e) {
      ctx.toast(`Ruling failed: ${e.message}`, "err");
      el.disabled = false;
    }
  });
  on(root, "click", "[data-field-court]", (e, el) => { e.stopPropagation(); ctx.closeDetail(); ctx.navigate("court", { run: run.run_id, field: el.dataset.fieldCourt }); });
  on(root, "click", "[data-toggle]", (e, el) => {
    const row = el.closest(".frow");
    const det = row.nextElementSibling;
    const open = det && det.classList.contains("fdetail") && !det.hidden;
    if (det && det.classList.contains("fdetail")) det.hidden = open;
    row.classList.toggle("open", !open);
    el.textContent = open ? "Evidence" : "Hide";
    if (!open && det) enter([det], { y: 8, duration: 0.4 });
  });
  on(root, "click", "[data-jump]", (e, el) => {
    e.stopPropagation();
    const q = el.dataset.jump;
    const src = $("#source-text", root);
    const marks = $$("mark", src).filter((m) => m.textContent.trim().toUpperCase() === q.trim().toUpperCase());
    const target = marks[Number(el.dataset.side || 0)] || marks[0];
    if (!target) { ctx.toast("That text is not in the body (it may come from attachment OCR)", "warn"); return; }
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.add("flash");
    setTimeout(() => target.classList.remove("flash"), 1400);
  });

  loadSource(run, $("#source-text", root)).then((email) => {
    if (!email) return;
    for (const cell of $$(".fval.none[data-fill]", root)) {
      const [side, field] = cell.dataset.fill.split(":");
      const val = valueFromBody(email.body_text || "", side, field);
      if (val) { cell.textContent = val; cell.classList.remove("none"); }
    }
  });
}

const LABELS = {
  shipper: /^shipper\b/i,
  consignee: /^consignee\b/i,
  notify_party: /^notify(?: party)?\b/i,
  port_of_loading: /^(?:port of loading|load(?:ing)? port|pol)\b/i,
  port_of_discharge: /^(?:port of discharge|discharge port|pod)\b/i,
  container_count: /^container(?:s| count| qty)?\b/i,
  gross_weight: /^(?:gross )?weight\b/i,
  vessel_voyage: /^vessel(?:\s*\/\s*voyage)?\b/i,
};

/** Pull "Label: value" for a field out of the SI or BL section of the body. */
function valueFromBody(body, side, field) {
  const re = LABELS[field];
  if (!re) return "";
  const siIdx = body.search(/=== SHIPPING INSTRUCTION/i);
  const blIdx = body.search(/=== BILL OF LADING/i);
  let section = body;
  if (siIdx >= 0 && blIdx >= 0) section = side === "si" ? body.slice(siIdx, blIdx) : body.slice(blIdx);
  for (const line of section.split(/\r?\n/)) {
    const m = /^\s*([^:：]{2,40})[:：]\s*(.+)$/.exec(line);
    if (m && re.test(m[1].trim())) return m[2].trim();
  }
  return "";
}

function frow(fv) {
  const l = fv.charge?.left;
  const r = fv.charge?.right;
  const ref = ledgerRef(fv);
  const rule = ref ? store.ruleById(ref.ruleId) : null;
  const hasDetail = !!fv.charge;
  return `
    <div class="frow s-${fv.state}" data-field="${esc(fv.field)}">
      <div class="fname"><b>${esc(fieldZh(fv.field))}</b><small>${esc(fieldEn(fv.field)).toUpperCase()} · ${esc(RISK[fv.risk_level] || fv.risk_level)} risk</small></div>
      <div class="fval ${l ? "" : "none"}" data-fill="si:${esc(fv.field)}">${l ? esc(l.raw_value) : "character match"}</div>
      <div class="fval ${r ? "" : "none"}" data-fill="bl:${esc(fv.field)}">${r ? esc(r.raw_value) : "character match"}</div>
      <div class="fstate">${STATE[fv.state] || fv.state}${ref ? `<span class="chip signal" title="From a ledger rule">rule</span>` : ""}</div>
      <div class="fmore">
        ${hasDetail ? `<button type="button" class="btn btn-sm" data-toggle>Evidence</button><button type="button" class="btn btn-sm" data-field-court="${esc(fv.field)}">Court</button>` : ""}
      </div>
    </div>
    ${hasDetail ? `<div class="fdetail" hidden>${fdetail(fv, ref, rule)}</div>` : ""}`;
}

function fdetail(fv, ref, rule) {
  const l = fv.charge.left;
  const r = fv.charge.right;
  const [dl, dr] = diffChars(l.raw_value, r.raw_value);
  const pleas = fv.pleas || [];
  const conf = confidenceOf(fv);
  return `
    ${ref ? `<div class="rule-src">${ref.replayed ? "Replay" : "Hit"} ledger rule <code>#${shortId(ref.ruleId)}</code> · ${rule ? `locked by ${esc(rule.created_by)} on case #${shortId(rule.source_case_id)}: “${esc(rule.left_pattern)}”${rule.decision === "accept_as_match" ? "≡" : "≠"}“${esc(rule.right_pattern)}”` : "locked by an earlier pilot ruling"}</div>` : ""}
    <p class="rationale">${rationaleZh(fv)}${pleas.length ? ` · defence ${pleas.filter((p) => p.accepted).length}/${pleas.length} held: ${pleas.map((p) => `${strategyZh(p.strategy)}${p.accepted ? " ✓" : " ✗"}`).join(", ")}` : ""}${conf != null ? ` · extract confidence ${Math.round(conf * 100)}%` : ""}</p>
    <div class="evidence-split">
      ${pane("SI", l, dl, 0)}
      ${pane("BL", r, dr, 1)}
    </div>`;
}

function pane(side, fvv, diff, idx) {
  const ev = fvv.evidence || {};
  const conf = fvv.confidence ?? 0.5;
  const bbox = ev.bbox;
  return `
    <div class="evidence-pane">
      <div class="label">${side} · ${esc(fieldEn(fvv.name)).toUpperCase()}</div>
      <div class="val">${renderDiff(diff)}</div>
      <div class="src">
        <span class="chip">${esc(sourceZh(ev.source))}</span>
        ${ev.attachment_name ? `<span class="chip mono">${esc(ev.attachment_name)}</span>` : ""}
        ${ev.page ? `<span class="chip mono">p.${ev.page}</span>` : ""}
        <span class="conf ${conf < 0.75 ? "low" : ""}"><i style="--p:${conf}"></i>${Math.round(conf * 100)}%</span>
        <button type="button" class="btn btn-sm" data-jump="${esc(fvv.raw_value)}" data-side="${idx}">Find in source</button>
      </div>
      ${bbox && (bbox.x1 || bbox.y1) ? `<div class="bbox-doc" title="Attachment bbox"><span class="box" style="left:${pct(bbox.x0)}%;top:${pct(bbox.y0)}%;width:${pct(bbox.x1 - bbox.x0)}%;height:${pct(bbox.y1 - bbox.y0)}%"></span></div>` : ""}
      ${ev.snippet && ev.snippet !== fvv.raw_value ? `<div class="muted" style="font-size:.8rem">…${esc(ev.snippet)}…</div>` : ""}
    </div>`;
}

function pct(v) {
  const n = Number(v) || 0;
  return Math.max(0, Math.min(100, n <= 1 ? n * 100 : n / 10));
}

function sourceZh(src) {
  return { text: "Text", ocr: "OCR scan", vision: "Vision model", email_body: "Email body", attachment_meta: "Attachment metadata", rule: "Rule", ledger: "Ledger" }[src] || src || "Text";
}

export function rationaleZh(fv) {
  const r = fv.rationale || "";
  if (r === "raw equality") return "Character-for-character match";
  if (r.startsWith("defended by ")) return `Defence “${strategyZh(r.slice(12))}” held — treated as a match`;
  if (r.startsWith("ledger replay:")) return "Rewritten by a ledger-rule replay";
  if (r.startsWith("ledger:")) return "Hit a ledger rule and ruled directly";
  if (r.startsWith("all strategies failed")) return "Every defence failed — confirmed discrepancy";
  if (r.startsWith("confidence or evidence")) return "Confidence or evidence too thin to hold — handed to a human";
  return esc(r);
}

async function loadSource(run, el) {
  const email = await store.getEmail(run.email_id);
  if (!email) {
    el.innerHTML = `<span class="muted">Source unavailable (${store.live ? "backend did not return it" : "offline snapshot does not include it"}). Field evidence is in the table above.</span>`;
    return null;
  }
  const fields = orderedFields(run).filter((f) => f.charge);
  const terms = new Map();
  for (const f of fields) {
    const cls = f.state === "MISMATCH" ? "" : f.state === "UNCERTAIN" ? "warn" : "si";
    for (const side of [f.charge.left, f.charge.right]) {
      const val = (side?.raw_value || "").trim();
      if (val.length >= 2) terms.set(val, cls);
    }
  }
  let body = esc(email.body_text || "");
  body = body.replace(/(=== [A-Z ]+ ===)/g, '<span class="hd">$1</span>');
  const sorted = [...terms.keys()].sort((a, b) => b.length - a.length);
  if (sorted.length) {
    const re = new RegExp(`(${sorted.map((t) => reEscape(esc(t))).join("|")})`, "g");
    body = body.replace(re, (m) => `<mark class="${terms.get(unesc(m)) || ""}">${m}</mark>`);
  }
  el.innerHTML = `<div class="hd">${esc(email.subject || "")}</div><div class="muted" style="font-size:.78rem;margin-bottom:.6rem">${esc(email.from_addr || "")} → ${esc((email.to_addrs || []).join(", "))}${(email.attachment_paths || []).length ? ` · attachments ${email.attachment_paths.map((p) => esc(p.split(/[\\/]/).pop())).join(", ")}` : ""}</div>${body || '<span class="muted">(empty body)</span>'}`;
  return email;
}

function unesc(s) {
  const t = document.createElement("textarea");
  t.innerHTML = s;
  return t.value;
}
