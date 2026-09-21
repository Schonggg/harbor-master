// Harbormaster Bridge — shell: routing, store wiring, header, drawer, toasts.
import { store } from "./lib/store.js?v=69";
import { mountScene, scene } from "./lib/scene.js?v=13";
import { $, $$, h, esc } from "./lib/dom.js?v=69";
import { gsap, reduced, swapView, countTo, pulse, mountSpotlight, playBoot, mountParallax } from "./lib/motion.js?v=18";
import { renderDetail } from "./views/detail.js?v=69";
import * as board from "./views/board.js?v=69";
import * as court from "./views/court.js?v=69";
import * as ledger from "./views/ledger.js?v=69";
import * as chaos from "./views/chaos.js?v=69";
import * as metrics from "./views/metrics.js?v=69";
import * as pilot from "./views/pilot.js?v=69";

const VIEWS = { board, court, pilot, ledger, chaos, metrics };
const ORDER = Object.keys(VIEWS);
const MOOD_BY_VIEW = { board: "calm", court: "court", pilot: "pilot", ledger: "ledger", chaos: "chaos", metrics: "calm" };

const viewRoot = $("#view");
const tabs = $("#tabs");
const indicator = $(".indicator", tabs);
const drawer = $("#drawer");
const backdrop = $("#drawer-backdrop");
const toasts = $("#toasts");
const busyBar = $("#busy");

let current = { name: null, instance: null };
let drawerOpen = false;

mountScene($("#sea"));
mountSpotlight($("#spot"));
mountParallax(scene);
playBoot($("#boot"));

// ── toasts ──────────────────────────────────────────────────────────────
function toast(msg, kind = "", ms = 3600) {
  const el = h(`<div class="toast ${kind}" role="status">${esc(msg)}</div>`);
  toasts.appendChild(el);
  if (gsap && !reduced) gsap.fromTo(el, { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4 });
  setTimeout(() => {
    if (gsap && !reduced) gsap.to(el, { opacity: 0, y: 10, duration: 0.3, onComplete: () => el.remove() });
    else el.remove();
  }, ms);
}

// ── drawer ──────────────────────────────────────────────────────────────
function openDetail(runId) {
  renderDetail(drawer, runId, ctx);
  drawer.setAttribute("aria-hidden", "false");
  backdrop.classList.add("open");
  document.body.style.overflow = "hidden";
  drawerOpen = true;
  drawer.scrollTop = 0;
  if (gsap && !reduced) {
    gsap.to(drawer, { x: 0, xPercent: 0, duration: 0.55, ease: "power4.out", overwrite: true });
    gsap.to(backdrop, { opacity: 1, duration: 0.4, overwrite: true });
  } else {
    drawer.style.transform = "none";
    backdrop.style.opacity = "1";
  }
  $("[data-close]", drawer)?.focus();
}
function closeDetail() {
  if (!drawerOpen) return;
  drawerOpen = false;
  drawer.setAttribute("aria-hidden", "true");
  backdrop.classList.remove("open");
  document.body.style.overflow = "";
  if (gsap && !reduced) {
    gsap.to(drawer, { xPercent: 104, duration: 0.4, ease: "power3.in", overwrite: true });
    gsap.to(backdrop, { opacity: 0, duration: 0.3, overwrite: true });
  } else {
    drawer.style.transform = "";
    backdrop.style.opacity = "0";
  }
}
if (gsap) gsap.set(drawer, { xPercent: 104 });
backdrop.addEventListener("click", closeDetail);
drawer.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeDetail(); });

