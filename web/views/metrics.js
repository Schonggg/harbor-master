// ⑥ Metrics + autonomy dial — false alarms as the hero number, confusion matrix,
// field-level agreement, and a live what-if dial over the match-confidence floor.
import { store as bridgeStore } from "../lib/store.js?v=56";
import { esc, $, $$, on } from "../lib/dom.js?v=56";
import { enter, countTo } from "../lib/motion.js";
import { fieldZh, fieldEn, PRESETS } from "../lib/copy.js";
import { sevenFields } from "../lib/case.js?v=56";
import { SEVEN_FIELDS, effectiveState } from "../lib/field-display.js?v=56";

export function mount(root, ctx) {
  const store = ctx.store || bridgeStore;
  let floor = store.s.autonomy?.thresholds?.match_confidence_floor ?? 0.92;

  root.innerHTML = `
    <section class="view">
      <div class="view-head">
        <div>
          <h1>Metrics <small>METRICS</small></h1>
          <p>Top row is score-sheet discipline (rules we can prove). The mix and field bars below are this live 520 board. The dial previews a stricter or looser HOLD gate on the same evidence — apply it to move the header and Pilot queue.</p>
        </div>
      </div>
      <div class="kpi-grid" id="kpis"></div>
      <p class="muted desk-now" id="desk-now"></p>
      <div class="metrics-grid">
        <div class="panel panel-pad">
          <div class="section-title"><h3>This inbox, two contracts</h3><small>OFFICIAL SUBMISSION · BRIDGE DESK</small></div>
          <p class="muted" id="mix-line">Official categories and compare status versus the three-state desk the operator sees.</p>
          <div id="mix"></div>
        </div>
        <div class="panel panel-pad">
          <div class="section-title"><h3>Field-level agreement</h3><small>WHAT THE COURT DID ON THIS BOARD</small></div>
          <div class="fbars" id="fbars"></div>
          <div class="legend"><span class="s-MATCH"><i></i>Match</span><span class="s-MISMATCH"><i></i>Mismatch</span><span class="s-UNCERTAIN"><i></i>Review</span></div>
        </div>
      </div>
      <div class="panel panel-pad">
        <div class="section-title"><h3>HOLD strictness</h3><small>SAME EVIDENCE · CONFIDENCE GATE ONLY</small></div>
        <div class="dial-layout">
          <div class="dial-controls">
            <div class="dial-value"><b id="dial-v">${floor.toFixed(2)}</b><span>Same SI/BL evidence. Raise the floor and leftover mismatches with extract confidence below it leave HOLD and join Pilot.</span></div>
            <input type="range" class="dial" id="dial" min="0.60" max="0.98" step="0.01" value="${floor}" aria-label="Confidence floor" />
            <div class="dial-scale"><span style="--at:0">0.60 hold more</span><span style="--at:52.6316">0.80</span><span style="--at:100">0.98 hand more to humans</span></div>
            <div class="presets">${Object.entries(PRESETS).map(([k, p]) => `<button type="button" class="btn btn-sm" data-preset="${k}">${p.zh} · ${p.floor}</button>`).join("")}</div>
            <div class="dial-stats" id="dial-stats"></div>
            <div class="dial-actions">
              <button type="button" class="btn btn-primary" data-apply-floor>Apply to this desk</button>
              <button type="button" class="btn" data-restore-desk>Restore recorded 520</button>
            </div>
            <p class="muted" style="font-size:.8rem" id="dial-note"></p>
          </div>
          <div><svg class="curve" id="curve" viewBox="0 0 200 110" role="img" aria-label="Floor vs HOLD and Pilot counts"></svg></div>
        </div>
      </div>
      <details class="panel panel-pad metrics-fold" id="discipline-panel">
        <summary class="section-title"><h3>Score-sheet grid</h3><small>220 CELLS · OPEN IF A JUDGE ASKS HOW</small></summary>
        <p class="muted" id="disc-line">Every compare field, every format, every label. Equivalent writing must never defect.</p>
        <div class="matrix-wrap" id="fmt-matrix"></div>
        <div class="axis-note"><span>rows = seven compare fields</span><span>columns = txt / pdf / docx / xlsx</span></div>
        <p class="muted" id="ritual-line" style="margin-top:.8rem"></p>
      </details>
      <details class="panel panel-pad metrics-fold" id="robustness-panel">
        <summary class="section-title"><h3>Pipeline identity</h3><small>SAME PIPELINE · NO GROUND TRUTH IMPORT</small></summary>
        <p class="muted" id="robust-line">Checking whether two identical runs stay identical…</p>
        <div id="robust-seeds"></div>
      </details>
      <details class="panel panel-pad ops-panel metrics-fold" id="ops">
        <summary class="section-title"><h3>System</h3><small>HEALTH · STORAGE · KEYS · SUBMISSION</small></summary>
        <p class="muted" id="ops-line">Checking backend…</p>
        <div class="ops-actions">
          <button type="button" class="btn btn-sm" data-ops="export">Export submission</button>
          <button type="button" class="btn btn-sm" data-ops="submit">Submit to inbox</button>
          <button type="button" class="btn btn-sm" data-ops="full">Run full corpus</button>
          <button type="button" class="btn btn-sm" data-ops="backup">Backup DB</button>
        </div>
        <div class="ops-grid">
          <div>
            <div class="section-title" style="margin-top:1rem"><h3>Object storage</h3><small>LOCAL OR S3 / R2 / MINIO</small></div>
            <p class="muted" id="ops-storage">—</p>
            <div class="object-list" id="ops-objects"></div>
          </div>
          <div>
            <div class="section-title" style="margin-top:1rem"><h3>API keys</h3><small>HASHED AT REST · SHOWN ONCE</small></div>
            <div class="key-issue">
              <input type="text" id="key-name" maxlength="80" placeholder="Integration name" aria-label="API key name" />
              <button type="button" class="btn btn-sm" data-ops="issue-key">Issue key</button>
            </div>
            <div class="key-reveal" id="key-reveal" hidden></div>
            <div class="key-list" id="key-list"></div>
          </div>
        </div>
      </details>
    </section>`;

  const dial = $("#dial", root);
  dial.addEventListener("input", () => { floor = Number(dial.value); renderDial(); });
  on(root, "click", "[data-preset]", (_, el) => {
    const p = PRESETS[el.dataset.preset];
    if (!p) return;
    floor = p.floor;
    dial.value = floor;
    renderDial();
  });
  on(root, "click", "[data-apply-floor]", () => {
    const before = store.recordedCounts();
    const after = store.applyFloorToDesk(floor);
    ctx.toast(`Desk HOLD ${before.HOLD} → ${after.HOLD}, Pilot ${before.PILOT} → ${after.PILOT}. Header and Pilot follow. Official 520 is unchanged.`, "ok", 6000);
  });
  on(root, "click", "[data-restore-desk]", () => {
    const after = store.restoreRecordedDesk();
    ctx.toast(`Restored recorded desk: ${after.CLEAR} CLEAR · ${after.HOLD} HOLD · ${after.PILOT} PILOT.`, "ok", 5000);
    renderDial();
  });
  on(root, "click", "[data-ops]", async (_, el) => {
    const op = el.dataset.ops;
    el.disabled = true;
    try {
      if (op === "export") {
        const out = await store.exportSubmission();
        ctx.toast(`Wrote ${out.count} emails to ${out.path}`, "ok");
      } else if (op === "submit") {
        const out = await store.submitOfficial();
        ctx.toast(`Inbox scored ${out.count} emails`, "ok");
      } else if (op === "full") {
        const out = await store.runFull({ rulesOnly: true });
        ctx.toast(`Full run queued (${out.job_id || "ok"})`, "ok");
      } else if (op === "backup") {
        const out = await store.backup({ cloud: true });
        const where = out.object?.backend ? `${out.object.backend}:${out.object.key}` : out.path;
        ctx.toast(`Backup ${where}`, "ok");
        await loadOps();
      } else if (op === "issue-key") {
        const name = ($("#key-name", root)?.value || "integration").trim() || "integration";
        const out = await store.issueKey(name);
        const box = $("#key-reveal", root);
        box.hidden = false;
        box.innerHTML = `<p>Copy this key now — it will not be shown again.</p><code>${esc(out.key)}</code>`;
        ctx.toast("API key issued", "ok", 5000);
        await loadOps();
      }
    } catch (e) {
      ctx.toast(e.message, "err", 6000);
    }
    el.disabled = false;
  });

  on(root, "click", "[data-revoke]", async (_, el) => {
    el.disabled = true;
    try {
      await store.revokeKey(el.dataset.revoke);
      ctx.toast("Key revoked", "ok");
      await loadOps();
    } catch (e) {
      ctx.toast(e.message, "err");
    }
    el.disabled = false;
  });

  let opsCache = null;

  function renderKpis(animate) {
    const m = store.s.metrics || {};
    const first = !$("#kpi-fa", root);
    if (first) {
      $("#kpis", root).innerHTML = `
        <div class="kpi panel hero"><span class="lbl">FALSE ALARMS</span><b class="val" id="kpi-fa" data-value="0">0</b><span class="quote">"without creating false alarms." — the brief</span></div>
        <div class="kpi panel"><span class="lbl">FORMAT MATRIX</span><b class="val" id="kpi-matrix">—</b><span class="sub">7 fields × txt/pdf/docx/xlsx × labels</span></div>
        <div class="kpi panel"><span class="lbl">FULL INBOX RITUAL</span><b class="val" id="kpi-ritual">—</b><span class="sub" id="kpi-ritual-sub">crash-free official corpus</span></div>
        <div class="kpi panel"><span class="lbl">FALSE-ALARM TRAPS</span><b class="val v-CLEAR" id="kpi-traps" data-value="0" style="color:var(--v)">0</b><span class="sub">Equivalent writing must not defect</span></div>`;
      if (animate) enter($$(".kpi", root), { stagger: 0.06, y: 14 });
    }
    countTo($("#kpi-fa", root), m.false_alarms || 0);
    const head = m.discipline?.headline || {};
    const cells = head.cells || m.discipline?.matrix?.cells || 0;
    const passed = head.passed || m.discipline?.matrix?.passed || 0;
    const mx = $("#kpi-matrix", root);
    if (mx) mx.textContent = cells ? `${passed}/${cells}` : "—";
    const ritualN = head.ritual_count || 0;
    const ritualOk = head.ritual_ok || 0;
    const rt = $("#kpi-ritual", root);
    if (rt) rt.textContent = ritualN ? `${ritualOk}/${ritualN}` : "—";
    const rts = $("#kpi-ritual-sub", root);
    if (rts) rts.textContent = head.ritual_kind ? `${head.ritual_kind} · crash-free official corpus` : "crash-free official corpus";
    const traps = head.false_alarm_traps;
    countTo($("#kpi-traps", root), traps == null ? 0 : traps);
    const desk = $("#desk-now", root);
    if (desk) {
      const c = store.counts();
      desk.textContent = `Desk now: ${c.CLEAR || 0} CLEAR · ${c.HOLD || 0} HOLD · ${c.PILOT || 0} PILOT`;
    }
    renderRobustness();
    renderDiscipline();
  }

  function renderDiscipline() {
    const line = $("#disc-line", root);
    const grid = $("#fmt-matrix", root);
    const ritualEl = $("#ritual-line", root);
    const d = store.s.metrics?.discipline || {};
    if (line) line.textContent = d.talking_point || "";
    const matrix = d.matrix || {};
    const fields = matrix.fields || [];
    const formats = matrix.formats || ["txt", "pdf", "docx", "xlsx"];
    const cells = matrix.grid || {};
    if (grid) {
      if (!fields.length) {
        grid.innerHTML = `<div class="empty"><p>Run python scripts/run_discipline.py to tick every cell.</p></div>`;
      } else {
        grid.innerHTML = `<div class="matrix" style="grid-template-columns: 7.5rem repeat(${formats.length}, minmax(64px, 1fr))">
          <div class="lab"></div>
          ${formats.map((f) => `<div class="lab col">${esc(f)}</div>`).join("")}
          ${fields.map((field) => `<div class="lab">${esc(fieldZh(field) || field)}</div>${formats.map((fmt) => {
            const cell = cells[field]?.[fmt] || {};
            const n = cell.n || 0;
            const fail = cell.fail || 0;
            const ok = cell.ok || 0;
            const pass = n > 0 && fail === 0;
            return `<div class="c ${pass ? "diag hot" : fail ? "off hot" : ""}" style="--h:${pass ? "1" : fail ? "0.7" : "0"}" title="${esc(field)} · ${esc(fmt)}: ${ok}/${n}">${n ? `${ok}/${n}` : "·"}</div>`;
          }).join("")}`).join("")}
        </div>`;
      }
    }
    if (ritualEl) {
      const fa = d.false_alarms?.count;
      const ritual = d.ritual || [];
      const last = ritual.slice(-2);
      const ritualTxt = last.length
        ? last.map((r) => `${r.kind || "run"} ${r.ok}/${r.count}${r.crash_free ? " crash-free" : " CRASH"}`).join(" · ")
        : "Full 520-email ritual not stamped in this build.";
      ritualEl.textContent = `False-alarm traps ${fa == null ? "—" : fa} · Full inbox ${ritualTxt}`;
    }
  }

  function renderRobustness() {
    const el = $("#robust-line", root);
    const list = $("#robust-seeds", root);
    if (!el) return;
    const r = store.s.metrics?.robustness || {};
    el.textContent = r.talking_point || r.note || "Run python scripts/calibrate_seeds.py --seeds 7,13,21,42,99";
    const seeds = r.seeds || [];
    if (!list) return;
    if (!seeds.length) {
      const local = r.local_reproducibility || {};
      const ident = local.ok ? `Two identical pipeline runs matched (${local.count || 0} cases).` : "Local identity check not recorded.";
      list.innerHTML = `<p class="muted">${esc(ident)} Ground truth never enters the pipeline.${r.status === "generator_not_in_tree" ? " Sponsor generate.py is not bundled here." : ""}</p>`;
      return;
    }
    list.innerHTML = `<div class="legend">${seeds.map((s) => {
      const mark = s.final_score != null ? Number(s.final_score).toFixed(4) : (s.score_pct != null ? s.score_pct + "%" : s.status || "ok");
      return `<span class="chip">${esc(String(s.seed))} · ${esc(String(mark))}</span>`;
    }).join("")}</div>
      <p class="muted" style="margin-top:.6rem">Variance ${r.score_variance != null ? r.score_variance : "—"} · ${esc(r.local_reproducibility?.ok === false ? "local replay drifted" : "local replay identical")}</p>`;
  }

  function mixRow(label, n, total, cls = "") {
    const pct = total ? Math.round((1000 * n) / total) / 10 : 0;
    return `<div class="fbar">
      <div class="nm">${esc(label)}</div>
      <div class="bar"><i class="${cls || "s-MATCH"}" style="width:${pct}%"></i></div>
      <div class="cnt"><span><b>${n}</b></span><span>${pct}%</span></div>
    </div>`;
  }

  function renderMatrix() {
    const el = $("#mix", root);
    if (!el) return;
    const m = store.s.metrics || {};
    const official = m.official || {};
    const cats = official.categories || {};
    const status = official.status || {};
    const counts = store.counts();
    const catN = Object.values(cats).reduce((a, b) => a + b, 0) || official.emails || 0;
    const stN = Object.values(status).reduce((a, b) => a + b, 0) || catN;
    const boardN = (counts.CLEAR || 0) + (counts.HOLD || 0) + (counts.PILOT || 0);
    const line = $("#mix-line", root);
    if (line) {
      line.textContent = catN
        ? `${catN} official emails graded · ${boardN} unique cards on the desk. Official OK/MISMATCH/NEEDS_REVIEW is the submission. CLEAR/HOLD/PILOT is the operator desk.`
        : "Waiting on the hosted ledger…";
    }
    const CAT = [
      ["BL_COMPARISON", "BL compare"],
      ["SI_REQUEST", "SI request"],
      ["INVOICE_QUERY", "Invoice query"],
      ["GENERAL", "General"],
      ["SPAM", "Spam"],
    ];
    const ST = [
      ["OK", "Official OK", "s-MATCH"],
      ["MISMATCH", "Official mismatch", "s-MISMATCH"],
      ["NEEDS_REVIEW", "Official needs review", "s-UNCERTAIN"],
      ["null", "No SI/BL compare", ""],
    ];
    el.innerHTML = `
      <div class="section-title" style="margin-top:.2rem"><h3>Official category</h3><small>SUBMISSION.JSON</small></div>
      ${CAT.map(([k, lab]) => mixRow(lab, cats[k] || 0, catN)).join("")}
      <div class="section-title" style="margin-top:1rem"><h3>Official compare</h3><small>L8 ASSEMBLE</small></div>
      ${ST.map(([k, lab, cls]) => mixRow(lab, status[k] || 0, stN, cls)).join("")}
      <div class="section-title" style="margin-top:1rem"><h3>Desk verdicts</h3><small>THIS BOARD</small></div>
      ${mixRow("CLEAR", counts.CLEAR || 0, boardN, "s-MATCH")}
      ${mixRow("HOLD", counts.HOLD || 0, boardN, "s-MISMATCH")}
      ${mixRow("PILOT", counts.PILOT || 0, boardN, "s-UNCERTAIN")}`;
  }

  function renderFields() {
    const el = $("#fbars", root);
    const fs = {};
    for (const name of SEVEN_FIELDS) fs[name] = { MATCH: 0, MISMATCH: 0, UNCERTAIN: 0 };
    let any = false;
    for (const r of store.s.runs || []) {
      for (const fv of sevenFields(r)) {
        const key = fv.field === "gross_weight" ? "gross_weight_kg" : fv.field;
        if (!fs[key]) continue;
        any = true;
        const st = effectiveState(fv);
        fs[key][st] = (fs[key][st] || 0) + 1;
      }
    }
    const names = SEVEN_FIELDS.filter((f) => {
      const s = fs[f];
      return (s.MATCH || 0) + (s.MISMATCH || 0) + (s.UNCERTAIN || 0) > 0;
    });
    if (!any || !names.length) { el.innerHTML = `<div class="empty"><p>No field data yet.</p></div>`; return; }
    el.innerHTML = names.map((f) => {
      const s = fs[f];
      const total = (s.MATCH || 0) + (s.MISMATCH || 0) + (s.UNCERTAIN || 0) || 1;
      const pct = (n) => `${((n || 0) / total) * 100}%`;
      return `<div class="fbar">
        <div class="nm">${esc(fieldZh(f))}<small>${esc(fieldEn(f))}</small></div>
        <div class="bar"><i class="s-MATCH" style="width:${pct(s.MATCH)}"></i><i class="s-MISMATCH" style="width:${pct(s.MISMATCH)}"></i><i class="s-UNCERTAIN" style="width:${pct(s.UNCERTAIN)}"></i></div>
        <div class="cnt"><span class="s-MATCH"><b>${Math.round(((s.MATCH || 0) / total) * 100)}%</b></span><span>${s.MATCH || 0}/${s.MISMATCH || 0}/${s.UNCERTAIN || 0}</span></div>
      </div>`;
    }).join("");
  }

  function renderDial() {
    $("#dial-v", root).textContent = floor.toFixed(2);
    const rec = store.recordedCounts();
    const p = store.project(floor);
    const live = store.counts();
    const dHold = p.HOLD - rec.HOLD;
    const dPilot = p.PILOT - rec.PILOT;
    const applied = store.s.deskFloor != null && Math.abs(store.s.deskFloor - floor) < 0.001;
    $$("[data-preset]", root).forEach((btn) => {
      const pr = PRESETS[btn.dataset.preset];
      btn.classList.toggle("on", Boolean(pr && Math.abs(pr.floor - floor) < 0.001));
    });
    const dClear = p.CLEAR - rec.CLEAR;
    const delta = (n) => (n ? ` <span style="font-size:.75rem;font-weight:500">${n > 0 ? "+" : ""}${n}</span>` : "");
    $("#dial-stats", root).innerHTML = `
      <div class="dial-stat"><small>If applied CLEAR</small><b class="v-CLEAR" style="color:var(--v)">${p.CLEAR}${delta(dClear)}</b></div>
      <div class="dial-stat"><small>If applied HOLD</small><b class="v-HOLD" style="color:var(--v)">${p.HOLD}${delta(dHold)}</b></div>
      <div class="dial-stat"><small>If applied Pilot</small><b class="v-PILOT" style="color:var(--v)">${p.PILOT}${delta(dPilot)}</b></div>`;
    const applyBtn = $("[data-apply-floor]", root);
    if (applyBtn) applyBtn.disabled = applied;
    $("#dial-note", root).textContent = applied
      ? `This desk already uses floor ${floor.toFixed(2)}. Header is ${live.CLEAR} CLEAR · ${live.HOLD} HOLD · ${live.PILOT} PILOT. Defence outcomes stay put. Refresh restores the recorded 520.`
      : `Preview only. Recorded desk is ${rec.CLEAR} CLEAR · ${rec.HOLD} HOLD · ${rec.PILOT} PILOT. On this 520, leftover mismatch confidence sits around 0.93 and 0.96 — Balanced 0.92 matches the header; Cautious 0.97 hands those HOLDs to Pilot. Apply moves this session's header, Board, and Pilot. Official submission stays put.`;
    renderCurve();
  }

  function renderCurve() {
    const svg = $("#curve", root);
    const rec = store.recordedCounts();
    const xs = [];
    for (let f = 0.6; f <= 0.981; f += 0.01) xs.push(Number(f.toFixed(2)));
    const pts = xs.map((f) => ({ f, ...store.project(f) }));
    const maxHold = Math.max(1, rec.HOLD, ...pts.map((p) => p.HOLD));
    const maxPilot = Math.max(1, rec.PILOT, ...pts.map((p) => p.PILOT));
    const X = (f) => 14 + ((f - 0.6) / 0.38) * 180;
    const Yh = (n) => 96 - (n / maxHold) * 84;
    const Yp = (n) => 96 - (n / maxPilot) * 84;
    const path = (fn, Y) => pts.map((p, i) => `${i ? "L" : "M"}${X(p.f).toFixed(1)},${Y(fn(p)).toFixed(1)}`).join(" ");
    const grid = [0, 0.25, 0.5, 0.75, 1].map((g) => `<line class="grid" x1="14" x2="194" y1="${96 - g * 84}" y2="${96 - g * 84}" />`).join("");
    const ticks = [0.6, 0.7, 0.8, 0.9, 0.98].map((t) => {
      const anchor = t <= 0.61 ? "start" : t >= 0.97 ? "end" : "middle";
      return `<text x="${X(t).toFixed(1)}" y="106" text-anchor="${anchor}">${t.toFixed(2)}</text>`;
    }).join("");
    const fx = X(floor);
    const floorAnchor = floor <= 0.64 ? "start" : floor >= 0.94 ? "end" : "middle";
    svg.innerHTML = `
      ${grid}${ticks}
      <path class="auto" d="${path((p) => p.HOLD, Yh)}" />
      <path class="pilot" d="${path((p) => p.PILOT, Yp)}" />
      <line class="cur" x1="${fx}" x2="${fx}" y1="8" y2="96" />
      <text x="${fx.toFixed(1)}" y="6" text-anchor="${floorAnchor}" style="fill:var(--signal)">floor ${floor.toFixed(2)}</text>
      <text x="148" y="14" style="fill:var(--hold)">HOLD count</text>
      <text x="148" y="20" style="fill:var(--pilot)">Pilot count</text>`;
  }

  async function loadOps() {
    if (!store.live) return;
    try {
      opsCache = await store.opsStatus();
      renderOps();
      await renderKeys();
    } catch {
      opsCache = null;
      renderOps();
    }
  }

  function renderOps() {
    const el = $("#ops-line", root);
    if (!el) return;
    const h = store.s.health;
    const m = store.s.metrics || {};
    const st = opsCache?.storage || h?.storage;
    const keys = opsCache?.issued_keys ?? h?.keys?.issued ?? 0;
    if (!store.live) {
      el.textContent = "Offline replay — export/submit need a live backend.";
      return;
    }
    if (!h) {
      el.textContent = "Connected. Waiting on health…";
      return;
    }
    const off = m.official || {};
    el.textContent = [
      h.inbox?.ok ? `Inbox ${h.inbox.email_count}` : "Inbox unreachable",
      h.llm?.configured ? `LLM ${h.llm.model || ""}` : "LLM not configured",
      st?.backend ? `Storage ${st.backend}${st.ok === false ? " down" : ""}` : null,
      off.emails ? `${off.emails} graded emails` : "no graded corpus yet",
      m.llm_cache_entries ? `${m.llm_cache_entries} cached extracts` : null,
      keys ? `${keys} API keys` : "open auth",
    ].filter(Boolean).join(" · ");
    const storageEl = $("#ops-storage", root);
    if (storageEl) {
      if (!st) storageEl.textContent = "Storage status unavailable.";
      else {
        const err = st.error ? ` · ${st.error}` : "";
        const n = st.count != null ? ` · ${st.count} objects` : "";
        storageEl.textContent = `${st.ok === false ? "DOWN" : "OK"} · ${st.backend}${st.bucket ? " · " + st.bucket : ""}${st.root ? " · " + st.root : ""}${n}${err}`;
      }
    }
    const objEl = $("#ops-objects", root);
    if (objEl) {
      const rows = opsCache?.objects || [];
      objEl.innerHTML = rows.length
        ? rows.slice(0, 6).map((o) => `<div class="object-row"><code>${esc(o.object_key)}</code><span>${esc(o.backend)} · ${o.bytes} B</span></div>`).join("")
        : `<p class="muted">No offloaded artifacts yet. Backup or export writes here.</p>`;
    }
  }

  async function renderKeys() {
    const list = $("#key-list", root);
    if (!list || !store.live) return;
    try {
      const keys = await store.listKeys();
      if (!keys.length) {
        list.innerHTML = `<p class="muted">No issued keys. Demo stays open until you set HARBORMASTER_API_KEY or issue one (same-origin UI still works).</p>`;
        return;
      }
      list.innerHTML = keys.map((k) => `
        <div class="key-row">
          <div><code>${esc(k.prefix)}</code><small>${esc(k.name || "")}</small></div>
          <button type="button" class="btn btn-sm" data-revoke="${esc(k.key_id)}">Revoke</button>
        </div>`).join("");
    } catch {
      list.innerHTML = `<p class="muted">Could not list keys.</p>`;
    }
  }

  function renderAll(animate) {
    renderOps();
    renderKpis(animate);
    renderDiscipline();
    renderMatrix();
    renderFields();
    renderDial();
  }

  renderAll(true);
  loadOps();
  return {
    update(_s, reason) {
      if (reason === "busy") return;
      if (reason === "autonomy" || reason === "refresh" || reason === "mode") {
        const f = store.s.autonomy?.thresholds?.match_confidence_floor;
        if (f != null && document.activeElement !== dial) { floor = Number(f); dial.value = floor; }
      }
      renderAll(false);
    },
    destroy() {},
  };
}
