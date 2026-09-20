// ② Court — prosecutor files a charge, the defender tries each deterministic
// strategy one by one, the judge rules. A GSAP timeline gives it courtroom
// pacing: slow enough to read, fast enough to keep the room.
import { store as bridgeStore } from "../lib/store.js?v=59";
import { esc, $, $$, on, shortId, fmtUsd, diffChars, renderDiff } from "../lib/dom.js?v=59";
import { gsap, reduced, enter } from "../lib/motion.js";
import { fieldZh, fieldEn, strategyZh, STRATEGIES, RISK, STATE } from "../lib/copy.js";
import { card, courtFields, orderedFields, confidenceOf, ledgerRef } from "../lib/case.js?v=59";
import { present, effectiveState } from "../lib/field-display.js?v=59";

const STRATEGY_ORDER = Object.keys(STRATEGIES).filter((k) => k !== "ledger");

function hydratePleas(fv) {
  return (fv?.pleas || []).map((p, i) => {
    const strategy = p.strategy || STRATEGY_ORDER[i] || "";
    return {
      ...p,
      strategy,
      argument: p.argument || STRATEGIES[strategy]?.hint || "",
    };
  });
}

export function mount(root, ctx, params = {}) {
  const store = ctx.store || bridgeStore;
  let runId = params.run || null;
  let field = params.field || null;
  let tl = null;

  root.innerHTML = `
    <section class="view">
      <div class="view-head">
        <div>
          <h1>Court <small>COURTROOM</small></h1>
          <p>Prosecution charges that two documents disagree. Defence tries each deterministic strategy. The judge rules in three states. The LLM is not in the room: it extracts. It never sits on the bench.</p>
        </div>
      </div>
      <div class="court-layout">
        <aside class="court-rail">
          <div class="panel panel-pad">
            <div class="section-title"><h3>Cases</h3><small id="case-count"></small></div>
            <div class="case-list" id="case-list"></div>
          </div>
          <div class="panel panel-pad">
            <div class="section-title"><h3>Contested fields</h3><small>CHARGES</small></div>
            <div class="field-tabs" id="field-tabs"></div>
          </div>
        </aside>
        <div class="court-stage panel" id="stage"></div>
      </div>
    </section>`;

  const caseList = $("#case-list", root);
  const fieldTabs = $("#field-tabs", root);
  const stage = $("#stage", root);

  on(caseList, "click", ".case-item", (_, el) => { runId = el.dataset.run; field = null; renderAll(true); });
  on(fieldTabs, "click", ".field-tab:not(.quiet)", (_, el) => { field = el.dataset.field; renderAll(true); });
  on(stage, "click", "[data-replay]", () => play());
  on(stage, "click", "[data-next]", (_, el) => { field = el.dataset.next; renderAll(true); });
  on(stage, "click", "[data-pilot]", (_, el) => ctx.navigate("pilot", { run: runId, field: el.dataset.pilot }));
  on(stage, "click", "[data-detail]", () => ctx.openDetail(runId));
  on(stage, "click", "[data-pick]", (_, el) => { runId = el.dataset.pick; renderAll(true); });

  function candidates() {
    return store.s.runs.filter((r) => courtFields(r).length);
  }

  function pickDefaults() {
    const list = candidates();
    if (!list.find((r) => r.run_id === runId)) {
      const pref = list.find((r) => card(r).verdict === "PILOT" && courtFields(r).some((f) => f.state === "UNCERTAIN"))
      || list.find((r) => card(r).verdict === "HOLD")
      || list.find((r) => card(r).verdict === "PILOT")
      || list[0];
      runId = pref?.run_id || null;
    }
    const run = store.runById(runId);
    if (!run) return;
    const fs = courtFields(run);
    if (!fs.find((f) => f.field === field)) {
      const pref = fs.find((f) => f.state === "UNCERTAIN") || fs.find((f) => f.state === "MISMATCH") || fs[0];
      field = pref?.field || null;
    }
  }

  function renderRail() {
    const list = candidates();
    $("#case-count", root).textContent = `${list.length} in dispute`;
    caseList.innerHTML = list.length ? list.map((r) => {
      const c = card(r);
      return `<button type="button" class="case-item v-${c.verdict} ${r.run_id === runId ? "on" : ""}" data-run="${esc(r.run_id)}"><i></i><span><span>${esc(c.subject || r.email_id)}</span><small>${c.verdict} · #${shortId(r.run_id)} · ${courtFields(r).length} charges</small></span></button>`;
    }).join("") : `<p class="muted" style="font-size:.85rem">No disputed cases yet. Load the official inbox on the Board first.</p>`;
    const run = store.runById(runId);
    const all = run ? orderedFields(run) : [];
    const cf = run ? courtFields(run) : [];
    fieldTabs.innerHTML = run ? all.map((f) => {
      const inCourt = cf.includes(f);
      const st = effectiveState(f);
      return `<button type="button" class="field-tab s-${st} ${inCourt ? "" : "quiet"} ${f.field === field ? "on" : ""}" data-field="${esc(f.field)}" ${inCourt ? "" : "tabindex=-1"}><span>${esc(fieldZh(f.field))}</span><span class="st">${inCourt ? (STATE[st] || st) : "uncontested"}</span></button>`;
    }).join("") : "";
  }

  function renderStage() {
    const run = store.runById(runId);
    const fv = run ? courtFields(run).find((f) => f.field === field) : null;
    if (!run || !fv) {
      stage.innerHTML = `<div class="empty"><h3>Court is empty</h3><p>Pick a case on the left, or go back to the Board and seed the inbox. Court only sits when SI and BL still disagree after format (caps, locode, labels). Matching fields do not need a hearing.</p></div>`;
      return;
    }
    const c = card(run);
    const L = fv.charge?.left || { raw_value: "-", confidence: 1 };
    const R = fv.charge?.right || { raw_value: "-", confidence: 1 };
    const lShow = present(fv.field, L.raw_value);
    const rShow = present(fv.field, R.raw_value);
    const [dl, dr] = diffChars(lShow.text || L.raw_value, rShow.text || R.raw_value);
    if ((fv.pleas || []).some((p) => !p.strategy)) store.hydrateRun?.(runId);
    const pleas = hydratePleas(fv);
    const ref = ledgerRef(fv);
    const rule = ref ? store.ruleById(ref.ruleId) : null;
    const conf = confidenceOf(fv);
    const cf = courtFields(run);
    const idx = cf.indexOf(fv);
    const next = cf[idx + 1];

    const verdictText = verdictCopy(fv, rule, conf);

    stage.innerHTML = `
      <div class="court-progress"><i id="progress"></i></div>
      <div class="court-controls">
        <span class="muted" style="margin-right:auto;font-size:.8rem">#${shortId(run.run_id)} · ${esc(c.subject || run.email_id)} · ${idx + 1} of ${cf.length}</span>
        <button type="button" class="btn btn-sm" data-replay>Replay <kbd style="opacity:.6;margin-left:.3rem">R</kbd></button>
        <button type="button" class="btn btn-sm" data-detail>Case detail</button>
      </div>

      <div class="charge" id="charge">
        <div class="who">Prosecution · PROSECUTOR</div>
        <div class="charge-line">SI writes <b>${esc(lShow.text || L.raw_value)}</b>${lShow.locode ? ` <span class="locode">${esc(lShow.locode)}</span>` : ""}. BL writes <b>${esc(rShow.text || R.raw_value)}</b>${rShow.locode ? ` <span class="locode">${esc(rShow.locode)}</span>` : ""}. Charge: <b>${esc(fieldZh(fv.field))}</b> does not match.</div>
        <div class="versus">
          <div class="side" id="side-l"><small>SI · Shipping instruction</small><b>${renderDiff(dl)}${lShow.locode ? ` <span class="locode">${esc(lShow.locode)}</span>` : ""}</b><span class="conf ${L.confidence < 0.75 ? "low" : ""}"><i style="--p:${L.confidence}"></i>${Math.round(L.confidence * 100)}%</span></div>
          <div class="vs" id="vs">VS</div>
          <div class="side" id="side-r"><small>BL · Bill of lading</small><b>${renderDiff(dr)}${rShow.locode ? ` <span class="locode">${esc(rShow.locode)}</span>` : ""}</b><span class="conf ${R.confidence < 0.75 ? "low" : ""}"><i style="--p:${R.confidence}"></i>${Math.round(R.confidence * 100)}%</span></div>
        </div>
      </div>

      <div class="charge">
        <div class="who def">Defence · DEFENDER <span class="muted" style="letter-spacing:0;font-weight:400">· ${pleas.length} deterministic strategies, tried in order</span></div>
        <div class="pleas" id="pleas">
          <div class="rail"><i id="rail"></i></div>
          ${pleas.map((p, i) => `
            <div class="plea ${p.accepted ? "ok" : "no"}" data-i="${i}">
              <span class="idx">${String(i + 1).padStart(2, "0")}</span>
              <div class="body">
                <div class="name">${esc(strategyZh(p.strategy))}<code>${esc(p.strategy)}</code></div>
                <div class="arg">${esc(p.argument || STRATEGIES[p.strategy]?.hint || "")}</div>
                ${p.transformed_left != null || p.transformed_right != null ? `<div class="xform"><b>${esc(present(fv.field, p.transformed_left ?? L.raw_value).text || p.transformed_left)}</b><span class="ar">${p.accepted ? "≡" : "≠"}</span><b>${esc(present(fv.field, p.transformed_right ?? R.raw_value).text || p.transformed_right)}</b></div>` : ""}
              </div>
              <span class="stamp">${p.accepted ? "✓ holds" : "✗ fails"}</span>
            </div>`).join("")}
          ${!pleas.length ? `<div class="plea no" data-i="0" style="visibility:visible;opacity:.7"><span class="idx">00</span><div class="body"><div class="name">No strategy applies</div><div class="arg">${ref ? "This field was ruled by a ledger rule. Defence has nothing to say." : "No strategy claims it can explain this difference."}</div></div></div>` : ""}
        </div>
      </div>

      <div class="verdict-row s-${fv.state}" id="verdict">
        <div class="gavel" id="gavel">JUDGE</div>
        <div class="txt">
          <div class="who judge" style="font-family:var(--font-mono);font-size:.7rem;letter-spacing:.18em;color:var(--pilot)">Judge · JUDGE</div>
          <b>${verdictText.title}</b>
          <span>${verdictText.body}</span>
          <span class="exp">${esc(RISK[fv.risk_level] || fv.risk_level)}-risk field · exposure ${fmtUsd(fv.exposure_usd)} · ${esc(fv.advise || "")}</span>
        </div>
        <div id="verdict-actions" style="display:grid;gap:.5rem;justify-items:end">
          ${fv.state === "UNCERTAIN" ? `<button type="button" class="btn btn-pilot" data-pilot="${esc(fv.field)}">Hand to a pilot <span class="arrow">→</span></button>` : ""}
          ${next ? `<button type="button" class="btn btn-sm" data-next="${esc(next.field)}">Next: ${esc(fieldZh(next.field))} <span class="arrow">→</span></button>` : ""}
        </div>
      </div>
      <div class="court-foot">
        <span>Ruling: any strategy holds → MATCH; all fail and confidence ≥ ${Math.round((store.s.autonomy?.thresholds?.match_confidence_floor ?? 0.92) * 100)}% → MISMATCH; else UNCERTAIN → Pilot.</span>
        <span>${ref ? `Ledger rule #${shortId(ref.ruleId)}` : "No ledger rule hit"}</span>
      </div>`;

    play();
  }

  function verdictCopy(fv, rule, conf) {
    const ref = ledgerRef(fv);
    if (ref) {
      const who = rule ? `${rule.created_by} on case #${shortId(rule.source_case_id)}` : "a pilot";
      return fv.state === "MATCH"
        ? { title: "Ledger rule: treat as match", body: `${who} already ruled these two writings equivalent (rule #${shortId(ref.ruleId)}${ref.replayed ? ", this case was rewritten on replay" : ""}). Defence need not speak.` }
        : { title: "Ledger rule: confirm mismatch", body: `${who} already ruled these two writings a real discrepancy (rule #${shortId(ref.ruleId)}).` };
    }
    if (fv.state === "MATCH") {
      return { title: "Defence holds. Not a discrepancy.", body: `${strategyZh(fv.winning_strategy)} normalised both sides to one value. The field is released. No false alarm.` };
    }
    if (fv.state === "MISMATCH") {
      return { title: "Defence fails. Real discrepancy.", body: `${(fv.pleas || []).length} strategies all failed, and extract confidence ${conf != null ? Math.round(conf * 100) + "%" : "is sufficient"} — enough to hold.` };
    }
    return { title: "Evidence is thin. Hand to Pilot.", body: `Every defence failed, but confidence is only ${conf != null ? Math.round(conf * 100) + "%" : "-"}${fv.charge?.left?.evidence?.source === "ocr" || fv.charge?.right?.evidence?.source === "ocr" ? " (OCR source)" : ""}, too low to hold. The system raised a hand instead of guessing.` };
  }

  function play() {
    if (tl) { tl.kill(); tl = null; }
    const run = store.runById(runId);
    const fv = run ? courtFields(run).find((f) => f.field === field) : null;
    if (!fv) return;
    const pleas = $$(".plea", stage);
    const verdict = $("#verdict", stage);
    const rail = $("#rail", stage);
    const progress = $("#progress", stage);
    const mood = fv.state === "MATCH" ? "clear" : fv.state === "MISMATCH" ? "hold" : "pilot";

    if (!gsap || reduced) {
      pleas.forEach((p) => { p.style.visibility = "visible"; p.style.display = "grid"; });
      verdict.style.visibility = "visible";
      if (rail) rail.style.transform = "none";
      if (progress) progress.style.transform = "none";
      ctx.scene.setMood(mood);
      return;
    }
    ctx.scene.setMood("court");
    stage.scrollTop = 0;
    $("#charge", stage)?.scrollIntoView({ block: "nearest" });
    gsap.set(pleas, { display: "none", visibility: "hidden", opacity: 0, x: -18 });
    gsap.set($$(".stamp", stage), { opacity: 0, scale: 2.2, rotate: -14 });
    gsap.set(verdict, { visibility: "hidden", opacity: 0, y: 24 });
    gsap.set(rail, { scaleY: 0 });
    gsap.set(progress, { scaleX: 0 });
    gsap.set($("#verdict-actions", stage), { opacity: 0 });

    tl = gsap.timeline({
      defaults: { ease: "power3.out" },
      onUpdate: () => gsap.set(progress, { scaleX: tl.progress() }),
    });
    tl.fromTo("#charge .who", { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.4 })
      .fromTo("#charge .charge-line", { opacity: 0, y: 14, filter: "blur(6px)" }, { opacity: 1, y: 0, filter: "blur(0px)", duration: 0.8 }, "-=0.15")
      .fromTo("#side-l", { opacity: 0, x: -40 }, { opacity: 1, x: 0, duration: 0.6 }, "-=0.35")
      .fromTo("#side-r", { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.6 }, "<")
      .fromTo("#vs", { scale: 0.4, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.5, ease: "back.out(2)" }, "-=0.3")
      .addLabel("defense", "+=0.45");

    const perPlea = 1.35;
    tl.to(rail, { scaleY: 1, duration: perPlea * Math.max(pleas.length, 1), ease: "none" }, "defense");
    pleas.forEach((p, i) => {
      const at = `defense+=${i * perPlea}`;
      tl.set(p, { display: "grid", visibility: "visible" }, at);
      tl.to(p, { opacity: 1, x: 0, duration: 0.45 }, at);
      const stamp = p.querySelector(".stamp");
      if (stamp) {
        tl.to(stamp, { opacity: 1, scale: 1, rotate: p.classList.contains("ok") ? -4 : 3, duration: 0.35, ease: "back.out(3)" }, `${at}+=0.55`);
        if (p.classList.contains("ok")) {
          tl.fromTo(p, { boxShadow: "0 0 0 0 rgba(65,217,143,0)" }, { boxShadow: "0 0 40px -6px rgba(65,217,143,0.55)", duration: 0.5 }, `${at}+=0.55`);
        } else {
          tl.to(p, { x: 4, duration: 0.05, yoyo: true, repeat: 3, ease: "none" }, `${at}+=0.55`);
        }
      }
    });

    tl.addLabel("ruling", `defense+=${pleas.length * perPlea + 0.5}`);
    tl.to(verdict, { visibility: "visible", opacity: 1, y: 0, duration: 0.7 }, "ruling")
      .fromTo("#gavel", { scale: 1.8, rotate: -35, y: -40 }, { scale: 1, rotate: 0, y: 0, duration: 0.55, ease: "bounce.out" }, "ruling+=0.1")
      .add(() => { ctx.scene.setMood(mood); if (fv.state !== "MATCH") ctx.scene.shock(); }, "ruling+=0.4")
      .fromTo(verdict, { boxShadow: "0 0 0 0 rgba(255,255,255,0)" }, { boxShadow: "0 0 60px -10px var(--v)", duration: 0.8 }, "ruling+=0.45")
      .to($("#verdict-actions", stage), { opacity: 1, duration: 0.5 }, "ruling+=0.9");
  }

  function renderAll(swap = false) {
    pickDefaults();
    renderRail();
    renderStage();
    if (swap) enter([stage], { y: 10, duration: 0.35 });
  }

  renderAll();

  const key = (e) => { if ((e.key === "r" || e.key === "R") && !e.metaKey && !e.ctrlKey && !/input|textarea/i.test(e.target.tagName)) play(); };
  addEventListener("keydown", key);

  return {
    update(_state, reason) {
      if (reason === "busy" || reason === "autonomy") return;
      const before = runId;
      pickDefaults();
      renderRail();
      if (before !== runId || !$("#verdict", stage)) renderStage();
    },
    setParams(p) { if (p.run) runId = p.run; if (p.field) field = p.field; renderAll(true); },
    destroy() { removeEventListener("keydown", key); if (tl) tl.kill(); },
  };
}