// ── router ──────────────────────────────────────────────────────────────
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [name, qs] = raw.split("?");
  const params = Object.fromEntries(new URLSearchParams(qs || ""));
  return { name: VIEWS[name] ? name : "board", params };
}
function navigate(name, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const next = `#/${name}${qs ? `?${qs}` : ""}`;
  if (location.hash === next) route();
  else location.hash = next;
}
function route() {
  const { name, params } = parseHash();
  closeDetail();
  if (current.name === name && current.instance?.setParams && Object.keys(params).length) {
    current.instance.setParams(params);
    return;
  }
  if (current.name === name) return;
  const prev = current.instance;
  current = { name, instance: null };
  moveIndicator(name);
  scene.setMood(MOOD_BY_VIEW[name] || "calm");
  swapView(viewRoot, () => {
    prev?.destroy?.();
    viewRoot.innerHTML = "";
    current.instance = VIEWS[name].mount(viewRoot, ctx, params);
  });
  window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
}
function moveIndicator(name) {
  $$("button", tabs).forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  const btn = $(`button[data-view="${name}"]`, tabs);
  if (!btn) return;
  const x = btn.offsetLeft;
  const w = btn.offsetWidth;
  if (gsap && !reduced) gsap.to(indicator, { x, width: w, duration: 0.45, ease: "power3.out" });
  else { indicator.style.transform = `translateX(${x}px)`; indicator.style.width = `${w}px`; }
  btn.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
}
tabs.addEventListener("click", (e) => { const b = e.target.closest("button[data-view]"); if (b) navigate(b.dataset.view); });
addEventListener("hashchange", route);
addEventListener("resize", () => current.name && moveIndicator(current.name));

// ── header ──────────────────────────────────────────────────────────────
function renderHeader() {
  const c = store.counts();
  countTo($("#c-clear"), c.CLEAR);
  countTo($("#c-hold"), c.HOLD);
  countTo($("#c-pilot"), c.PILOT);
  const badge = $("#pilot-badge");
  badge.hidden = !c.PILOT;
  badge.textContent = c.PILOT;
  const mode = $("#mode");
  const health = store.s.health;
  const llmDown = health?.llm?.configured && health?.llm?.ok === false;
  const degraded = store.s.mode === "live" && (health?.status === "degraded" || llmDown || health?.inbox?.ok === false);
  mode.className = `mode ${store.s.mode}${degraded ? " degraded" : ""}`;
  if (store.s.mode === "live") {
    mode.textContent = degraded ? "LIVE · DEGRADED" : `LIVE${store.s.apiBase ? " · " + store.s.apiBase.replace(/^https?:\/\//, "") : ""}`;
  } else if (store.s.mode === "offline") {
    mode.textContent = "OFFLINE · replay";
  } else {
    mode.textContent = "CONNECTING";
  }
  mode.title = store.s.mode === "offline" ? `Backend unreachable: ${store.s.lastError || ""}. Use ?api=https://host:port to pin a backend.` : store.s.apiBase || location.origin;
  const sys = $("#sys-status");
  if (sys) {
    if (store.s.mode === "offline") {
      sys.textContent = "Backend unreachable · replay mode";
    } else if (health) {
      const bits = [
        health.db?.ok ? "DB ok" : "DB down",
        health.storage?.backend ? (health.storage.ok === false ? `Storage ${health.storage.backend} down` : `Storage ${health.storage.backend}`) : null,
        health.llm?.configured ? (health.llm.ok === false ? "LLM fail" : "LLM ready") : "LLM off",
        health.inbox?.ok ? `Inbox ${health.inbox.email_count}${health.inbox.source && health.inbox.source !== "remote" ? " · " + health.inbox.source : ""}` : "Inbox down",
        store.s.job && (store.s.job.status === "running" || store.s.job.status === "queued")
          ? `Filling ${store.s.job.processed || 0}/${store.s.job.total || 0}`
          : null,
      ].filter(Boolean);
      sys.textContent = bits.join(" · ");
    }
  }
  const seedBtn = $("#btn-seed");
  if (seedBtn) seedBtn.disabled = store.s.mode === "connecting" || store.s.busy > 0;
  const resetBtn = $("#btn-reset");
  if (resetBtn) resetBtn.disabled = store.s.mode === "connecting" || store.s.busy > 0;
}

