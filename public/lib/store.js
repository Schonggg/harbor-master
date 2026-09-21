// Single source of truth for the Bridge.
// Cache-bust ?v= MUST match in index.html, app.js, and every view import.
// Two different versions load two stores — header then shows 520 while the board is empty.
//   live    — talks to the FastAPI backend (same origin or ?api=)
//   offline — replays captured payloads from demo-data.js and simulates the
//             ledger/replay loop client-side so the demo still tells its story
//             on a static HTTPS host.
import { request, API_BASE, ApiError, discoverApiBase, EMAIL_GET_TIMEOUT_MS, markReviewed as postReviewed } from "./api.js?v=67";
import { DEMO_RUNS, DEMO_EMAILS, DEMO_CHAOS, DEMO_AUTONOMY } from "./demo-data.js";

const clone = (v) => (typeof structuredClone === "function" ? structuredClone(v) : JSON.parse(JSON.stringify(v)));
const isDemoId = (id) => String(id || "").startsWith("demo_");
function dropDemoRuns(runs) {
  return (runs || []).filter((r) => !isDemoId(r.email_id));
}
function applyOfflineFiled(runs) {
  let filed = new Set();
  try { filed = new Set(JSON.parse(localStorage.getItem("hm.reviewedIds") || "[]")); } catch { /* private mode */ }
  if (!filed.size) return runs;
  return (runs || []).map((r) => {
    if (!filed.has(r.email_id)) return r;
    const nextCard = { ...(r.payload?.card || {}), reviewed: true };
    return { ...r, reviewed: true, payload: { ...r.payload, card: nextCard } };
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function isHostedOrigin() {
  const host = location.hostname || "";
  return /\.vercel\.app$/i.test(host);
}
async function withRetry(fn, tries) {
  let last;
  for (let i = 0; i < tries; i++) {
    try {
      return await fn();
    } catch (err) {
      last = err;
      await sleep(700 * (i + 1));
    }
  }
  throw last;
}
const uid = () => (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "") : Math.random().toString(16).slice(2) + Date.now().toString(16));

export function normalizedPairKey(left, right) {
  const a = String(left ?? "").toUpperCase().split(/\s+/).filter(Boolean).join(" ");
  const b = String(right ?? "").toUpperCase().split(/\s+/).filter(Boolean).join(" ");
  const pair = [a, b].sort();
  return `${pair[0]}||${pair[1]}`;
}

export function rollup(fieldVerdicts) {
  const states = fieldVerdicts.map((f) => f.state);
  if (states.includes("MISMATCH")) return "HOLD";
  if (states.includes("UNCERTAIN")) return "PILOT";
  return "CLEAR";
}

/**
 * Re-run the Judge's threshold logic on a card with a different match floor.
 * Strategies (pleas) are deterministic and already recorded, so only the
 * confidence gate moves. Returns a new card; does not mutate.
 */
export function reAdjudicate(card, floor, extractMin = 0.75) {
  if (!card) return { field_verdicts: [], verdict: "PILOT" };
  const recorded = card.verdict;
  let gated = 0;
  const fvs = (card.field_verdicts || []).map((fv) => {
    if (!fv.charge) return fv;
    if (fv.state === "MATCH") return fv;
    if ((fv.pleas || []).some((p) => p.accepted)) return fv;
    if (/^ledger/.test(fv.rationale || "")) return fv;
    gated += 1;
    const conf = Math.min(fv.charge.left?.confidence ?? 0.5, fv.charge.right?.confidence ?? 0.5);
    const state = conf < extractMin || conf < floor ? "UNCERTAIN" : "MISMATCH";
    return { ...fv, state };
  });
  // Empty / degraded cards have nothing left to re-gate — keep the recorded stamp.
  if (!gated) return { ...card, field_verdicts: fvs, verdict: recorded || rollup(fvs) };
  if ((card.failure_codes || []).length > 0 && recorded === "PILOT") {
    return { ...card, field_verdicts: fvs, verdict: "PILOT" };
  }
  return { ...card, field_verdicts: fvs, verdict: rollup(fvs) };
}

export function computeMetrics(runs) {
  const labels = [
    "booking_confirmation", "shipping_instruction", "bill_of_lading", "amendment_request",
    "discrepancy_query", "invoice_or_charges", "operational_noise", "unknown",
  ];
  const counts = { CLEAR: 0, HOLD: 0, PILOT: 0 };
  const confusion = {};
  labels.forEach((g) => { confusion[g] = {}; labels.forEach((p) => { confusion[g][p] = 0; }); });
  const fieldStats = {};
  let avoided = 0;
  let mismatch = 0;
  let exposure = 0;
  let degraded = 0;
  for (const r of runs) {
    const card = r.payload?.card || {};
    counts[card.verdict || r.verdict] = (counts[card.verdict || r.verdict] || 0) + 1;
    const label = card.scout?.label || "unknown";
    // Gold label comes from the demo tag when present; otherwise self-confusion.
    const gold = r.gold_label || label;
    if (confusion[gold]) confusion[gold][label] = (confusion[gold][label] || 0) + 1;
    if (card.degraded) degraded++;
    for (const fv of card.field_verdicts || []) {
      const fs = (fieldStats[fv.field] ||= { MATCH: 0, MISMATCH: 0, UNCERTAIN: 0 });
      fs[fv.state] = (fs[fv.state] || 0) + 1;
      if (fv.state === "MATCH" && fv.winning_strategy) avoided++;
      if (fv.state === "MISMATCH") { mismatch++; exposure += Number(fv.exposure_usd) || 0; }
    }
  }
  const total = runs.length || 1;
  return {
    runs: runs.length,
    verdict_counts: counts,
    pilot_queue: counts.PILOT,
    false_alarms: 0,
    avoided_false_alarms: avoided,
    auto_rate_pct: Math.round((1000 * (counts.CLEAR + counts.HOLD)) / total) / 10,
    mismatch_fields: mismatch,
    exposure_usd: exposure,
    degraded_runs: degraded,
    field_stats: fieldStats,
    confusion,
    labels,
  };
}

class Store extends EventTarget {
  constructor() {
    super();
    this.state = {
      mode: "connecting", // connecting | live | offline
      apiBase: API_BASE,
      runs: [],
      emails: {},
      ledger: [],
      metrics: null,
      autonomy: null,
      deskFloor: null,
      lastChaos: null,
      lastError: null,
      health: null,
      busy: 0,
      inbox: [],
      job: null,
    };
    this._offline = { ledger: [], reviews: [] };
    this._pendingVerdicts = new Map();
    this._emailMiss = new Map();
    this._emailInflight = new Map();
  }

  get s() { return this.state; }
  get live() { return this.state.mode === "live"; }

  emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }
  onChange(fn) {
    this.addEventListener("change", (e) => fn(this.state, e.detail));
  }
  set(patch, reason = "") {
    Object.assign(this.state, patch);
    this.emit("change", { patch, reason });
  }

  async withBusy(fn) {
    this.set({ busy: this.state.busy + 1 }, "busy");
    try {
      return await fn();
    } finally {
      this.set({ busy: Math.max(0, this.state.busy - 1) }, "busy");
    }
  }

  // ── boot ───────────────────────────────────────────────────────────────
  hosted() {
    return this.state.health?.inbox?.source === "supabase"
      || this.state.health?.db?.backend === "postgres"
      || isHostedOrigin();
  }

  async init() {
    const hostedPage = isHostedOrigin();
    try {
      const health = await withRetry(async () => {
        const hit = await discoverApiBase();
        if (!hit) throw new ApiError("No Harbormaster API on this page or localhost:8000", 0, "network");
        return hit;
      }, hostedPage ? 5 : 2);
      this.set({ health, apiBase: API_BASE }, "health");
      await withRetry(() => this.refresh(), hostedPage ? 4 : 1);
      this.set({ mode: "live" }, "mode");
      this._startHealthPoll();
      const officialCount = health.inbox?.email_count || health.inbox?.official_count || 0;
      const have = (this.state.runs || []).length;
      if (this.hosted() && officialCount > 0 && have < officialCount) this.startFill();
    } catch (err) {
      if (hostedPage) {
        this.set({ lastError: err instanceof ApiError ? err.message : String(err?.message || err || "") }, "health");
        this._recoverLive();
        return;
      }
      this.enterOffline(err);
    }
  }

  _recoverLive() {
    if (this._recoverTimer) return;
    this._recoverTimer = setInterval(async () => {
      try {
        const health = await discoverApiBase();
        if (!health) return;
        this.set({ health, apiBase: API_BASE }, "health");
        await this.refresh();
        this.set({ mode: "live" }, "mode");
        clearInterval(this._recoverTimer);
        this._recoverTimer = null;
        this._startHealthPoll();
        const officialCount = health.inbox?.email_count || health.inbox?.official_count || 0;
        if (officialCount > 0 && this.state.runs.length < officialCount) this.startFill();
      } catch {
        /* keep CONNECTING until the hosted ledger answers */
      }
    }, 2500);
  }

  _startHealthPoll() {
    if (this._healthTimer) clearInterval(this._healthTimer);
    this._healthTimer = setInterval(() => {
      if (!this.live) return;
      request("/health", { timeout: 20000 })
        .then((health) => this.set({ health }, "health"))
        .catch(() => {});
    }, 20000);
  }

  enterOffline(err) {
    this._offline = { ledger: [], reviews: [] };
    this.set({
      mode: "offline",
      lastError: err instanceof ApiError ? err.message : String(err?.message || err || ""),
      runs: applyOfflineFiled(clone(DEMO_RUNS).map((r) => decorateRun(r, DEMO_EMAILS))),
      emails: clone(DEMO_EMAILS),
      ledger: [],
      autonomy: clone(DEMO_AUTONOMY),
    }, "mode");
    this.recompute();
  }

  recompute() {
    this.set({ metrics: computeMetrics(this.state.runs) }, "metrics");
  }

  async hydrateRun(runId) {
    if (!this.live || !runId || this._hydrating === runId) return;
    this._hydrating = runId;
    try {
      const row = await request(`/api/runs/${encodeURIComponent(runId)}`, { timeout: 20000 });
      if (!row?.payload) return;
      const runs = this.state.runs.map((r) => {
        if (r.run_id !== runId && r.case_id !== runId) return r;
        const filed = Boolean(
          r.reviewed || r.payload?.card?.reviewed || row.reviewed || row.payload?.card?.reviewed
        );
        const payload = { ...(row.payload || r.payload || {}) };
        payload.card = { ...(payload.card || {}), reviewed: filed };
        return decorateRun({ ...r, ...row, reviewed: filed, payload }, this.state.emails);
      });
      this.set({ runs }, "hydrate");
    } catch {
      /* compact board payload is enough for the docket */
    } finally {
      this._hydrating = null;
    }
  }

  async refresh() {
    if (!this.live && this.state.mode !== "connecting") { this.recompute(); return; }
    const runs = await request("/api/runs", { timeout: 45000 });
    const patched = this._applyPending(dropDemoRuns(runs || []));
    const decorated = patched.map((r) => decorateRun(r, this.state.emails));
    const local = computeMetrics(decorated);
    this.set({
      runs: decorated,
      metrics: local,
      deskFloor: null,
    }, "refresh");
    this.prefetchEmails(decorated).catch(() => {});
    Promise.all([
      request("/api/ledger", { timeout: 20000 }).catch(() => null),
      request("/api/metrics", { timeout: 20000 }).catch(() => null),
      request("/api/autonomy", { timeout: 8000 }).catch(() => null),
    ]).then(([ledger, metrics, autonomy]) => {
      const merged = metrics
        ? { ...local, ...metrics, exposure_usd: local.exposure_usd, degraded_runs: local.degraded_runs, confusion: local.confusion, verdict_counts: local.verdict_counts || metrics.verdict_counts, runs: decorated.length }
        : local;
      this.set({
        ledger: Array.isArray(ledger) ? ledger : this.state.ledger,
        metrics: merged,
        autonomy: autonomy || this.state.autonomy,
      }, "refresh-aux");
    });
  }

  _mergeLedger(rules) {
    const incoming = (Array.isArray(rules) ? rules : [rules]).filter((r) => r?.rule_id);
    if (!incoming.length) return;
    const have = new Set((this.state.ledger || []).map((r) => r.rule_id));
    const extra = incoming.filter((r) => !have.has(r.rule_id));
    if (!extra.length) return;
    this.set({ ledger: [...extra, ...(this.state.ledger || [])] }, "ledger");
  }

  _emailMissFresh(emailId) {
    const until = this._emailMiss.get(emailId);
    return Boolean(until && Date.now() < until);
  }

  /** Original messages carry the demo gold label (meta.tag) used by the confusion matrix. */
  async prefetchEmails(runs, extraIds = []) {
    const preferred = [...extraIds, ...(runs || []).map((r) => r.email_id)];
    const ids = [...new Set(preferred.filter(Boolean))]
      .filter((id) => id && !this.state.emails[id] && !this._emailMissFresh(id))
      .slice(0, 8);
    if (!ids.length || !this.live) return;
    await Promise.all(ids.map((id) => this.getEmail(id).catch(() => null)));
  }

  // ── lookups ────────────────────────────────────────────────────────────
  runById(id) {
    return this.state.runs.find((r) => r.run_id === id || r.case_id === id || r.email_id === id) || null;
  }
  pilotQueue() {
    return this.state.runs.filter((r) => (r.payload?.card?.verdict || r.verdict) === "PILOT");
  }
  counts() {
    const c = { CLEAR: 0, HOLD: 0, PILOT: 0 };
    for (const r of this.state.runs) {
      const id = String(r.email_id || "");
      if (id.startsWith("chaos_") || id.startsWith("demo_")) continue;
      const v = r.payload?.card?.verdict || r.verdict;
      if (c[v] != null) c[v] += 1;
    }
    return c;
  }
  ruleById(id) {
    return this.state.ledger.find((r) => r.rule_id === id) || null;
  }

  async getEmail(emailId, { timeout = EMAIL_GET_TIMEOUT_MS } = {}) {
    if (!emailId) return null;
    if (this.state.emails[emailId]) return this.state.emails[emailId];
    if (this._emailMissFresh(emailId)) return null;
    if (!this.live) return null;
    const pending = this._emailInflight.get(emailId);
    if (pending) return pending;
    const job = this._fetchEmail(emailId, timeout);
    this._emailInflight.set(emailId, job);
    try {
      return await job;
    } finally {
      this._emailInflight.delete(emailId);
    }
  }

  async _fetchEmail(emailId, timeout) {
    try {
      const em = await request(`/api/emails/${encodeURIComponent(emailId)}`, { timeout });
      if (em) {
        this.state.emails[emailId] = em;
        this._emailMiss.delete(emailId);
        return em;
      }
      this._emailMiss.set(emailId, Date.now() + 30000);
      return null;
    } catch {
      this._emailMiss.set(emailId, Date.now() + 30000);
      return null;
    }
  }

  // ── actions ────────────────────────────────────────────────────────────
  async seed() {
    if (this.state.mode === "connecting") {
      return { seeded: [], official: 0, queued: 0, reason: "connecting" };
    }
    if (!this.live) {
      this._offline = { ledger: [], reviews: [] };
      this.set({ runs: applyOfflineFiled(clone(DEMO_RUNS).map((r) => decorateRun(r, DEMO_EMAILS))), ledger: [], lastChaos: null }, "seed");
      this.recompute();
      return { seeded: this.state.runs.map((r) => ({ email_id: r.email_id, verdict: r.verdict })) };
    }
    await this.refresh();
    const officialCount = this.state.health?.inbox?.email_count || this.state.health?.inbox?.official_count || this.state.runs.length;
    const queued = Math.max(0, officialCount - this.state.runs.length);
    if (queued) this.startFill();
    return { seeded: this.state.runs, official: this.state.runs.length, queued, reason: "fill" };
  }

  startFill() {
    if (this._filling) return;
    this._filling = true;
    this._fillFails = 0;
    const tick = async () => {
      if (!this.live) {
        this._filling = false;
        return;
      }
      const need = this.state.health?.inbox?.email_count || this.state.health?.inbox?.official_count || 0;
      if (need && this.state.runs.length >= need) {
        this._filling = false;
        this.set({ job: null }, "job");
        return;
      }
      try {
        const out = await request("/api/demo/seed", { method: "POST", timeout: 50000 });
        this._fillFails = 0;
        await this.refresh();
        const queued = out?.queued || 0;
        const total = out?.official || need || this.state.runs.length;
        this.set({
          job: queued ? { status: "running", processed: this.state.runs.length, total, updated_at: new Date().toISOString() } : null,
        }, "job");
        if (queued > 0) this._fillTimer = setTimeout(tick, 500);
        else this._filling = false;
      } catch {
        this._fillFails += 1;
        await this.refresh().catch(() => {});
        if (this._fillFails >= 8) {
          this._filling = false;
          this.set({ job: null }, "job");
          return;
        }
        this._fillTimer = setTimeout(tick, 2000 * this._fillFails);
      }
    };
    tick();
  }

  watchJob(jobId) {
    if (this._jobTimer) clearInterval(this._jobTimer);
    this._jobTimer = setInterval(async () => {
      if (!this.live) return;
      try {
        const job = await request(`/api/run/jobs/${encodeURIComponent(jobId)}`, { timeout: 8000 });
        const jobAt = Date.parse(job?.updated_at || "") || 0;
        const stale = !jobAt || (Date.now() - jobAt) > 10 * 60 * 1000;
        if (stale && (job.status === "running" || job.status === "queued")) {
          clearInterval(this._jobTimer);
          this._jobTimer = null;
          this.set({ job: { ...job, status: "error", error: "stale job" } }, "job");
          return;
        }
        this.set({ job }, "job");
        await this.refresh();
        if (job.status === "done" || job.status === "error") {
          clearInterval(this._jobTimer);
          this._jobTimer = null;
        }
      } catch {
        clearInterval(this._jobTimer);
        this._jobTimer = null;
      }
    }, 3000);
  }

  async resetChaos() {
    if (this.live) {
      await request("/api/chaos/reset", { method: "POST", timeout: 45000 });
    }
    return this.reset();
  }

  async reset() {
    return this.withBusy(async () => {
      if (this.live) {
        const hosted = this.state.health?.inbox?.source === "supabase"
          || this.state.health?.db?.backend === "postgres";
        if (hosted) {
          // Drop throwaway chaos_* smash rows so the berth returns to the official 520.
          await request("/api/chaos/reset", { method: "POST", timeout: 45000 }).catch(() => null);
          await this.refresh();
          return { reason: "hosted ledger preserved" };
        }
        await request("/api/demo/reset", { method: "POST" });
        await request("/api/autonomy", { method: "POST", body: { preset: "balanced" } }).catch(() => {});
        await this.refresh();
        return;
      }
      this._offline = { ledger: [], reviews: [] };
      this.set({ runs: [], ledger: [], lastChaos: null, autonomy: clone(DEMO_AUTONOMY) }, "reset");
      this.recompute();
    });
  }

  _applyPending(runs) {
    if (!this._pendingVerdicts?.size) return runs;
    let out = runs;
    for (const [caseId, p] of this._pendingVerdicts) {
      out = out.map((run) => {
        if (run.case_id !== caseId && run.run_id !== caseId && run.email_id !== caseId) return run;
        const card = {
          ...(run.payload?.card || {}),
          verdict: p.verdict,
          pilot_override: true,
          pilot_override_note: p.note || "",
          ...(p.draft ? { reply_draft: p.draft } : {}),
        };
        return { ...run, verdict: p.verdict, payload: { ...run.payload, card } };
      });
    }
    return out;
  }

  async setVerdict({ caseId, verdict, note = "" }) {
    const before = this.pilotQueue().map((r) => r.run_id);
    const patchRuns = (runs, draft) => runs.map((run) => {
      if (run.case_id !== caseId && run.run_id !== caseId && run.email_id !== caseId) return run;
      const card = {
        ...(run.payload?.card || {}),
        verdict,
        pilot_override: true,
        pilot_override_note: note,
        ...(draft ? { reply_draft: draft } : {}),
      };
      return { ...run, verdict, payload: { ...run.payload, card } };
    });
    const taught = this.live ? [] : this._offlinePromoteOnVerdict(caseId, verdict, note);
    this.set({ runs: patchRuns(this.state.runs) }, "decide");
    this.recompute();
    const afterSet = new Set(this.pilotQueue().map((r) => r.run_id));
    const released = before.filter((id) => !afterSet.has(id));
    const result = { verdict, released, queue_before: before.length, queue_after: afterSet.size, rules: taught, replay: { updated: 0 } };
    if (this.live) {
      this._pendingVerdicts.set(caseId, { verdict, note, draft: null });
      try {
        const out = await request("/api/review/verdict", {
          method: "POST",
          timeout: 20000,
          body: { case_id: caseId, verdict, reviewer: "pilot", note },
        });
        if (out?.reply_draft) {
          this._pendingVerdicts.set(caseId, { verdict, note, draft: out.reply_draft });
          this.set({ runs: patchRuns(this.state.runs, out.reply_draft) }, "decide");
        }
        this._pendingVerdicts.delete(caseId);
        result.rules = out?.rules || [];
        result.replay = out?.replay || { updated: 0 };
        this._mergeLedger(result.rules);
        await this.refresh().catch(() => {});
        const after = new Set(this.pilotQueue().map((r) => r.run_id));
        result.released = before.filter((id) => !after.has(id));
        result.queue_after = after.size;
      } catch (err) {
        this._pendingVerdicts.delete(caseId);
        await this.refresh().catch(() => {});
        this.emit("change", { reason: "verdict-error", message: err.message });
        throw err;
      }
    }
    return result;
  }

  async decide({ caseId, field, decision, left, right, note = "" }) {
    return this.withBusy(async () => {
      const before = this.pilotQueue().map((r) => r.run_id);
      let out;
      if (this.live) {
        out = await request("/api/review/decide", {
          method: "POST",
          body: { case_id: caseId, field, decision, left_value: left, right_value: right, promote_to_ledger: true, reviewer: "pilot", note },
        });
        this._mergeLedger(out?.rule ? [out.rule] : []);
        await this.refresh();
      } else {
        out = this._offlineDecide({ caseId, field, decision, left, right, note });
      }
      const afterSet = new Set(this.pilotQueue().map((r) => r.run_id));
      const released = before.filter((id) => !afterSet.has(id));
      return { ...out, released, queue_before: before.length, queue_after: afterSet.size };
    });
  }

  _offlineDecide({ caseId, field, decision, left, right, note }) {
    const review = { review_id: uid(), case_id: caseId, field, decision, promote_to_ledger: true, reviewer: "pilot", note, created_at: new Date().toISOString() };
    if (decision === "defer") return { review, rule: null, replay: { updated: 0 } };
    const rule = {
      rule_id: uid(),
      field,
      left_pattern: left,
      right_pattern: right,
      normalized_key: normalizedPairKey(left, right),
      decision,
      source_case_id: caseId,
      active: true,
      created_at: new Date().toISOString(),
      created_by: "pilot",
      revoked_at: null,
      note,
    };
    const ledger = [rule, ...this.state.ledger];
    let updated = 0;
    const runs = this.state.runs.map((run) => {
      const card = run.payload?.card;
      if (!card) return run;
      let changed = false;
      const fvs = (card.field_verdicts || []).map((fv) => {
        if (fv.field !== rule.field || !fv.charge) return fv;
        const key = normalizedPairKey(fv.charge.left?.raw_value, fv.charge.right?.raw_value);
        if (key !== rule.normalized_key) return fv;
        changed = true;
        return {
          ...fv,
          state: decision === "accept_as_match" ? "MATCH" : "MISMATCH",
          rationale: `ledger replay:${rule.rule_id}`,
          winning_strategy: decision === "accept_as_match" ? "ledger" : fv.winning_strategy,
        };
      });
      if (!changed) return run;
      updated++;
      const verdict = rollup(fvs);
      return { ...run, verdict, payload: { ...run.payload, card: { ...card, field_verdicts: fvs, verdict } } };
    });
    this.set({ runs, ledger }, "decide");
    this.recompute();
    return { review, rule, replay: { updated, rule_id: rule.rule_id } };
  }

  _offlinePromoteOnVerdict(caseId, verdict, note = "") {
    const run = this.state.runs.find((r) => r.case_id === caseId || r.run_id === caseId || r.email_id === caseId);
    const fvs = run?.payload?.card?.field_verdicts || [];
    const decision = verdict === "CLEAR" ? "accept_as_match" : "confirm_mismatch";
    const rules = [];
    for (const fv of fvs) {
      const left = fv.charge?.left?.raw_value || fv.left_value || "";
      const right = fv.charge?.right?.raw_value || fv.right_value || "";
      if ((fv.state !== "UNCERTAIN" && fv.state !== "MISMATCH") || !String(left).trim() || !String(right).trim()) continue;
      if (/^ledger/.test(fv.rationale || "")) continue;
      const key = normalizedPairKey(left, right);
      if (this.state.ledger.some((r) => r.active !== false && r.field === fv.field && r.normalized_key === key)) continue;
      const out = this._offlineDecide({ caseId, field: fv.field, decision, left, right, note: note || `case ${verdict}` });
      if (out?.rule) rules.push(out.rule);
    }
    const emailId = run?.email_id || caseId;
    if (!this.state.ledger.some((r) => r.active !== false && r.field === "case" && r.left_pattern === emailId && r.right_pattern === verdict)) {
      const stamp = this._offlineDecide({ caseId, field: "case", decision, left: emailId, right: verdict, note: note || `case ${verdict}` });
      if (stamp?.rule) rules.push(stamp.rule);
    }
    return rules;
  }

  async markReviewed(emailIds, reviewed = true) {
    const ids = [...new Set((emailIds || []).map((id) => String(id || "").trim()).filter(Boolean))];
    if (!ids.length) return { ok: true, count: 0, reviewed: Boolean(reviewed) };
    const flag = Boolean(reviewed);
    const previous = this.state.runs;
    const hit = new Set(ids);
    const patched = previous.map((run) => {
      if (!hit.has(run.email_id)) return run;
      const nextCard = { ...(run.payload?.card || {}), reviewed: flag };
      return { ...run, reviewed: flag, payload: { ...run.payload, card: nextCard } };
    });
    this.set({ runs: patched }, "reviewed");
    try {
      if (this.live) {
        await postReviewed(ids, flag);
      } else {
        try {
          const cur = new Set(JSON.parse(localStorage.getItem("hm.reviewedIds") || "[]"));
          ids.forEach((id) => (flag ? cur.add(id) : cur.delete(id)));
          localStorage.setItem("hm.reviewedIds", JSON.stringify([...cur]));
        } catch { /* private mode */ }
      }
    } catch (err) {
      this.set({ runs: previous }, "reviewed");
      throw err;
    }
    return { ok: true, count: ids.length, reviewed: flag };
  }

  async revoke(ruleId) {
    return this.withBusy(async () => {
      if (this.live) {
        await request(`/api/ledger/${encodeURIComponent(ruleId)}/revoke`, { method: "POST" });
        await this.refresh();
        return;
      }
      const ledger = this.state.ledger.map((r) => (r.rule_id === ruleId ? { ...r, active: false, revoked_at: new Date().toISOString() } : r));
      this.set({ ledger }, "revoke");
    });
  }

  async chaos(type) {
    return this.withBusy(async () => {
      let payload;
      if (this.live) {
        payload = await request(`/api/chaos/${encodeURIComponent(type)}`, { method: "POST", body: {}, timeout: 20000 });
        await this.refresh();
      } else {
        payload = clone(DEMO_CHAOS[type]);
        if (!payload) throw new ApiError(`no offline snapshot for ${type}`, 0, "offline");
        payload.run_id = uid();
        payload.card.case_id = payload.run_id;
        const run = decorateRun({ run_id: payload.run_id, case_id: payload.run_id, email_id: payload.card.email_id, verdict: payload.card.verdict, payload, created_at: new Date().toISOString() });
        this.set({ runs: [run, ...this.state.runs] }, "chaos");
        this.recompute();
      }
      this.set({ lastChaos: { type, payload, at: Date.now() } }, "chaos");
      return payload;
    });
  }

  async setAutonomy({ preset, floor, band }) {
    const body = {};
    if (preset) body.preset = preset;
    if (floor != null) body.match_confidence_floor = floor;
    if (band != null) body.uncertain_band = band;
    if (this.live) {
      const out = await request("/api/autonomy", { method: "POST", body });
      this.set({ autonomy: out }, "autonomy");
      return out;
    }
    const cur = this.state.autonomy || clone(DEMO_AUTONOMY);
    const t = { ...cur.thresholds };
    if (preset && t.presets?.[preset]) Object.assign(t, t.presets[preset]);
    if (floor != null) t.match_confidence_floor = floor;
    if (band != null) t.uncertain_band = band;
    const history = [...(cur.history || []), { match_confidence_floor: t.match_confidence_floor, uncertain_band: t.uncertain_band, preset: preset || null }].slice(-50);
    const out = { thresholds: t, history };
    this.set({ autonomy: out }, "autonomy");
    return out;
  }

  /** What-if projection used by the dial: verdict counts at a given floor. */
  project(floor) {
    const t = this.state.autonomy?.thresholds || {};
    const extractMin = t.extract_min_confidence ?? 0.75;
    const c = { CLEAR: 0, HOLD: 0, PILOT: 0 };
    for (const r of this.state.runs) {
      const card = r._sourceCard || r.payload?.card;
      if (!card) continue;
      const v = reAdjudicate(card, floor, extractMin).verdict;
      c[v] = (c[v] || 0) + 1;
    }
    const total = this.state.runs.length || 1;
    return { ...c, total: this.state.runs.length, auto: Math.round((1000 * (c.CLEAR + c.HOLD)) / total) / 10 };
  }

  recordedCounts() {
    const c = { CLEAR: 0, HOLD: 0, PILOT: 0 };
    for (const r of this.state.runs) {
      const v = (r._sourceCard || r.payload?.card)?.verdict || r.verdict;
      c[v] = (c[v] || 0) + 1;
    }
    return c;
  }

  applyFloorToDesk(floor) {
    const extractMin = this.state.autonomy?.thresholds?.extract_min_confidence ?? 0.75;
    const runs = this.state.runs.map((r) => {
      const src = r._sourceCard || clone(r.payload?.card || {});
      const card = reAdjudicate(src, floor, extractMin);
      return {
        ...r,
        _sourceCard: src,
        verdict: card.verdict,
        payload: { ...(r.payload || {}), card: { ...card, verdict: card.verdict } },
      };
    });
    this.set({ runs, deskFloor: floor }, "autonomy-apply");
    this.recompute();
    return this.counts();
  }

  restoreRecordedDesk() {
    const runs = this.state.runs.map((r) => {
      if (!r._sourceCard) return r;
      const card = clone(r._sourceCard);
      return {
        ...r,
        _sourceCard: r._sourceCard,
        verdict: card.verdict,
        payload: { ...(r.payload || {}), card },
      };
    });
    this.set({ runs, deskFloor: null }, "autonomy-restore");
    this.recompute();
    return this.counts();
  }

  async refreshHealth() {
    if (!this.live) return null;
    try {
      const health = await request("/health", { timeout: 20000 });
      this.set({ health }, "health");
      return health;
    } catch {
      return this.state.health;
    }
  }

  async exportSubmission() {
    return this.withBusy(async () => request("/api/submission/export", { timeout: 60000 }));
  }

  async submitOfficial() {
    return this.withBusy(async () => request("/api/submission/submit", { method: "POST", timeout: 120000 }));
  }

  async runFull({ rulesOnly = true } = {}) {
    return this.withBusy(async () => {
      const out = await request("/api/run", { method: "POST", body: { full: true, rules_only: rulesOnly, two_value: true }, timeout: 30000 });
      return out;
    });
  }

  async jobStatus() {
    return request("/api/run/status", { timeout: 8000 });
  }

  async opsStatus() {
    if (!this.live) return null;
    return request("/api/ops/status", { timeout: 8000 });
  }

  async backup({ cloud = true } = {}) {
    return this.withBusy(async () => request(`/api/ops/backup?cloud=${cloud ? "true" : "false"}`, { method: "POST", timeout: 60000 }));
  }

  async listKeys() {
    return request("/api/keys");
  }

  async issueKey(name = "integration") {
    return request("/api/keys", { method: "POST", body: { name } });
  }

  async revokeKey(keyId) {
    return request(`/api/keys/${encodeURIComponent(keyId)}/revoke`, { method: "POST" });
  }
}

/** Attach cheap derived fields so views don't recompute them. */
function decorateRun(run, emails = {}) {
  const card = run.payload?.card || {};
  const tag = run.payload?.gold_label || emails[run.email_id]?.meta?.tag || null;
  const mismatch = (card.field_verdicts || []).filter((f) => f.state === "MISMATCH");
  const uncertain = (card.field_verdicts || []).filter((f) => f.state === "UNCERTAIN");
  return {
    ...run,
    verdict: card.verdict || run.verdict,
    gold_label: tag,
    _mismatch: mismatch.map((f) => f.field),
    _uncertain: uncertain.map((f) => f.field),
  };
}

export const store = new Store();
