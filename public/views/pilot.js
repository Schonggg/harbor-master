// ③ Pilot deck — the human in the loop. One decision becomes a ledger rule, the
// ledger replays history, and the queue visibly collapses.
import { store as bridgeStore } from "../lib/store.js?v=46";
import { esc, $, $$, on, shortId, diffChars, renderDiff, fmtUsd, sourceWaitHtml } from "../lib/dom.js";
import { gsap, reduced, enter, countTo, collapseOut, pulse } from "../lib/motion.js";
import { fieldZh, fieldEn, RISK, failureZh } from "../lib/copy.js";
import { card, orderedFields, pilotReasons, ledgerRef, confidenceOf } from "../lib/case.js?v=12";

export function mount(root, ctx, params = {}) {
  const store = ctx.store || bridgeStore;
  let runId = params.run || null;
  let field = params.field || null;
  let lastStamp = null;
  let deciding = false;
  let filter = "lockable";
  let filterPinned = false;

  root.innerHTML = `
    <section class="view">
      <div class="view-head">
        <div>
          <h1>Pilot <small>PILOT DECK</small></h1>
          <p>Read the mail. Release it as CLEAR or stop it as HOLD. A grey SI/BL pair can be locked into the Ledger so later mail reuses that ruling. Chaos / broken-pipeline cases sit in this same queue — filter them on the left.</p>
        </div>
        <div class="view-actions">
          <button type="button" class="btn" id="pilot-ledger">Ledger rules <span class="arrow">→</span></button>
        </div>
      </div>
      <div class="pilot-layout">
        <aside class="panel">
          <div class="queue-head">
            <div><small>PILOT QUEUE</small><div class="big v-PILOT" id="qn" data-value="0">0</div><div class="muted" style="font-size:.8rem" id="q-sub"></div></div>
          </div>
          <div class="seg queue-filters" id="q-filters"></div>
          <div class="queue-list" id="queue"></div>
        </aside>
        <div class="panel pilot-main" id="main"></div>
      </div>
    </section>`;

  const queueEl = $("#queue", root);
  const mainEl = $("#main", root);

  on(queueEl, "click", ".queue-item", (_, el) => { runId = el.dataset.run; field = null; lastStamp = null; renderMain(true); renderQueue(); });
  on(root, "click", "[data-qfilter]", (e, el) => {
    e.preventDefault();
    const next = el.dataset.qfilter;
    if (!next) return;
    filter = next;
    filterPinned = true;
    lastStamp = null;
    pickDefaults({ fromFilter: true });
    renderQueue();
    renderMain();
  });
  on(root, "click", "[data-ledger], #pilot-ledger", () => ctx.navigate("ledger"));
  on(mainEl, "click", "[data-field]", (_, el) => { field = el.dataset.field; renderMain(true); });
  on(mainEl, "click", "[data-decide]", (_, el) => decide(el.dataset.decide));
  on(mainEl, "click", "[data-case-verdict]", (_, el) => decideCase(el.dataset.caseVerdict));
  on(mainEl, "click", "[data-court]", () => ctx.navigate("court", { run: runId, field }));
  on(mainEl, "click", "[data-detail]", () => ctx.openDetail(runId));
  on(mainEl, "click", "[data-open-run]", (_, el) => ctx.openDetail(el.dataset.openRun));
  on(mainEl, "click", "[data-board]", () => ctx.navigate("board"));

  const SMASH = ["ATTACHMENT_CORRUPT", "OCR_GARBLED", "EMPTY_EMAIL", "LLM_TIMEOUT"];
  function isChaos(run) {
    const codes = card(run).failure_codes || [];
    return codes.includes("CHAOS_INJECTED") || SMASH.some((c) => codes.includes(c));
  }
  function hasWriting(side) {
    const v = side?.raw_value;
    return v != null && String(v).trim() !== "";
  }
  function lockableFields(run) {
    return orderedFields(run).filter((f) => (
      (f.state === "UNCERTAIN" || f.state === "MISMATCH")
      && hasWriting(f.charge?.left)
      && hasWriting(f.charge?.right)
    ));
  }
  function canLock(run) {
    if (card(run).lockable === true) return true;
    return lockableFields(run).length > 0;
  }
  function rank(run) {
    const lock = lockableFields(run);
    if (card(run).lockable || lock.some((f) => f.state === "UNCERTAIN")) return 0;
    if (lock.length) return 1;
    if (isChaos(run)) return 2;
    if (card(run).degraded) return 3;
    return 4;
  }
  function sortQueue(list) {
    return [...list].sort((a, b) => rank(a) - rank(b) || String(a.email_id).localeCompare(String(b.email_id)));
  }
  function applyFilter(all, id) {
    if (id === "lockable" || id === "grey") return sortQueue(all.filter(canLock));
    if (id === "chaos") return sortQueue(all.filter(isChaos));
    if (id === "degraded") return sortQueue(all.filter((r) => card(r).degraded));
    return sortQueue(all);
  }
  function resolveFilter(all) {
    const nLock = all.filter(canLock).length;
    if (!filterPinned) filter = nLock ? "lockable" : "all";
    return { q: applyFilter(all, filter), nLock };
  }
  function emptyCopy(id, hasRuns) {
    if (!hasRuns) return { title: "No cases yet", body: "Load the official inbox from the Board first." };
    if (id === "lockable") return {
      title: "No pair to lock",
      body: "Ledger only stores an SI writing and a BL writing. None of the remaining Pilot mail has that pair — it is smash/broken or rules-only. CLEAR already matched; HOLD already confirmed a mismatch. When a later Pilot case has both writings, Lock to Ledger lists it first.",
    };
    if (id === "chaos") return {
      title: "No smashed cases",
      body: "Nothing in this queue is attachment-corrupt, garbled, empty, or timed out.",
    };
    if (id === "degraded") return {
      title: "No degraded cases",
      body: "Every remaining Pilot mail extracted with the model, not rules-only.",
    };
    return { title: "Queue is empty", body: "Every mail was ruled automatically. To see Pilot work, smash a case that needs a human in Chaos." };
  }
  function kindOf(run) {
    if (canLock(run)) return "lockable";
    if (isChaos(run)) return "chaos";
    if (card(run).degraded) return "degraded";
    return "other";
  }

  function pickDefaults({ fromFilter = false } = {}) {
    const q = applyFilter(store.pilotQueue(), filter);
    const inFiltered = q.some((r) => r.run_id === runId);
    if (fromFilter || !store.runById(runId) || (!lastStamp && !inFiltered)) {
      if (!lastStamp) runId = q[0]?.run_id || null;
    }
    const run = store.runById(runId);
    if (!run) { field = null; return; }
    const lockable = lockableFields(run);
    if (!lockable.find((f) => f.field === field)) {
      field = lockable.find((f) => f.state === "UNCERTAIN")?.field || lockable[0]?.field || null;
    }
  }

  function renderFilters(nLock, nChaos, nDeg, nAll) {
    const el = $("#q-filters", root);
    if (!el) return;
    const counts = { lockable: nLock, all: nAll, chaos: nChaos, degraded: nDeg };
    if (el.dataset.ready !== "1") {
      el.innerHTML = [
        ["lockable", "Lock to Ledger"],
        ["all", "All"],
        ["chaos", "Chaos / broken"],
        ["degraded", "Degraded"],
      ].map(([id, label]) => `<button type="button" data-qfilter="${id}">${label}<span class="n">0</span></button>`).join("");
      el.dataset.ready = "1";
    }
    $$("[data-qfilter]", el).forEach((btn) => {
      const id = btn.dataset.qfilter;
      btn.classList.toggle("on", id === filter);
      const n = btn.querySelector(".n");
      if (n) n.textContent = String(counts[id] ?? 0);
    });
  }

  function renderQueue(animateIn = false) {
    const all = store.pilotQueue();
    const { q, nLock } = resolveFilter(all);
    const nChaos = all.filter(isChaos).length;
    const nDeg = all.filter((r) => card(r).degraded).length;
    const qn = $("#qn", root);
    if (qn) {
      qn.dataset.value = String(q.length);
      qn.textContent = String(q.length);
    }
    const sub = $("#q-sub", root);
    if (sub) {
      sub.textContent = all.length
        ? `${nLock} can lock to Ledger · ${nChaos} smashed / broken · ${nDeg} degraded`
        : "Queue is empty";
    }
    renderFilters(nLock, nChaos, nDeg, all.length);
    const ledgerBtn = $("#pilot-ledger", root);
    if (ledgerBtn) {
      const n = (store.s.ledger || []).filter((r) => r.active).length;
      ledgerBtn.innerHTML = n ? `Ledger · ${n} rules <span class="arrow">→</span>` : `Ledger rules <span class="arrow">→</span>`;
    }
    if (gsap) gsap.killTweensOf($$(".queue-item", queueEl));
    if (!q.length) {
      const empty = emptyCopy(filter, store.s.runs.length);
      queueEl.innerHTML = `<div class="empty" style="padding:2rem 1rem"><h3>${esc(empty.title)}</h3><p>${esc(empty.body)}</p></div>`;
      return;
    }
    queueEl.innerHTML = q.map((r) => {
      const c = card(r);
      const reasons = pilotReasons(r);
      return `<button type="button" class="queue-item ${r.run_id === runId ? "on" : ""}" data-run="${esc(r.run_id)}" data-kind="${kindOf(r)}">
        <b>${esc(c.subject || r.email_id)}</b>
        <div class="why">${reasons.slice(0, 2).map((x) => `<span class="chip warn">${esc(x.short || x.text)}</span>`).join("")}${reasons.length > 2 ? `<span class="chip">+${reasons.length - 2}</span>` : ""}</div>
        <small class="mono muted">#${shortId(r.run_id)}</small>
      </button>`;
    }).join("");
    if (animateIn && q.length && q.length <= 16) enter($$(".queue-item", queueEl), { stagger: 0.04, y: 10 });
  }

  function renderMain(swap = false) {
    const run = store.runById(runId);
    if (!run) {
      const empty = emptyCopy(filter, store.s.runs.length);
      mainEl.innerHTML = `<div class="empty"><h3>${esc(empty.title)}</h3><p>${esc(empty.body)}</p><button type="button" class="btn" data-board>Back to Board</button></div>`;
      return;
    }
    const c = card(run);
    const lockable = lockableFields(run);
    const fv = lockable.find((f) => f.field === field) || null;
    const reasons = pilotReasons(run);

    let body = "";
    if (lastStamp && lastStamp.runId === run.run_id) {
      body = lastStamp.kind === "case" ? caseStamp(lastStamp) : stampBlock(lastStamp);
    } else {
      body = `
        ${mailBlock(run)}
        ${caseButtons()}
        ${fv ? decideBlock(fv) : fieldHint(c, reasons)}`;
    }

    mainEl.innerHTML = `
      <div>
        <div class="meta-row" style="margin-bottom:.5rem">
          <span class="verdict-tag v-${c.verdict}" style="color:var(--v)">${c.verdict}</span>
          <span class="chip mono">#${shortId(run.run_id)}</span>
          ${c.degraded ? `<span class="degraded">DEGRADED</span>` : ""}
        </div>
        <h2>${esc(c.subject || run.email_id)}</h2>
        ${reasons.length ? `<div class="reason-line" style="margin-top:.5rem"><span class="muted">Why the hand went up</span>${reasons.map((r) => `<span class="chip warn">${esc(r.text)}</span>`).join("")}</div>` : ""}
      </div>
      ${lockable.length > 1 ? `<div class="seg">${lockable.map((f) => `<button type="button" data-field="${esc(f.field)}" class="${f.field === field ? `on v s-${f.state}` : ""}">${esc(fieldZh(f.field))}</button>`).join("")}</div>` : ""}
      ${body}
      ${ledgerNotes(run)}`;
    if (swap) enter([mainEl], { y: 10, duration: 0.35 });
  }

  function mailBlock(run) {
    const em = store.s.emails[run.email_id];
    const body = (em?.body_text || em?.body || "").trim();
    const token = run.email_id;
    if (!body) {
      const late = setTimeout(() => {
        const el = $("#pilot-mail", mainEl);
        if (!el || el.dataset.filled === "1" || el.dataset.token !== token) return;
        el.innerHTML = sourceWaitHtml({ slow: true });
      }, 5000);
      store.getEmail(run.email_id).then((got) => {
        clearTimeout(late);
        const el = $("#pilot-mail", mainEl);
        if (!el || runId !== run.run_id || el.dataset.token !== token) return;
        const text = (got?.body_text || got?.body || "").trim();
        el.classList.remove("is-wait");
        if (!text) {
          el.innerHTML = `<span class="muted">Source unavailable. Field evidence stays in Court; close this mail as CLEAR or HOLD.</span>`;
          return;
        }
        el.dataset.filled = "1";
        el.textContent = text;
      });
      return `
      <div>
        <div class="section-title"><h3>Source mail</h3><small>${esc(run.email_id)}</small></div>
        <div class="pilot-mail is-wait" id="pilot-mail" data-token="${esc(token)}">${sourceWaitHtml()}</div>
      </div>`;
    }
    return `
      <div>
        <div class="section-title"><h3>Source mail</h3><small>${esc(run.email_id)}</small></div>
        <pre class="pilot-mail" id="pilot-mail" data-filled="1">${esc(body)}</pre>
      </div>`;
  }

  function caseButtons() {
    return `
      <div class="decide-row">
        <button type="button" class="btn btn-lg btn-clear" data-case-verdict="CLEAR" ${deciding ? "disabled" : ""}>Release · CLEAR</button>
        <button type="button" class="btn btn-lg btn-hold" data-case-verdict="HOLD" ${deciding ? "disabled" : ""}>Stop · HOLD</button>
        <button type="button" class="btn" data-court>Court record</button>
        <button type="button" class="btn" data-detail>Case detail</button>
      </div>`;
  }

  function fieldHint(c, reasons) {
    if ((c.failure_codes || []).length) {
      const hits = (c.failure_codes || []).filter((x) => x !== "CHAOS_INJECTED").map((x) => failureZh(x));
      return `<p class="pilot-hint">This mail has no SI/BL pair to teach — ${hits.length ? esc(hits.join(", ")) : "the pipeline broke before a compare"}. Close it as CLEAR or HOLD. Ledger only stores a pair of writings, so smash/broken cases stay here until a human closes them.${c.degraded ? " Stamped DEGRADED: extract ran rules-only." : ""}</p>
        <div class="decide-row"><button type="button" class="btn" data-ledger>Open Ledger <span class="arrow">→</span></button></div>`;
    }
    if (!reasons.length) {
      return `<p class="pilot-hint">No pair left to lock. Close the mail as CLEAR or HOLD, or open the Ledger to see rules already taught.</p>
        <div class="decide-row"><button type="button" class="btn" data-ledger>Open Ledger <span class="arrow">→</span></button></div>`;
    }
    return "";
  }

  function caseStamp(s) {
    const clear = s.verdict === "CLEAR";
    const run = store.runById(s.runId);
    const draft = run?.payload?.card?.reply_draft || "";
    return `
      <div class="rule-stamp">
        <div class="seal">${clear ? "OK" : "HOLD"}</div>
        <div>
          <div>You closed this mail as <b>${esc(s.verdict)}</b>. It left the Pilot queue${s.released.length ? `; queue <strong>${s.queueBefore}</strong> → <strong style="color:var(--clear)">${s.queueAfter}</strong>` : ""}.</div>
          <div class="pilot-hint" style="margin-top:.5rem">Header counts move with it: Pilot down, ${clear ? "CLEAR" : "HOLD"} up. The model did not sit on the bench.</div>
        </div>
      </div>
      ${draft ? `<div class="section-title" style="margin-top:1.2rem"><h3>Outbox reply</h3><small>DRAFT · never auto-sent</small></div><pre class="pilot-mail">${esc(draft)}</pre>` : ""}
      <div class="decide-row">
        <button type="button" class="btn btn-primary" data-board>Back to Board <span class="arrow">→</span></button>
        <button type="button" class="btn" data-ledger>Open Ledger</button>
        <button type="button" class="btn" data-detail>Case detail</button>
      </div>`;
  }

  function decideBlock(fv) {
    const L = fv.charge.left;
    const R = fv.charge.right;
    const [dl, dr] = diffChars(L.raw_value, R.raw_value);
    const conf = confidenceOf(fv);
    const similar = store.s.runs.filter((r) => r.run_id !== runId && orderedFields(r).some((f) => f.field === fv.field && f.charge && sameKey(f.charge, fv.charge)));
    return `
      <div>
        <div class="section-title"><h3>${esc(fieldZh(fv.field))} <span class="muted" style="font-weight:400;font-size:.8rem">${esc(fieldEn(fv.field))} · ${esc(RISK[fv.risk_level] || "")} risk · exposure ${fmtUsd(fv.exposure_usd)}</span></h3><small>Confidence ${conf != null ? Math.round(conf * 100) : "-"}%</small></div>
        <div class="evidence-split">
          ${pane("SI", L, dl)}
          ${pane("BL", R, dr)}
        </div>
        <p class="rationale" style="margin-top:.7rem">${fv.state === "UNCERTAIN"
          ? `Defence tried ${(fv.pleas || []).length} strategies and none held, but confidence is too low to hold. Treat as same or confirm the discrepancy — that pair is written to the Ledger.`
          : `The court already called this a mismatch. Confirm it (or treat as same) to lock the pair into the Ledger so later mail reuses the ruling.`}</p>
        ${similar.length ? `<p class="pilot-hint">Locking this writes a Ledger rule and immediately replays <b style="color:var(--text)">${similar.length}</b> historical cases with the same writing.</p>` : `<p class="pilot-hint">Treat as same / Confirm discrepancy writes the first Ledger rule. CLEAR / HOLD above only closes this mail.</p>`}
      </div>
      <div class="decide-row">
        <button type="button" class="btn btn-lg btn-clear" data-decide="accept_as_match" ${deciding ? "disabled" : ""}>Lock in Ledger · same ✓</button>
        <button type="button" class="btn btn-lg btn-hold" data-decide="confirm_mismatch" ${deciding ? "disabled" : ""}>Lock in Ledger · different ✗</button>
        <button type="button" class="btn" data-ledger>Open Ledger</button>
        <button type="button" class="btn" data-court>Court record</button>
        <button type="button" class="btn" data-detail>Case detail</button>
      </div>`;
  }

  function pane(side, v, diff) {
    const ev = v.evidence || {};
    return `<div class="evidence-pane">
      <div class="label">${side}</div>
      <div class="val">${renderDiff(diff)}</div>
      <div class="src"><span class="chip">${esc({ ocr: "OCR scan", email_body: "Email body", text: "Text", vision: "Vision model" }[ev.source] || ev.source || "Text")}</span>${ev.attachment_name ? `<span class="chip mono">${esc(ev.attachment_name)}</span>` : ""}<span class="conf ${v.confidence < 0.75 ? "low" : ""}"><i style="--p:${v.confidence}"></i>${Math.round(v.confidence * 100)}%</span></div>
    </div>`;
  }

  function stampBlock(s) {
    const rule = s.rule;
    const acc = rule?.decision === "accept_as_match";
    return `
      <div class="rule-stamp">
        <div class="seal">${acc ? "≡" : "≠"}</div>
        <div>
          <div>${rule ? `Rule <b>#${shortId(rule.rule_id)}</b> locked: “${esc(rule.left_pattern)}” ${acc ? "treated as same" : "confirmed discrepancy"} “${esc(rule.right_pattern)}”` : "Ruling recorded (no rule generated)"}</div>
          <div class="replay" style="margin-top:.4rem">Replay of history → <strong id="replay-n" data-value="0">0</strong> cases rewritten${s.released.length ? `; queue <strong>${s.queueBefore}</strong> → <strong style="color:var(--clear)">${s.queueAfter}</strong>` : ""}</div>
          ${s.released.length ? `<div class="affected">${s.released.map((id) => { const r = store.runById(id); const c = card(r || {}); return `<span>#${shortId(id)} ${esc(c.subject || "")} <b>→ ${c.verdict || ""}</b> <button type="button" class="btn btn-sm" data-open-run="${esc(id)}">Open</button></span>`; }).join("")}</div>` : ""}
          <div class="pilot-hint" style="margin-top:.5rem">Every later automatic ruling on the same field will cite “rule locked by ${esc(rule?.created_by || "pilot")} on #${shortId(rule?.source_case_id || "")}”.</div>
        </div>
      </div>
      <div class="decide-row">
        <button type="button" class="btn btn-primary" data-ledger>See this rule on the Ledger <span class="arrow">→</span></button>
        <button type="button" class="btn" data-court>See its court now</button>
        <button type="button" class="btn" data-detail>Case detail</button>
      </div>`;
  }

  function ledgerNotes(run) {
    const ruled = orderedFields(run).filter((f) => ledgerRef(f));
    if (!ruled.length) return "";
    return `<div>
      <div class="section-title"><h3>Fields already ruled by a ledger rule</h3><small>RULE SOURCE</small></div>
      ${ruled.map((f) => { const ref = ledgerRef(f); const rule = store.ruleById(ref.ruleId); return `<div class="rule-src s-${f.state}" style="margin-bottom:.4rem"><b style="color:var(--v)">${esc(fieldZh(f.field))} · ${f.state}</b> · from ${esc(rule?.created_by || "operator")} on case <code>#${shortId(rule?.source_case_id || ref.ruleId)}</code>, rule <code>#${shortId(ref.ruleId)}</code>${ref.replayed ? " (rewritten on replay)" : ""}</div>`; }).join("")}
    </div>`;
  }

  async function decideCase(verdict) {
    const run = store.runById(runId);
    if (!run || deciding) return;
    deciding = true;
    $$("[data-case-verdict], [data-decide]", mainEl).forEach((b) => { b.disabled = true; });
    pulse($(`[data-case-verdict="${verdict}"]`, mainEl), 1.1);
    try {
      const out = await store.setVerdict({
        caseId: run.case_id || run.run_id,
        verdict,
      });
      lastStamp = {
        kind: "case",
        runId: run.run_id,
        verdict,
        released: out.released,
        queueBefore: out.queue_before,
        queueAfter: out.queue_after,
      };
      ctx.scene.setMood(verdict === "CLEAR" ? "clear" : "hold");
      const nodes = out.released.map((id) => $(`.queue-item[data-run="${id}"]`, queueEl)).filter(Boolean);
      if (nodes.length) await collapseOut(nodes, { stagger: 0.09 });
      pickDefaults();
      renderQueue();
      pulse($("#qn", root), 1.25);
      renderMain(true);
      ctx.toast(`Mail → ${verdict}. Queue ${out.queue_before} → ${out.queue_after}`, "ok", 5000);
    } catch (e) {
      ctx.toast(`Ruling failed: ${e.message}`, "err");
      renderMain();
    } finally {
      deciding = false;
    }
  }

  async function decide(decision) {
    const run = store.runById(runId);
    const fv = run && orderedFields(run).find((f) => f.field === field && f.charge);
    if (!fv || deciding) return;
    deciding = true;
    $$("[data-decide]", mainEl).forEach((b) => { b.disabled = true; });
    const btn = $(`[data-decide="${decision}"]`, mainEl);
    pulse(btn, 1.1);
    try {
      const out = await store.decide({
        caseId: run.case_id || run.run_id,
        field: fv.field,
        decision,
        left: fv.charge.left.raw_value,
        right: fv.charge.right.raw_value,
      });
      lastStamp = { runId: run.run_id, rule: out.rule, replay: out.replay, released: out.released, queueBefore: out.queue_before, queueAfter: out.queue_after };
      ctx.scene.setMood(decision === "accept_as_match" ? "clear" : "hold");
      const nodes = out.released.map((id) => $(`.queue-item[data-run="${id}"]`, queueEl)).filter(Boolean);
      await collapseOut(nodes, { stagger: 0.09 });
      renderQueue();
      pulse($("#qn", root), 1.25);
      renderMain(true);
      const n = $("#replay-n", mainEl);
      if (n) countTo(n, out.replay?.updated || 0, { duration: 0.8 });
      if (out.released.length) {
        ctx.toast(`Queue ${out.queue_before} → ${out.queue_after}: replay rewrote ${out.replay?.updated || 0} historical cases`, "ok", 6000);
      } else {
        ctx.toast(out.rule ? `Rule #${shortId(out.rule.rule_id)} written to the ledger` : "Ruling recorded", "ok");
      }
    } catch (e) {
      ctx.toast(`Ruling failed: ${e.message}`, "err");
      renderMain();
    } finally {
      deciding = false;
    }
  }

  function renderAll() { pickDefaults(); renderQueue(false); renderMain(); }
  renderAll();

  return {
    update(_s, reason) {
      if (reason === "busy" || reason === "autonomy") return;
      if (deciding) {
        if (reason === "decide" && lastStamp) renderMain();
        return;
      }
      if (reason === "decide") {
        pickDefaults();
        renderQueue();
        if (lastStamp) renderMain();
        return;
      }
      pickDefaults();
      renderQueue();
      renderMain();
    },
    setParams(p) { if (p.run) runId = p.run; if (p.field) field = p.field; lastStamp = null; pickDefaults(); renderQueue(); renderMain(true); },
    destroy() {},
  };
}

function sameKey(a, b) {
  const k = (c) => [String(c.left?.raw_value || "").toUpperCase().split(/\s+/).join(" "), String(c.right?.raw_value || "").toUpperCase().split(/\s+/).join(" ")].sort().join("||");
  return k(a) === k(b);
}
