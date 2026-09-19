// ⑤ Chaos — four red buttons. The point is not that the system survives; it is
// that it raises its hand honestly: detect → flag → hand to pilot, with a
// DEGRADED tag whenever the LLM was cut.
import { store as bridgeStore } from "../lib/store.js?v=52";
import { esc, $, $$, on, shortId, sleep } from "../lib/dom.js";
import { gsap, reduced, enter, shake, pulse, tiltify } from "../lib/motion.js";
import { CHAOS, failureZh, VERDICT, scoutZh } from "../lib/copy.js";
import { pilotReasons } from "../lib/case.js";

export function mount(root, ctx) {
  const store = ctx.store || bridgeStore;
  let running = false;

  root.innerHTML = `
    <section class="view">
      <div class="view-head">
        <div>
          <h1>Chaos <small>SMASH THE STAGE</small></h1>
          <p>Four ways to smash the stage. Watch whether the system <b>raises its hand honestly</b> when it detects a fault, instead of inventing an answer. Every button really re-runs the pipeline.</p>
        </div>
        <div class="view-actions"><button type="button" class="btn btn-outline-hold" id="chaos-reset">Refresh board</button></div>
      </div>
      <div class="chaos-grid" id="chaos-grid">
        ${CHAOS.map((c) => `
          <button type="button" class="chaos-btn" data-chaos="${c.id}">
            <span class="code">CHAOS · ${esc(c.expect)}</span>
            <span class="t">${esc(c.title)}</span>
            <span class="d">${esc(c.desc)}</span>
            <span class="glyph" aria-hidden="true">${esc(c.glyph)}</span>
          </button>`).join("")}
      </div>
      <div class="chaos-stage">
        <div class="panel steps" id="steps">
          ${step(1, "Detecting", "Inject the fault and re-run Scout → extract → court.")}
          ${step(2, "Anomaly found", "The pipeline reports a failure code at some step, instead of guessing onward.")}
          ${step(3, "Hand to human", "The result card stops at Pilot with the failure code. No release. No hold.")}
        </div>
        <div class="panel result-slot" id="result">
          <div class="placeholder"><b>Nothing smashed yet</b><span>Press any of the red buttons.</span></div>
        </div>
      </div>
      <div class="chaos-foot">
        <span class="muted" style="font-size:.85rem">Refresh reloads the official board. Hosted Postgres is never wiped.</span>
        <span class="muted" style="font-size:.85rem" id="chaos-count"></span>
      </div>
    </section>`;

  const grid = $("#chaos-grid", root);
  const stepsEl = $("#steps", root);
  const resultEl = $("#result", root);

  const unTilt = tiltify(grid, ".chaos-btn", { max: 6 });
  on(grid, "click", ".chaos-btn", (_, el) => smash(el.dataset.chaos, el));
  $("#chaos-reset", root).addEventListener("click", async () => {
    if (running) return;
    const b = $("#chaos-reset", root);
    b.disabled = true;
    try {
      await store.reset();
      ctx.scene.setMood("calm");
      resetSteps();
      resultEl.innerHTML = `<div class="placeholder"><b>Refreshed</b><span>Official ledger kept. Smash a button to inject a fault on a live case.</span></div>`;
      ctx.toast("Board refreshed", "ok");
    } catch (e) { ctx.toast(`Reset failed: ${e.message}`, "err"); }
    b.disabled = false;
  });
  on(resultEl, "click", "[data-detail]", (_, el) => ctx.openDetail(el.dataset.detail));
  on(resultEl, "click", "[data-pilot]", (_, el) => ctx.navigate("pilot", { run: el.dataset.pilot }));

  function step(n, title, desc) {
    return `<div class="step" data-step="${n}"><div class="n">${n}</div><div class="txt"><b>${title}</b><span>${desc}</span><div class="extra"></div></div></div>`;
  }

  function resetSteps() {
    $$(".step", stepsEl).forEach((s) => { s.className = "step"; $(".extra", s).innerHTML = ""; });
  }

  function setStep(n, cls, extraHtml) {
    const s = $(`.step[data-step="${n}"]`, stepsEl);
    if (!s) return;
    s.classList.remove("active");
    s.classList.add(cls);
    if (extraHtml != null) $(".extra", s).innerHTML = extraHtml;
  }
  function activate(n, extraHtml) {
    const s = $(`.step[data-step="${n}"]`, stepsEl);
    s.classList.add("active");
    if (extraHtml != null) $(".extra", s).innerHTML = extraHtml;
    if (gsap && !reduced) gsap.fromTo(s, { x: -6, opacity: 0.6 }, { x: 0, opacity: 1, duration: 0.4 });
  }

  async function smash(type, btn) {
    if (running) return;
    running = true;
    const meta = CHAOS.find((c) => c.id === type);
    $$(".chaos-btn", grid).forEach((b) => { b.disabled = true; });
    pulse(btn, 1.08);
    shake(document.querySelector(".shell"), 5);
    ctx.scene.setMood("chaos");
    ctx.scene.shock();
    resetSteps();
    resultEl.innerHTML = `<div class="placeholder"><b>${esc(meta.title)}</b><span>Re-running the pipeline…</span><div class="scanline" style="width:220px"><i id="scan"></i></div></div>`;
    if (gsap && !reduced) gsap.to("#scan", { left: "65%", duration: 0.7, yoyo: true, repeat: -1, ease: "sine.inOut" });

    activate(1, `<div class="scanline"><i id="scan1"></i></div>`);
    if (gsap && !reduced) gsap.to("#scan1", { left: "65%", duration: 0.6, yoyo: true, repeat: -1, ease: "sine.inOut" });

    const started = performance.now();
    let payload;
    let err;
    try {
      payload = await store.chaos(type);
    } catch (e) { err = e; }
    await sleep(Math.max(0, 900 - (performance.now() - started)));

    if (err) {
      setStep(1, "alarm", `<span class="chip danger">Request failed: ${esc(err.message)}</span>`);
      resultEl.innerHTML = `<div class="error-panel"><span>The backend did not answer this smash. <code>${esc(err.message)}</code></span></div>`;
      $$(".chaos-btn", grid).forEach((b) => { b.disabled = false; });
      running = false;
      return;
    }

    const card = payload.card || {};
    const codes = (card.failure_codes || []).filter((c) => c !== "CHAOS_INJECTED");
    setStep(1, "done", `<span class="chip">Pipeline finished · ${Math.round(performance.now() - started)} ms</span>`);
    await sleep(350);
    activate(2);
    await sleep(500);
    setStep(2, codes.length ? "alarm" : "done", codes.length
      ? `<div class="codes">${codes.map((c) => `<span class="chip danger" title="${esc(failureZh(c))}">${esc(c)}</span>`).join("")}</div>`
      : `<span class="chip">No failure code</span>`);
    await sleep(500);
    activate(3);
    await sleep(450);
    const v = card.verdict;
    setStep(3, v === "PILOT" ? "pilot" : "done", `<span class="chip v v-${v}">${v} · ${esc(VERDICT[v]?.zh || "")}</span>${card.degraded ? `<span class="degraded" style="margin-left:.4rem">DEGRADED · RULES ONLY</span>` : ""}`);

    ctx.scene.setMood(v === "PILOT" ? "pilot" : v === "HOLD" ? "hold" : "clear");
    const reasons = pilotReasons({ payload, verdict: v, run_id: payload.run_id, _uncertain: [] });
    resultEl.innerHTML = `
      <div class="result-card v-${v}">
        <div class="meta-row">
          <span class="verdict-tag" style="color:var(--v)">${v}<em>${esc(VERDICT[v]?.zh || "")}</em></span>
          ${card.degraded ? `<span class="degraded">DEGRADED · rules only</span>` : ""}
          <span class="chip">${esc(scoutZh(card.scout?.label))}${card.scout?.route ? ` · ${esc(card.scout.route)}` : ""}</span>
        </div>
        <h3>${esc(card.subject || card.email_id || "(empty email)")}</h3>
        <div class="codes">${codes.map((c) => `<span class="chip danger">${esc(failureZh(c))}</span>`).join("") || `<span class="chip">No failure code</span>`}</div>
        <p class="dim" style="font-size:.9rem">${honestLine(type, card, reasons)}</p>
        <div class="decide-row">
          ${v === "PILOT" ? `<button type="button" class="btn btn-pilot" data-pilot="${esc(payload.run_id)}">See it on Pilot <span class="arrow">→</span></button>` : ""}
          <button type="button" class="btn" data-detail="${esc(payload.run_id)}">Case detail</button>
        </div>
      </div>`;
    enter([resultEl.firstElementChild], { y: 14, duration: 0.5 });

    $("#chaos-count", root).textContent = `Smashed ${store.s.runs.filter((r) => (r.payload?.card?.failure_codes || []).includes("CHAOS_INJECTED")).length} time(s) this round`;
    ctx.toast(codes.length ? `Hand raised: ${codes.map(failureZh).join(", ")} → ${v}` : `Result ${v}`, v === "PILOT" ? "warn" : "ok");
    $$(".chaos-btn", grid).forEach((b) => { b.disabled = false; });
    running = false;
  }

  function honestLine(type, card, reasons) {
    const degraded = card.degraded ? " The result card is stamped DEGRADED. It did not pretend the LLM was still there." : "";
    switch (type) {
      case "attachment_corrupt": return `The attachment will not open. The system did not cobble a BL out of the email body. It reported ATTACHMENT_CORRUPT and parked the case at Pilot.${degraded}`;
      case "ocr_garble": return `The scan was soiled. OCR corrections are allowed only on OCR sources (ADR-003). Below the confidence floor it will not rule, so it hands to a human.${degraded}`;
      case "llm_timeout": return `The model was cut. Scout and extract fall back to rules-only. What they can judge, they judge. What they cannot, they raise a hand.${degraded || " The result card should carry a DEGRADED stamp."}`;
      case "empty_email": return `Subject, body, and attachments are all blank. With no evidence, the system refuses any field conclusion: EMPTY_EMAIL → PILOT.${degraded}`;
      default: return reasons.map((r) => r.text).join("; ");
    }
  }

  return { update() {}, destroy() { unTilt?.(); } };
}