async function seed() {
  if (store.s.mode === "connecting") {
    toast("Still connecting to the hosted ledger…", "", 4000);
    return;
  }
  const b = $("#btn-seed");
  b.disabled = true;
  toast(
    store.live
      ? "Loading the official inbox onto the board…"
      : "Loading local snapshot…",
    "",
    4000,
  );
  try {
    const out = await store.seed();
    if (out?.reason === "connecting") return;
    const n = out?.official ?? store.s.runs.length;
    const queued = out?.queued ? ` · filling ${out.queued} more in small batches` : "";
    toast(`${n} official emails on the board${queued}`, "ok", 7000);
    pulse($(".counters"), 1.04);
    if (current.name !== "board") navigate("board");
  } catch (e) { toast(`Load failed: ${e.message}`, "err", 6000); }
  b.disabled = false;
}
async function reset() {
  if (store.s.mode === "connecting") {
    toast("Still connecting to the hosted ledger…", "", 4000);
    return;
  }
  const b = $("#btn-reset");
  b.disabled = true;
  try {
    const out = await store.reset();
    scene.setMood("calm");
    toast(out?.reason === "hosted ledger preserved" ? "Official ledger kept · board refreshed" : "Board refreshed", "ok");
  } catch (e) { toast(`Refresh failed: ${e.message}`, "err"); }
  b.disabled = false;
}
$("#btn-seed").addEventListener("click", seed);
$("#btn-reset").addEventListener("click", reset);

// ── busy bar ────────────────────────────────────────────────────────────
let busyTween = null;
function renderBusy() {
  const on = store.s.busy > 0;
  busyBar.classList.toggle("on", on);
  if (!gsap || reduced) { busyBar.style.opacity = on ? "1" : "0"; return; }
  if (on && !busyTween) {
    gsap.to(busyBar, { opacity: 1, duration: 0.2 });
    busyTween = gsap.fromTo($("i", busyBar), { xPercent: -100 }, { xPercent: 340, duration: 1.1, ease: "power1.inOut", repeat: -1 });
  } else if (!on && busyTween) {
    gsap.to(busyBar, { opacity: 0, duration: 0.3, onComplete: () => { busyTween?.kill(); busyTween = null; } });
  }
}

// ── keyboard ────────────────────────────────────────────────────────────
addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (/input|textarea|select/i.test(e.target.tagName)) return;
  if (e.key === "Escape") { closeDetail(); return; }
  const n = Number(e.key);
  if (n >= 1 && n <= ORDER.length) navigate(ORDER[n - 1]);
});

// ── store wiring ────────────────────────────────────────────────────────
const ctx = { store, scene, navigate, openDetail, closeDetail, toast, seed };
store.onChange((s, detail) => {
  renderHeader();
  renderBusy();
  if (detail?.reason === "verdict-error") {
    toast(`Ruling did not save: ${detail.message || "network"}`, "err", 6000);
  }
  current.instance?.update?.(s, detail?.reason);
  if (drawerOpen && detail?.reason !== "busy" && detail?.reason !== "reviewed") {
    const runId = $(".drawer-inner", drawer)?.dataset?.run;
    if (runId) renderDetail(drawer, runId, ctx);
  }
});

// Offline banner (shown once per session).
store.addEventListener("change", (e) => {
  if (e.detail?.reason !== "mode") return;
  if (store.s.mode === "offline" && !sessionStorage.getItem("hm.offlineSeen")) {
    sessionStorage.setItem("hm.offlineSeen", "1");
    const banner = h(`<div class="banner"><span>Backend unreachable. Bridge is running in <b>replay mode</b>: decide, replay, Chaos, and the dial all simulate in the browser. To pin a live backend, add <code>?api=https://your-backend</code>.</span><button type="button" class="btn btn-sm" data-dismiss>Got it</button></div>`);
    $(".shell").insertBefore(banner, $("#view"));
    banner.querySelector("[data-dismiss]").addEventListener("click", () => banner.remove());
  }
});

route();
renderHeader();
store.init().then(() => {
  if (!store.live) {
    toast("Backend not found. Start FastAPI on :8000, or open http://127.0.0.1:8000 — Live Server :5500 cannot show the inbox by itself.", "err", 9000);
    return;
  }
  const n = store.s.health?.inbox?.email_count || store.s.runs.length || 0;
  toast(`Live · official inbox ${n} emails${store.s.apiBase ? " via " + store.s.apiBase : ""}`, "ok", 5000);
});
