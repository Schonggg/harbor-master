// ④ Ledger — case stamps + pair rules, with revoke / reopen clarity.
import { store as bridgeStore } from "../lib/store.js?v=70";
import { esc, $, $$, on, shortId, fmtTime } from "../lib/dom.js?v=70";
import { enter } from "../lib/motion.js";
import { fieldZh } from "../lib/copy.js";
import { card, orderedFields, ledgerRef } from "../lib/case.js?v=70";
import { present, effectiveState } from "../lib/field-display.js?v=70";

export function mount(root, ctx) {
  const store = ctx.store || bridgeStore;
  root.innerHTML = `
    <section class="view">
      <div class="view-head">
        <div>
          <h1>Ledger <small>LEDGER</small></h1>
          <p>Two kinds of memory: <b>case stamps</b> (you closed one mail) and <b>pair rules</b> (a contested SI/BL writing that may auto-close later mail). Opening this page never changes Board counts. Header Refresh wipes this book and re-judges all 520 with AI.</p>
        </div>
        <div class="view-actions"><span class="chip signal" id="rule-count"></span></div>
      </div>
      <div id="rules"></div>
    </section>`;

  const rulesEl = $("#rules", root);
  on(rulesEl, "click", "[data-revoke]", async (_, el) => {
    el.disabled = true;
    try {
      await store.revoke(el.dataset.revoke);
      const kind = el.dataset.kind || "pair";
      ctx.toast(
        kind === "case"
          ? `Case stamp #${shortId(el.dataset.revoke)} removed from the book (the mail stays CLEAR/HOLD — use Reopen to Pilot to undo).`
          : `Pair rule #${shortId(el.dataset.revoke)} revoked · auto-closed mail re-opened to Pilot.`,
        "warn",
        7000,
      );
    } catch (e) { ctx.toast(e.message, "err"); el.disabled = false; }
  });
  on(rulesEl, "click", "[data-reopen]", async (_, el) => {
    el.disabled = true;
    try {
      await store.reopenToPilot({ caseId: el.dataset.reopen });
      ctx.toast(`Mail reopened to Pilot · case stamp and taught pairs from that ruling revoked.`, "ok", 6000);
    } catch (e) { ctx.toast(e.message, "err"); el.disabled = false; }
  });
  on(rulesEl, "click", "[data-open]", (_, el) => ctx.openDetail(el.dataset.open));
  on(rulesEl, "click", "[data-pilot]", () => ctx.navigate("pilot"));

  function usage(ruleId) {
    const hits = [];
    for (const r of store.s.runs) for (const f of orderedFields(r)) { const ref = ledgerRef(f); if (ref?.ruleId === ruleId) hits.push({ run: r, fv: f, replayed: ref.replayed }); }
    return hits;
  }

  function ruleCard(r) {
    const acc = r.decision === "accept_as_match";
    const hits = usage(r.rule_id);
    const src = store.runById(r.source_case_id);
    const isCase = r.field === "case";
    const left = present(r.field, r.left_pattern);
    const right = present(r.field, r.right_pattern);
    const pairHtml = isCase
      ? `<div class="eq"><span class="chip">Case stamp</span><b>${esc(r.left_pattern)}</b><span class="op">→</span><b>${esc(r.right_pattern)}</b></div>`
      : `<div class="eq"><span class="chip">${esc(fieldZh(r.field))}</span><b>${esc(left.text || r.left_pattern)}</b>${left.locode ? `<span class="locode">${esc(left.locode)}</span>` : ""}<span class="op">${acc ? "≡" : "≠"}</span><b>${esc(right.text || r.right_pattern)}</b>${right.locode ? `<span class="locode">${esc(right.locode)}</span>` : ""}</div>`;
    return `<div class="rule ${r.active ? "" : "revoked"} ${acc ? "s-MATCH" : "s-MISMATCH"}">
      <div class="rid">#${shortId(r.rule_id)}<small>${r.active ? "ACTIVE" : "REVOKED"}</small></div>
      <div class="pair">
        ${pairHtml}
        <div class="meta">
          <span>Locked by <b>${esc(r.created_by)}</b> on case <button type="button" class="btn btn-sm" data-open="${esc(src?.run_id || r.source_case_id)}">#${shortId(r.source_case_id)}</button></span>
          <span>· ${fmtTime(r.created_at)}</span>
          ${isCase
            ? `<span>· human ${esc(r.right_pattern)} · provenance only</span>`
            : `<span>· touches <b style="color:var(--text)">${hits.length}</b> case${hits.length === 1 ? "" : "s"}${hits.length ? ` (${hits.filter((h) => h.replayed).length} rewritten on replay)` : ""}</span>`}
          ${r.note ? `<span>· ${esc(r.note)}</span>` : ""}
          ${r.revoked_at ? `<span>· revoked ${fmtTime(r.revoked_at)}</span>` : ""}
        </div>
        ${!isCase && hits.length ? `<div class="affected">${hits.slice(0, 6).map((h) => `<span>#${shortId(h.run.run_id)} ${esc(card(h.run).subject || "")} <b style="color:var(--v)">${effectiveState(h.fv)}</b> <button type="button" class="btn btn-sm" data-open="${esc(h.run.run_id)}">Open</button></span>`).join("")}${hits.length > 6 ? `<span class="muted">…${hits.length - 6} more</span>` : ""}</div>` : ""}
      </div>
      <div class="rule-actions">
        ${r.active && isCase ? `<button type="button" class="btn btn-sm btn-pilot" data-reopen="${esc(r.source_case_id || r.left_pattern)}">Reopen to Pilot</button>` : ""}
        ${r.active ? `<button type="button" class="btn btn-sm btn-outline-hold" data-revoke="${esc(r.rule_id)}" data-kind="${isCase ? "case" : "pair"}">${isCase ? "Remove stamp" : "Revoke & reopen auto-closed"}</button>` : `<span class="chip ghost">Revoked</span>`}
      </div>
    </div>`;
  }

  function render(animate = false) {
    const rules = store.s.ledger || [];
    const stamps = rules.filter((r) => r.field === "case");
    const pairs = rules.filter((r) => r.field !== "case");
    const active = rules.filter((r) => r.active).length;
    $("#rule-count", root).textContent = `${active} active · ${rules.length - active} revoked · ${stamps.length} stamps · ${pairs.length} pairs`;
    if (!rules.length) {
      rulesEl.innerHTML = `<div class="empty panel"><h3>The ledger is blank</h3><p>Close a PILOT mail as CLEAR or HOLD to write a case stamp, or lock a contested field. Pair rules only form from UNCERTAIN / MISMATCH writings. Header Refresh wipes this book and re-judges the 520.</p><button type="button" class="btn btn-pilot" data-pilot>Go to Pilot <span class="arrow">→</span></button></div>`;
      return;
    }
    rulesEl.innerHTML = `
      <div class="ledger-section">
        <div class="section-title"><h3>Case stamps</h3><small>${stamps.length} · human CLEAR/HOLD</small></div>
        ${stamps.length ? `<div class="rule-list">${stamps.map(ruleCard).join("")}</div>` : `<p class="muted" style="margin:.4rem 0 1.2rem">No case stamps yet. Closing a Pilot mail writes one here.</p>`}
      </div>
      <div class="ledger-section">
        <div class="section-title"><h3>Pair rules</h3><small>${pairs.length} · contested SI/BL writings</small></div>
        ${pairs.length ? `<div class="rule-list">${pairs.map(ruleCard).join("")}</div>` : `<p class="muted" style="margin:.4rem 0 1.2rem">No pair rules. Only UNCERTAIN / MISMATCH fields are taught — already-matched fields are not.</p>`}
      </div>`;
    if (animate) enter($$(".rule", rulesEl), { stagger: 0.05, y: 12 });
  }

  render(true);
  store.loadLedger().then(() => render()).catch(() => {});
  return { update(_s, reason) { if (reason !== "busy") render(); }, destroy() {} };
}
