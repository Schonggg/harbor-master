// ① Verdict board — Worldwide Hubs: three offices, then the docket.
import { store as bridgeStore } from "../lib/store.js?v=48";
import { esc, $, $$, on, shortId } from "../lib/dom.js";
import { enter, countTo, magnetize, tiltify, scrollToY } from "../lib/motion.js";
import { FIELD_ORDER, scoutZh, VERDICT, fieldZh } from "../lib/copy.js";
import { card, orderedFields, summarize } from "../lib/case.js?v=12";

const HUBS = [
  {
    id: "CLEAR",
    name: "CLEAR",
    kicker: "01  RELEASE",
    line: "Release the berth",
    copy: "Every field matched, or a defence absorbed the difference. The cargo moves.",
  },
  {
    id: "HOLD",
    name: "HOLD",
    kicker: "02  STOP",
    line: "Stop the cargo",
    copy: "A real discrepancy. No strategy held. The documents do not agree.",
  },
  {
    id: "PILOT",
    name: "PILOT",
    kicker: "03  HUMAN",
    line: "Hand to a human",
    copy: "Evidence is thin, or the run failed. The system raises a hand instead of guessing.",
  },
];

const ART = {
  CLEAR: `<svg viewBox="0 0 400 560" aria-hidden="true">
    <g fill="currentColor">
      <rect x="0" y="468" width="400" height="92" opacity="0.18"/>
      <path d="M0 468 Q100 452 200 468 T400 468 L400 560 L0 560 Z" opacity="0.28"/>
      <rect x="62" y="392" width="58" height="76"/>
      <rect x="128" y="368" width="62" height="100"/>
      <rect x="198" y="404" width="84" height="64"/>
      <rect x="194" y="96" width="14" height="292"/>
      <rect x="86" y="96" width="228" height="12"/>
      <rect x="86" y="96" width="12" height="72"/>
      <path d="M98 168 L98 204 L308 118 L308 98 Z"/>
      <rect x="302" y="98" width="10" height="126"/>
      <circle cx="201" cy="102" r="8"/>
    </g>
  </svg>`,
  HOLD: `<svg viewBox="0 0 400 560" aria-hidden="true">
    <g fill="currentColor">
      <rect x="0" y="468" width="400" height="92" opacity="0.18"/>
      <path d="M0 468 Q100 452 200 468 T400 468 L400 560 L0 560 Z" opacity="0.28"/>
      <rect x="108" y="148" width="184" height="248" opacity="0.2"/>
      <rect x="124" y="172" width="152" height="224"/>
      <rect x="140" y="196" width="120" height="8" opacity="0.35"/>
      <rect x="140" y="220" width="88" height="6" opacity="0.28"/>
      <rect x="140" y="240" width="104" height="6" opacity="0.28"/>
      <path d="M168 292 L232 356 M232 292 L168 356" stroke="currentColor" stroke-width="14" fill="none"/>
      <rect x="92" y="132" width="168" height="14" transform="rotate(-7 92 132)"/>
    </g>
  </svg>`,
  PILOT: `<svg viewBox="0 0 400 560" aria-hidden="true">
    <g fill="currentColor">
      <rect x="0" y="468" width="400" height="92" opacity="0.18"/>
      <path d="M0 468 Q100 452 200 468 T400 468 L400 560 L0 560 Z" opacity="0.28"/>
      <polygon points="200,78 226,162 174,162"/>
      <rect x="188" y="162" width="24" height="168"/>
      <polygon points="148,330 252,330 236,378 164,378"/>
      <rect x="128" y="378" width="144" height="44"/>
      <circle cx="200" cy="128" r="16" fill="none" stroke="currentColor" stroke-width="5"/>
      <rect x="197" y="46" width="6" height="32"/>
      <polygon points="200,90 310,150 200,122" opacity="0.22"/>
    </g>
  </svg>`,
};

