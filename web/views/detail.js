// Case drawer: verdict hero, seven-field comparison, evidence with in-place
// highlighting of the original message, and hand-offs to court / pilot.
import { store as bridgeStore } from "../lib/store.js?v=65";
import { esc, $, $$, on, shortId, fmtUsd, diffChars, renderDiff, reEscape, sourceWaitHtml } from "../lib/dom.js?v=65";
import { enter } from "../lib/motion.js";
import { fieldZh, fieldEn, scoutZh, VERDICT, STATE, RISK, strategyZh, failureZh } from "../lib/copy.js";
import { card, sevenFields, extraFields, orderedFields, ledgerRef, confidenceOf, pilotReasons } from "../lib/case.js?v=65";
import { pairView, present, effectiveState, valueFromBody } from "../lib/field-display.js?v=65";

export function renderDetail(root, runId, ctx) {
  const store = ctx.store || bridgeStore;
  const run = store.runById(runId);
  if (!run) {
    root.innerHTML = `<div class="drawer-inner"><button type="button" class="btn btn-sm drawer-close" data-close>Close</button><div class="empty"><h3>Case not found</h3><p>It may already have been cleared by a reset.</p></div></div>`;
    return;
  }
  const c = card(run);
  const v = c.verdict || run.verdict;
  const filed = run.reviewed === true || c.reviewed === true;
  const fields = sevenFields(run);
  const extras = extraFields(run);
  const charged = fields.filter((f) => f.charge && effectiveState(f) !== "MATCH");
  const reasons = v === "PILOT" ? pilotReasons(run) : [];
  const views = fields.map((fv) => ({ fv, view: pairView(fv) }));
  const disagree = views.filter((x) => x.view.state === "MISMATCH").length;
  const grey = views.filter((x) => x.view.state === "UNCERTAIN").length;
  const agree = fields.length - disagree - grey;
  const extraDisagree = extras.filter((f) => effectiveState(f) === "MISMATCH").length;

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
          <label class="detail-file">
            <input type="checkbox" data-file-card ${filed ? "checked" : ""} />
            <span>${filed ? "Filed — in folder" : "File to folder"}</span>
          </label>
          ${v === "PILOT" ? `
            <button type="button" class="btn btn-lg btn-clear" data-case-verdict="CLEAR">Release · CLEAR</button>
            <button type="button" class="btn btn-lg btn-hold" data-case-verdict="HOLD">Stop · HOLD</button>` : ""}
          ${charged.length ? `<button type="button" class="btn btn-primary" data-go-court>Open court, full argument <span class="arrow">→</span></button>` : ""}
          ${v === "PILOT" ? `<button type="button" class="btn btn-pilot" data-go-pilot>Open on Pilot <span class="arrow">→</span></button>` : ""}
        </div>
      </header>

      <section>
        <div class="section-title">
          <h3>Seven-field compare</h3>
          <small>${fields.length ? `${disagree ? `<b class="cmp-bad">${disagree} mismatch</b> · ` : ""}${agree} match${grey ? ` · ${grey} review` : ""}` : "SI · BL · STATE"}</small>
        </div>
        ${fields.length ? `
        ${disagree ? `<div class="cmp-hits">${views.filter((x) => x.view.state === "MISMATCH").map((x) => glanceHit(x.fv, x.view)).join("")}</div>` : ""}
        <p class="cmp-lead">${cmpLead(v, disagree, extraDisagree)}</p>
        <div class="ftable">
          <div class="frow head"><span>Field</span><span>Shipping instruction (SI)</span><span>Bill of lading (BL)</span><span>Result</span><span></span></div>
          ${views.map((x) => frow(x.fv, x.view, store)).join("")}
        </div>` : `<div class="empty"><p>This mail is not an SI/BL check, so there are no fields to compare. Scout labelled it “${esc(scoutZh(c.scout?.label))}” and filed it.</p></div>`}
        ${extras.length ? `
        <div class="section-title" style="margin-top:1.2rem"><h3>Also on the documents</h3><small>NOT IN THE SEVEN</small></div>
        <div class="ftable extra-ftable">
          <div class="frow head"><span>Field</span><span>Shipping instruction (SI)</span><span>Bill of lading (BL)</span><span>Result</span><span></span></div>
          ${extras.map((fv) => frow(fv, pairView(fv), store)).join("")}
        </div>` : ""}
      </section>

      <section id="source">
        <div class="section-title"><h3>Source mail</h3><small>EVIDENCE IN PLACE</small></div>
        <div class="source-text" id="source-text">${sourceWaitHtml()}</div>
      </section>

      ${c.reply_draft || v !== "PILOT" ? `<section><div class="section-title"><h3>Outbox reply</h3><small>DRAFT · never auto-sent</small></div><div class="reply-draft">${esc(c.reply_draft || "Close this mail as CLEAR or HOLD on Pilot to generate a sendable draft.")}</div></section>` : ""}
    </div>`;

  enter($$(".frow:not(.head)", root), { stagger: 0.03, y: 10 });

  on(root, "change", "[data-file-card]", async (e, input) => {
    const emailId = run.email_id;
    if (!emailId) return;
    const next = input.checked;
    const label = input.closest("label")?.querySelector("span");
    if (label) label.textContent = next ? "Filed — in folder" : "File to folder";
    try {
      await store.markReviewed([emailId], next);
      ctx.toast(next ? "Filed" : "Returned to docket", "ok");
      if (next) ctx.closeDetail();
    } catch (err) {
      input.checked = !next;
      if (label) label.textContent = !next ? "Filed — in folder" : "File to folder";
      ctx.toast(err.message || "Could not update the folder", "err");
    }
  });
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
    const pane = el.closest(".evidence-pane");
    const val = pane?.querySelector(".val");
    if (val) {
      val.classList.add("flash");
      val.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => val.classList.remove("flash"), 1400);
    }
    const src = $("#source-text", root);
    const target = findSourceMark(src, el.dataset.jump, el.dataset.file);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("flash");
      setTimeout(() => target.classList.remove("flash"), 1400);
    }
  });

  loadSource(store, run, $("#source-text", root)).then((email) => {
    if (!email) return;
    for (const cell of $$(".fval[data-fill]", root)) {
      const [side, field] = cell.dataset.fill.split(":");
      if (cell.dataset.filled === "1") continue;
      const val = valueFromBody(email.body_text || "", side, field);
      if (!val) continue;
      const shown = present(field, val);
      cell.innerHTML = fvalHtml(shown, null);
      cell.classList.remove("none");
      cell.dataset.filled = "1";
      const row = cell.closest(".frow");
      if (row?.dataset.state === "MATCH") {
        const otherSide = side === "si" ? "bl" : "si";
        const other = row.querySelector(`.fval[data-fill="${otherSide}:${field}"]`);
        if (other && other.dataset.filled !== "1") {
          other.innerHTML = fvalHtml(shown, null);
          other.classList.remove("none");
          other.dataset.filled = "1";
        }
      }
    }
  });
}

function cmpLead(verdict, disagree, extraDisagree) {
  if (disagree) return "Mismatches sit at the top in purple. Read SI versus BL on one row.";
  if (extraDisagree) return "The seven fields agree. A difference sits below — it is not one of the brief’s seven.";
  if (verdict === "HOLD") return "The seven fields write the same fact after format (caps, locode, labels). The stored court pass still holds this mail.";
  return "These seven fields agree. SI and BL write the same fact.";
}

function glanceHit(fv, view) {
  const si = view.L.text || "—";
  const bl = view.R.text || "—";
  return `<div class="cmp-hit"><b>${esc(fieldZh(fv.field))}</b><span>${esc(si)}</span><i>vs</i><span>${esc(bl)}</span></div>`;
}

function frow(fv, view, store) {
  const { L, R, state, si, bl } = view;
  const ref = ledgerRef(fv);
  const rule = ref ? store?.ruleById?.(ref.ruleId) : null;
  const contested = state !== "MATCH" && !!fv.charge;
  const hasDetail = contested;
  let leftHtml;
  let rightHtml;
  if (state === "MISMATCH" && si && bl) {
    const [dl, dr] = diffChars(L.text || si, R.text || bl);
    leftHtml = fvalHtml(L, dl);
    rightHtml = fvalHtml(R, dr);
  } else {
    leftHtml = fvalHtml(L, null);
    rightHtml = fvalHtml(R, null);
  }
  return `
    <div class="frow s-${state}" data-field="${esc(fv.field)}" data-state="${esc(state)}">
      <div class="fname"><b>${esc(fieldZh(fv.field))}</b><small>${esc(fieldEn(fv.field))} · ${esc(RISK[fv.risk_level] || fv.risk_level)} risk</small></div>
      <div class="fval ${L.empty ? "none" : ""}" data-fill="si:${esc(fv.field)}" ${L.empty ? "" : `data-filled="1"`}>${L.empty ? (state === "MATCH" ? "Agree" : "—") : leftHtml}</div>
      <div class="fval ${R.empty ? "none" : ""}" data-fill="bl:${esc(fv.field)}" ${R.empty ? "" : `data-filled="1"`}>${R.empty ? (state === "MATCH" ? "Agree" : "—") : rightHtml}</div>
      <div class="fstate">${STATE[state] || state}${ref ? `<span class="chip signal" title="From a ledger rule">rule</span>` : ""}</div>
      <div class="fmore">
        ${hasDetail ? `<button type="button" class="btn btn-sm" data-toggle>Evidence</button>` : ""}
        ${contested ? `<button type="button" class="btn btn-sm" data-field-court="${esc(fv.field)}">Court</button>` : ""}
      </div>
    </div>
    ${hasDetail ? `<div class="fdetail" hidden>${fdetail(fv, ref, rule)}</div>` : ""}`;
}

function fvalHtml(shown, diffParts) {
  const body = diffParts ? renderDiff(diffParts) : esc(shown.text);
  const code = shown.locode ? `<span class="locode">${esc(shown.locode)}</span>` : "";
  return `${body}${code}`;
}

function fdetail(fv, ref, rule) {
  const l = fv.charge.left;
  const r = fv.charge.right;
  const lShow = present(fv.field, l.raw_value);
  const rShow = present(fv.field, r.raw_value);
  const [dl, dr] = diffChars(lShow.text || l.raw_value, rShow.text || r.raw_value);
  const pleas = fv.pleas || [];
  const conf = confidenceOf(fv);
  return `
    ${ref ? `<div class="rule-src">${ref.replayed ? "Replay" : "Hit"} ledger rule <code>#${shortId(ref.ruleId)}</code> · ${rule ? `locked by ${esc(rule.created_by)} on case #${shortId(rule.source_case_id)}: “${esc(rule.left_pattern)}”${rule.decision === "accept_as_match" ? "≡" : "≠"}“${esc(rule.right_pattern)}”` : "locked by an earlier pilot ruling"}</div>` : ""}
    <p class="rationale">${rationaleZh(fv)}${pleas.length ? ` · defence ${pleas.filter((p) => p.accepted).length}/${pleas.length} held: ${pleas.map((p) => `${strategyZh(p.strategy) || "defence"}${p.accepted ? " ✓" : " ✗"}`).join(", ")}` : ""}${conf != null ? ` · extract confidence ${Math.round(conf * 100)}%` : ""}</p>
    <div class="evidence-split">
      ${pane("SI", l, dl, 0, lShow)}
      ${pane("BL", r, dr, 1, rShow)}
    </div>`;
}

function pane(side, fvv, diff, idx, shown) {
  const ev = fvv.evidence || {};
  const conf = fvv.confidence ?? 0.5;
  const bbox = ev.bbox;
  const code = shown?.locode ? `<span class="locode">${esc(shown.locode)}</span>` : "";
  return `
    <div class="evidence-pane">
      <div class="label">${side} · ${esc(fieldEn(fvv.name))}</div>
      <div class="val">${renderDiff(diff)}${code}</div>
      <div class="src">
        <span class="chip">${esc(sourceZh(ev.source))}</span>
        ${ev.attachment_name ? `<span class="chip mono">${esc(ev.attachment_name)}</span>` : ""}
        ${ev.page ? `<span class="chip mono">p.${ev.page}</span>` : ""}
        <span class="conf ${conf < 0.75 ? "low" : ""}"><i style="--p:${conf}"></i>${Math.round(conf * 100)}%</span>
        <button type="button" class="btn btn-sm" data-jump="${esc(fvv.raw_value)}" data-file="${esc(ev.attachment_name || "")}" data-side="${idx}">Find in source</button>
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
  if (r === "raw equality") return "Both sides write the same value";
  if (r.startsWith("defended by ")) return `Defence “${strategyZh(r.slice(12))}” held. Treated as a match`;
  if (r.startsWith("ledger replay:")) return "Rewritten by a ledger-rule replay";
  if (r.startsWith("ledger:")) return "Hit a ledger rule and ruled directly";
  if (r.startsWith("all strategies failed")) return "Every defence failed. Confirmed discrepancy";
  if (r.startsWith("confidence or evidence")) return "Confidence or evidence too thin to hold. Handed to a human";
  return esc(r);
}

async function loadSource(store, run, el) {
  if (!el || !store) return null;
  const emailId = run.email_id;
  el.dataset.loading = emailId;
  const stillHere = () => el.isConnected && el.dataset.loading === emailId;
  const unavailable = () => `<span class="muted">Source unavailable (${store.live ? "timed out or the backend did not return it" : "offline snapshot does not include it"}). Field evidence is in the table above.</span>`;

  if (!store.s.emails[emailId]) {
    el.innerHTML = sourceWaitHtml();
    const late = setTimeout(() => {
      if (!stillHere() || el.dataset.filled === "1") return;
      el.innerHTML = sourceWaitHtml({ slow: true });
    }, 5000);
    const email = await store.getEmail(emailId);
    clearTimeout(late);
    if (!stillHere()) return null;
    if (!email) {
      el.innerHTML = unavailable();
      return null;
    }
    paintSource(el, run, email);
    return email;
  }

  const email = await store.getEmail(emailId);
  if (!stillHere()) return null;
  if (!email) {
    el.innerHTML = unavailable();
    return null;
  }
  paintSource(el, run, email);
  return email;
}

function fold(s) {
  return String(s || "").replace(/\s+/g, " ").trim().toUpperCase();
}

function findSourceMark(src, q, file) {
  if (!src) return null;
  const needle = fold(q);
  const marks = $$("mark", src);
  const exact = marks.filter((m) => fold(m.textContent) === needle);
  if (exact.length) return exact[0];
  const head = needle.slice(0, 24);
  const fuzzy = marks.find((m) => {
    const t = fold(m.textContent);
    return (head && t.includes(head)) || (t && needle.includes(t.slice(0, 24)));
  });
  if (fuzzy) return fuzzy;
  if (file) {
    const hit = $$("[data-file]", src).find((n) => fold(n.dataset.file) === fold(file));
    if (hit) return hit;
  }
  return src.querySelector("[data-excerpt]");
}

function paintSource(el, run, email) {
  const fields = orderedFields(run).filter((f) => f.charge);
  const terms = new Map();
  const excerpts = [];
  const bodyFold = fold(email.body_text);
  for (const f of fields) {
    const st = effectiveState(f);
    const cls = st === "MISMATCH" ? "" : st === "UNCERTAIN" ? "warn" : "si";
    for (const [sideName, side] of [["SI", f.charge.left], ["BL", f.charge.right]]) {
      const val = (side?.raw_value || "").trim();
      if (val.length < 2) continue;
      terms.set(val, cls);
      const inBody = bodyFold.includes(fold(val).slice(0, 24));
      if (inBody) continue;
      const shown = present(f.field, val);
      excerpts.push({
        cls,
        val,
        text: shown.text || val,
        side: sideName,
        field: f.field,
        file: side?.evidence?.attachment_name || "",
        page: side?.evidence?.page || "",
      });
    }
  }
  let body = esc(email.body_text || "");
  body = body.replace(/(=== [A-Z ]+ ===)/g, '<span class="hd">$1</span>');
  const sorted = [...terms.keys()].sort((a, b) => b.length - a.length);
  if (sorted.length) {
    const re = new RegExp(`(${sorted.map((t) => reEscape(esc(t))).join("|")})`, "g");
    body = body.replace(re, (m) => `<mark class="${terms.get(unesc(m)) || ""}">${m}</mark>`);
  }
  const files = (email.attachment_paths || []).map((p) => p.split(/[\\/]/).pop()).filter(Boolean);
  const excerptHtml = excerpts.length ? `<div class="src-docs"><div class="hd">=== ATTACHMENTS / EXTRACTS ===</div>${excerpts.map((x) => `<p class="src-excerpt" data-excerpt="1" data-file="${esc(x.file)}"><mark class="${esc(x.cls)}">${esc(x.text)}</mark><span class="muted"> · ${esc(x.side)} ${esc(fieldEn(x.field))}${x.file ? ` · ${esc(x.file)}` : ""}${x.page ? ` p.${esc(x.page)}` : ""}</span></p>`).join("")}</div>` : "";
  el.dataset.filled = "1";
  el.innerHTML = `<div class="hd">${esc(email.subject || "")}</div><div class="muted" style="font-size:.78rem;margin-bottom:.6rem">${esc(email.from_addr || "")} → ${esc((email.to_addrs || []).join(", "))}${files.length ? ` · attachments ${files.map(esc).join(", ")}` : ""}</div>${body || '<span class="muted">(empty body)</span>'}${excerptHtml}`;
}

function unesc(s) {
  const t = document.createElement("textarea");
  t.innerHTML = s;
  return t.value;
}
