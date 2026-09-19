// ④ Ledger — every rule a pilot ever taught the system, with provenance and revoke.
import { store as bridgeStore } from "../lib/store.js?v=50";
import { esc, $, $$, on, shortId, fmtTime } from "../lib/dom.js";
import { enter } from "../lib/motion.js";
import { fieldZh } from "../lib/copy.js";
import { card, orderedFields, ledgerRef } from "../lib/case.js";

export function mount(root, ctx) {
  const store = ctx.store || bridgeStore;
  root.innerHTML = `
    <section class="view">
      <div class="view-head">
        <div>
          <h1>Ledger <small>LEDGER</small></h1>
          <p>Pilot is the human desk — one case, one stamp. Ledger is the memory: a promoted pair becomes a reusable rule, replays older mail, and can be revoked. It does not store HOLD cards; it stores the pair a pilot taught the court.</p>
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
      rulesEl.innerHTML = `<div class="empty panel"><h3>The ledger is blank</h3><p>Stamp a PILOT case on the Pilot deck and promote the pair. That rule lands here and can replay older mail. Until then there is nothing to show — this is not a HOLD archive.</p><button type="button" class="btn btn-pilot" data-pilot>Go to Pilot <span class="arrow">→</span></button></div>`;
      return;
    }
    rulesEl.innerHTML = `<div class="rule-list">${rules.map((r) => {
      const acc = r.decision === "accept_as_match";
      const hits = usage(r.rule_id);
      const src = store.runById(r.source_case_id);
      return `<div class="rule ${r.active ? "" : "revoked"} ${acc ? "s-MATCH" : "s-MISMATCH"}">
        <div class="rid">#${shortId(r.rule_id)}<small>${r.active ? "ACTIVE" : "REVOKED"}</small></div>
        <div class="pair">
          <div class="eq"><span class="chip">${esc(fieldZh(r.field))}</span><b>${esc(r.left_pattern)}</b><span class="op">${acc ? "≡" : "≠"}</span><b>${esc(r.right_pattern)}</b></div>
          <div class="meta">
            <span>Locked by <b>${esc(r.created_by)}</b> on case <button type="button" class="btn btn-sm" data-open="${esc(src?.run_id || r.source_case_id)}">#${shortId(r.source_case_id)}</button></span>
            <span>· ${fmtTime(r.created_at)}</span>
            <span>· touches <b style="color:var(--text)">${hits.length}</b> case${hits.length === 1 ? "" : "s"}${hits.length ? ` (${hits.filter((h) => h.replayed).length} rewritten on replay)` : ""}</span>
            ${r.note ? `<span>· ${esc(r.note)}</span>` : ""}
            ${r.revoked_at ? `<span>· revoked ${fmtTime(r.revoked_at)}</span>` : ""}
          </div>
          ${hits.length ? `<div class="affected">${hits.slice(0, 6).map((h) => `<span>#${shortId(h.run.run_id)} ${esc(card(h.run).subject || "")} <b style="color:var(--v)">${h.fv.state}</b> <button type="button" class="btn btn-sm" data-open="${esc(h.run.run_id)}">Open</button></span>`).join("")}${hits.length > 6 ? `<span class="muted">…${hits.length - 6} more</span>` : ""}</div>` : ""}
        </div>
        <div>${r.active ? `<button type="button" class="btn btn-sm btn-outline-hold" data-revoke="${esc(r.rule_id)}">Revoke</button>` : `<span class="chip ghost">Revoked</span>`}</div>
      </div>`;
    }).join("")}</div>`;
    if (animate) enter($$(".rule", rulesEl), { stagger: 0.05, y: 12 });
  }

  render(true);
  return { update(_s, reason) { if (reason !== "busy") render(); }, destroy() {} };
}