export function mount(root, ctx) {
  const store = ctx.store || bridgeStore;
  const state = { verdict: "ALL", label: "ALL" };

  root.innerHTML = `
    <section class="view board-view">
      <header class="hubs-hero">
        <div class="hubs-kicker">
          <span>Offices</span>
          <span id="inbox-tally">Inbox …</span>
        </div>
        <div class="hubs-title-row">
          <h1 class="js-para-title">Three verdicts.<em>One standard of work.</em></h1>
          <p class="js-para-copy">Harbormaster keeps three offices on the same water. Click a berth to filter the docket and drop into that office. The model extracts. It never sits on the bench.</p>
        </div>
        <div class="hubs js-para-hubs" id="hubs">
          ${HUBS.map((hub) => `
            <button type="button" class="hub v-${hub.id}" data-verdict="${hub.id}" aria-pressed="false">
              <span class="hub-name">${hub.name}</span>
              <span class="hub-art" aria-hidden="true">${ART[hub.id]}</span>
              <span class="hub-meta">
                <span class="hub-kicker">${hub.kicker}</span>
                <b id="hub-${hub.id.toLowerCase()}">0</b>
                <em>${hub.line}</em>
                <i>${hub.copy}</i>
              </span>
            </button>
          `).join("")}
        </div>
      </header>

      <div class="docket js-para-docket" id="docket">
        <div class="docket-head">
          <div>
            <h2>Docket</h2>
            <p id="docket-copy">One card per email. Open any card for the seven-field compare.</p>
          </div>
          <button type="button" class="btn" id="board-refresh">Refresh</button>
        </div>
        <div class="filter-row" id="filters"></div>
        <div id="cards"></div>
      </div>
    </section>`;

  const cardsEl = $("#cards", root);
  const filtersEl = $("#filters", root);
  const hubsEl = $("#hubs", root);

  $("#board-refresh", root).addEventListener("click", async () => {
    try { await store.refresh(); ctx.toast("Refreshed", "ok"); } catch (e) { ctx.toast(e.message, "err"); }
  });

  on(hubsEl, "click", ".hub", (e, b) => {
    const next = b.dataset.verdict;
    state.verdict = state.verdict === next ? "ALL" : next;
    renderHubs();
    renderFilters();
    renderCards(true);
    ctx.scene?.splash?.(e.clientX, e.clientY);
    const dock = $("#docket", root);
    if (dock) {
      const y = dock.getBoundingClientRect().top + scrollY - 96;
      scrollToY(y);
    }
  });
  on(filtersEl, "click", "button[data-verdict]", (_, b) => { state.verdict = b.dataset.verdict; renderHubs(); renderFilters(); renderCards(true); });
  on(filtersEl, "click", "button[data-label]", (_, b) => { state.label = b.dataset.label; renderFilters(); renderCards(true); });
  on(cardsEl, "click", ".mail-card", (e, el) => {
    if (e.target.closest("[data-court]")) return;
    if (!el.dataset.run) return;
    ctx.openDetail(el.dataset.run);
  });
  on(cardsEl, "click", "[data-court]", (e, el) => {
    e.stopPropagation();
    ctx.navigate("court", { run: el.dataset.court });
  });
  on(cardsEl, "click", "[data-seed]", () => ctx.seed());
  on(cardsEl, "keydown", ".mail-card", (e, el) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ctx.openDetail(el.dataset.run); }
  });

  function pendingItems() {
    const have = new Set((store.s.runs || []).map((r) => r.email_id));
    return (store.s.inbox || []).filter((item) => item?.email_id && !have.has(item.email_id));
  }

  function filtered() {
    const runs = store.s.runs.filter((r) => {
      const c = card(r);
      if (state.verdict !== "ALL" && (c.verdict || r.verdict) !== state.verdict) return false;
      if (state.label !== "ALL" && (c.scout?.label || "unknown") !== state.label) return false;
      return true;
    });
    if (state.verdict !== "ALL" || state.label !== "ALL") return runs;
    return runs.concat(pendingItems().map((item) => ({ pending: true, ...item })));
  }

  function renderHubs() {
    const c = store.counts();
    countTo($("#hub-clear", root), c.CLEAR);
    countTo($("#hub-hold", root), c.HOLD);
    countTo($("#hub-pilot", root), c.PILOT);
    $$(".hub", hubsEl).forEach((el) => {
      const on = state.verdict === el.dataset.verdict;
      el.classList.toggle("on", on);
      el.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function renderFilters() {
    const c = store.counts();
    const labels = new Map();
    for (const r of store.s.runs) {
      const l = card(r).scout?.label || "unknown";
      labels.set(l, (labels.get(l) || 0) + 1);
    }
    const seg = (key, val, text, n, cls = "") =>
      `<button type="button" data-${key}="${val}" class="${state[key === "verdict" ? "verdict" : "label"] === val ? "on" : ""} ${cls}">${text}<span class="n">${n}</span></button>`;
    filtersEl.innerHTML = `
      <div class="seg">
        ${seg("verdict", "ALL", "All", store.s.runs.length + pendingItems().length)}
        ${seg("verdict", "CLEAR", "CLEAR", c.CLEAR, "v v-CLEAR")}
        ${seg("verdict", "HOLD", "HOLD", c.HOLD, "v v-HOLD")}
        ${seg("verdict", "PILOT", "PILOT", c.PILOT, "v v-PILOT")}
      </div>
      <span class="sep"></span>
      <div class="seg">
        ${seg("label", "ALL", "All types", store.s.runs.length)}
        ${[...labels.entries()].sort((a, b) => b[1] - a[1]).map(([l, n]) => seg("label", l, scoutZh(l), n)).join("")}
      </div>`;
  }

  function fieldStrip(run) {
    const byName = Object.fromEntries(orderedFields(run).map((f) => [f.field, f]));
    return `<div class="field-strip" aria-hidden="true">${FIELD_ORDER.map((f) => {
      const fv = byName[f];
      return fv ? `<i class="s-${fv.state}" title="${esc(fieldZh(f))} · ${fv.state}"></i>` : `<i class="none"></i>`;
    }).join("")}</div>`;
  }

  function renderCards(animate = false) {
    const runs = filtered();
    if (!store.s.runs.length && !pendingItems().length) {
      const connecting = store.s.mode === "connecting";
      cardsEl.innerHTML = `
        <div class="empty panel">
          <h3>${connecting ? "Waking the official ledger" : "The offices are quiet"}</h3>
          <p>${connecting ? "Connecting to the hosted 520-email inbox. Header and hubs stay at zero until the ledger answers — no replay fixtures." : "No mail on the board yet. Load inbox pulls the official SDOC corpus (520 emails)."}</p>
          ${connecting ? "" : `<button type="button" class="btn btn-primary" data-seed>Load inbox <span class="arrow">→</span></button>`}
        </div>`;
      return;
    }
    if (!runs.length) {
      cardsEl.innerHTML = `<div class="empty panel"><h3>No matching cards</h3><p>Try a different office, or clear the filter.</p></div>`;
      return;
    }
    cardsEl.innerHTML = `<div class="card-grid">${runs.map((r) => {
      if (r.pending) {
        return `
        <article class="mail-card pending" data-email="${esc(r.email_id)}" tabindex="0">
          <div class="row">
            <span class="verdict-tag">QUEUED<em>待审</em></span>
            <span class="chip">${r.attachments || 0} attachments</span>
          </div>
          <h3 title="${esc(r.subject || r.email_id)}">${esc(r.subject || r.email_id)}</h3>
          <p class="summary">${esc(r.from_addr || "Official SDOC inbox")} — waiting for Scout → extract → court.</p>
          <div class="foot">
            <div class="field-strip" aria-hidden="true">${FIELD_ORDER.map(() => `<i class="none"></i>`).join("")}</div>
            <span class="id">${esc(r.email_id)}</span>
          </div>
        </article>`;
      }
      const c = card(r);
      const v = c.verdict || r.verdict;
      const label = c.scout?.label || "unknown";
      const charged = orderedFields(r).filter((f) => f.charge).length;
      return `
        <article class="mail-card v-${v}" data-run="${esc(r.run_id)}" tabindex="0" role="button" aria-label="${esc(c.subject || r.email_id)}">
          <div class="row">
            <span class="verdict-tag">${v}<em>${VERDICT[v]?.zh || ""}</em></span>
            <span class="chip">${esc(scoutZh(label))}${c.scout?.confidence != null ? ` · ${Math.round(c.scout.confidence * 100)}%` : ""}</span>
          </div>
          <h3 title="${esc(c.subject || r.email_id)}">${esc(c.subject || r.email_id)}</h3>
          <p class="summary">${esc(summarize(r))}</p>
          <div class="foot">
            ${fieldStrip(r)}
            <span class="id">${esc(r.email_id || shortId(r.run_id))}${c.degraded ? ' · <span class="v-PILOT" style="color:var(--v)">DEGRADED</span>' : ""}</span>
          </div>
          ${charged ? `<button type="button" class="btn btn-sm" data-court="${esc(r.run_id)}">Open court <span class="arrow">→</span></button>` : ""}
        </article>`;
    }).join("")}</div>`;
    if (animate && runs.length < 48) enter($$(".mail-card", cardsEl), { stagger: 0.035, y: 16 });
    prefetchVisible();
  }

  function prefetchVisible() {
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 160));
    idle(() => {
      const ids = $$(".mail-card[data-run]", cardsEl).flatMap((el) => {
        const box = el.getBoundingClientRect();
        if (box.bottom < 0 || box.top > innerHeight + 240) return [];
        const run = store.runById(el.dataset.run);
        return run?.email_id ? [run.email_id] : [];
      });
      store.prefetchEmails([], ids).catch(() => {});
    });
  }

  function renderDocketCopy() {
    const copy = $("#docket-copy", root);
    const tally = $("#inbox-tally", root);
    const official = store.s.runs.filter((r) => String(r.email_id || "").startsWith("email_")).length;
    const inbox = store.s.health?.inbox?.email_count || store.s.inbox?.length || 0;
    const pending = pendingItems().length;
    const job = store.s.job;
    if (copy) {
      const jobAt = Date.parse(job?.updated_at || "") || 0;
      const jobFresh = job && (job.status === "running" || job.status === "queued")
        && jobAt && (Date.now() - jobAt) < 10 * 60 * 1000;
      if (jobFresh) {
        copy.textContent = `Loading official inbox onto the board · ${Math.max(job.processed || 0, official)} / ${job.total || inbox || 520}. Cards appear as each email is judged.`;
      } else if (official || inbox) {
        copy.textContent = `Official SDOC inbox · ${official} judged${pending ? ` · ${pending} queued` : ""} · ${inbox || 520} files. Open a card for the seven-field compare.`;
      } else {
        copy.textContent = "One card per email. Open any card for the seven-field compare.";
      }
    }
    if (tally) {
      tally.textContent = inbox
        ? `Official inbox · ${inbox} emails`
        : "Est. 2026 — worldwide";
    }
  }

  function update(_s, reason) {
    renderHubs();
    renderFilters();
    renderCards(reason !== "refresh" && reason !== "job");
    renderDocketCopy();
  }

  update();
  const unMag = magnetize(hubsEl, ".hub", 6);
  const unTilt = tiltify(hubsEl, ".hub", { max: 3, glare: true });
  const unCardTilt = tiltify(cardsEl, ".mail-card", { max: 2, glare: true });
  return { update, destroy() { unMag?.(); unTilt?.(); unCardTilt?.(); } };
}
