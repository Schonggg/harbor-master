// ④ Ledger — every rule a pilot ever taught the system, with provenance and revoke.
import { store as bridgeStore } from "../lib/store.js?v=57";
import { esc, $, $$, on, shortId, fmtTime } from "../lib/dom.js?v=57";
import { enter } from "../lib/motion.js";
import { fieldZh } from "../lib/copy.js";
import { card, orderedFields, ledgerRef } from "../lib/case.js?v=57";
import { present, effectiveState } from "../lib/field-display.js?v=57";

export function mount(root, ctx) {
  const store = ctx.store || bridgeStore;
  root.innerHTML = `
    <section class="view">
      <div class="view-head">
        <div>
          <h1>Ledger <small>LEDGER</small></h1>
          <p>Pilot is the human desk. Closing a mail as CLEAR or HOLD, or locking a single field, writes the SI/BL pair here. Later mail with the same writings reuses that ruling. Smash/empty cases have no pair, so they leave Pilot without a rule. Revoke stops new mail from using a rule.</p>
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
      ctx.toast(`Rule #${shortId(el.dataset.revoke)} revoked. New cases will not apply it.`, "warn");
    } catch (e) { ctx.toast(e.message, "err"); el.disabled = false; }
  });
  on(rulesEl, "click", "[data-open]", (_, el) => ctx.openDetail(el.dataset.open));
  on(rulesEl, "click", "[data-pilot]", () => ctx.navigate("pilot"));

  function usage(ruleId) {
    const hits = [];
    for (const r of store.s.runs) for (const f of orderedFields(r)) { const ref = ledgerRef(f); if (ref?.ruleId === ruleId) hits.push({ run: r, fv: f, replayed: ref.replayed }); }
    return hits;
  }

  function render(animate = false) {
    const rules = store.s.ledger || [];
    const active = rules.filter((r) => r.active).length;
    $("#rule-count", root).textContent = `${active} active · ${rules.length - active} revoked`;
    if (!rules.length) {
      rulesEl.innerHTML = `<div class="empty panel"><h3>The ledger is blank</h3><p>Close a PILOT mail as CLEAR or HOLD, or lock a single field on the Pilot deck. That SI/BL pair lands here and can replay older mail. Until then there is nothing to show — smash/empty cases cannot teach a pair.</p><button type="button" class="btn btn-pilot" data-pilot>Go to Pilot <span class="arrow">→</span></button></div>`;
      return;
    }
    rulesEl.innerHTML = `<div class="rule-list">${rules.map((r) => {
      const acc = r.decision === "accept_as_match";
      const hits = usage(r.rule_id);
      const src = store.runById(r.source_case_id);
      const left = present(r.field, r.left_pattern);
      const right = present(r.field, r.right_pattern);
      return `<div class="rule ${r.active ? "" : "revoked"} ${acc ? "s-MATCH" : "s-MISMATCH"}">
        <div class="rid">#${shortId(r.rule_id)}<small>${r.active ? "ACTIVE" : "REVOKED"}</small></div>
        <div class="pair">
          <div class="eq"><span class="chip">${esc(fieldZh(r.field))}</span><b>${esc(left.text || r.left_pattern)}</b>${left.locode ? `<span class="locode">${esc(left.locode)}</span>` : ""}<span class="op">${acc ? "≡" : "≠"}</span><b>${esc(right.text || r.right_pattern)}</b>${right.locode ? `<span class="locode">${esc(right.locode)}</span>` : ""}</div>
          <div class="meta">
            <span>Locked by <b>${esc(r.created_by)}</b> on case <button type="button" class="btn btn-sm" data-open="${esc(src?.run_id || r.source_case_id)}">#${shortId(r.source_case_id)}</button></span>
            <span>· ${fmtTime(r.created_at)}</span>
            <span>· touches <b style="color:var(--text)">${hits.length}</b> case${hits.length === 1 ? "" : "s"}${hits.length ? ` (${hits.filter((h) => h.replayed).length} rewritten on replay)` : ""}</span>
            ${r.note ? `<span>· ${esc(r.note)}</span>` : ""}
            ${r.revoked_at ? `<span>· revoked ${fmtTime(r.revoked_at)}</span>` : ""}
          </div>
          ${hits.length ? `<div class="affected">${hits.slice(0, 6).map((h) => `<span>#${shortId(h.run.run_id)} ${esc(card(h.run).subject || "")} <b style="color:var(--v)">${effectiveState(h.fv)}</b> <button type="button" class="btn btn-sm" data-open="${esc(h.run.run_id)}">Open</button></span>`).join("")}${hits.length > 6 ? `<span class="muted">…${hits.length - 6} more</span>` : ""}</div>` : ""}
        </div>
        <div>${r.active ? `<button type="button" class="btn btn-sm btn-outline-hold" data-revoke="${esc(r.rule_id)}">Revoke</button>` : `<span class="chip ghost">Revoked</span>`}</div>
      </div>`;
    }).join("")}</div>`;
    if (animate) enter($$(".rule", rulesEl), { stagger: 0.05, y: 12 });
  }

  render(true);
  return { update(_s, reason) { if (reason !== "busy") render(); }, destroy() {} };
}
