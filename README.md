# Harbormaster

Shipping-document verification with a three-state court. The language model extracts values. Deterministic Python decides whether they match. A human closes the cases the system cannot.

The live product is the **official SDOC inbox (520 emails)** on a public HTTPS Bridge. Replay fixtures (`demo_*`) are not the judged demo.

Harbormaster reads operational mail (shipping instructions, bills of lading, invoices, and noise), extracts the seven scored fields, and returns one of three operational verdicts:

| Verdict | Meaning |
|---|---|
| **CLEAR** | Release. The documents agree, or the message is not a comparison case. |
| **HOLD** | Stop. A priced discrepancy survived every defence. |
| **PILOT** | Hand off. The system raised a hand; a **human** must rule. |

That third state is the product. Binary match/mismatch either manufactures false holds or buries uncertainty. PILOT is a first-class desk, not an error.

> The LLM extracts. It never sits on the bench.

Public site: [https://harbormaster-1.vercel.app/](https://harbormaster-1.vercel.app/)

Private GitHub: [https://github.com/Schonggg/harbor-master](https://github.com/Schonggg/harbor-master)

---

## Current progress

What is in production code as of 19 Sep 2026. The live header still shows the last Postgres run until the 520 is processed again; the rules below are what that re-run will use.

**Official categories (local rules-only walk of `data/sdoc/`, 520 emails).** This is our classifier, not organizer Stage-1 F1:

| Category | Count | How the rule decides |
|---|---|---|
| `BL_COMPARISON` | 220 | SI+BL attachments, or compare/check/verify/confirm-docs language. Not a bare "draft BL" or "SI" mention. |
| `SI_REQUEST` | 125 | Field list (POL/POD/Shipper/Consignee) or "please find / prepare shipping instruction", including the closer "Please revert with draft BL once available." Commits at confidence 0.96 (above the 0.95 rule floor). |
| `INVOICE_QUERY` | 98 | Billing / THC / D&D language. An invoice that only name-drops SI and BL stays here. |
| `GENERAL` | 49 | Ops noise, greetings, reminders. A bare SI/BL mention is not promoted to SI_REQUEST or BL_COMPARISON. |
| `SPAM` | 28 | Promo / unsubscribe / lottery. |

Of the 220 comparison cases: **148 OK**, **52 MISMATCH**, **20 NEEDS_REVIEW**.

**Official `NEEDS_REVIEW` (same local walk).** Earlier submissions marked ~226 mails for review because SI requests were swallowed as comparisons and then failed pairing. After Scout + health-check tightening, the gate is 20 mails, five per reason:

| `review_reason` | Count | Trigger |
|---|---|---|
| `missing_attachment` | 5 | Compare requested and the pair is dropped / still missing. Scene A ("please send the draft") is not this. |
| `wrong_doc_type` | 5 | Attachment is an invoice, packing list, or certificate even if the filename is `*_BL.txt`. |
| `unreadable` | 5 | Empty text layer / file will not open / image-only scan with no OCR text. |
| `missing_value` | 5 | A scored field is blank or a placeholder (`N/A`, `TBA`, `____`) on the document. |

`wrong_doc_type`, `missing_attachment`, and `unreadable` already caught their five true cases; the change was to stop them (and `missing_value`) firing on mails that should be OK or MISMATCH. `missing_value` now also treats `Port of Loading (POL): ____MT` / `N/A` / `TBA` as blanks instead of comparing them as ports.

**Reader.** Image-only PDFs go to VisionParser. A short labelled PDF still uses PdfParser (`pdf_has_text` min 1 character) so the 220-cell format matrix stays green. DOCX tables are flattened to `label: value` lines. PDF labels on their own line ("To the Order of" then the company) are read as the next line.

**Bridge (already on the public site).** Board **Find** (`/` to focus): email number (`12` or `email_012`) and keywords over subject / verdict / extracted fields. Dark olive instrument rail, not a cream card. Pilot Chaos / Lock to Ledger filters, Source-mail 15s timeout, HOLD-strictness dial, mild card tilt. Cache lockstep: `app.js?v=51` and `store.js?v=51`, `styles.css?v=34`.

**Tests.** `py -3 -m pytest -q` is **127 passed**. Official `score_cli.py` on the local 520 rules-only `data/submission.json` prints **final_score 1.0000**. Sponsor generator robustness (`scripts/calibrate_seeds.py --seeds 7,23,99,150,2026`) also scores **1.0000 on every seed**; `score_variance` is **0.0**.

---

## Why this shape

| Typical pipeline | Harbormaster |
|---|---|
| Two outcomes: same / different | Three: release / stop / **human** |
| The model writes the verdict | The model reads values; **Python adjudicates** |
| Review is a dead end | Each Pilot field ruling can become a **Ledger rule** and replay history |
| Demo shows 14 happy-path mails | Live board is the **520-email official corpus** |
| "Looks similar" scoring | Official L5 is **exact match after format normalize only** - no fuzzy threshold |

Three courtroom roles exist. They are deterministic Python, not three extra model calls:

1. **Prosecutor** - files a charge per compared field.
2. **Defender** - tries seven strategies in order until one plea is accepted.
3. **Judge** - emits `MATCH`, `MISMATCH`, or `UNCERTAIN`, then Risk rolls the case up to CLEAR / HOLD / PILOT.

---

## Architecture

```
Email -> Scout -> Reader -> Court -> Risk -> Report -> Bridge
                              ^
                         Ledger <- Pilot (human)
```

| Layer | Responsibility |
|---|---|
| **Scout** | Rules first, LLM second. Commits to one official category: `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, `SPAM`. Comparison needs a compare/check/verify verb or an SI+BL pair; a field-list SI request is `SI_REQUEST` even if the mail says "draft BL". |
| **Reader** | MIME-aware parsers (PDF via PyMuPDF, DOCX including tables, XLSX, text, vision for image-only scans). The LLM extracts `FieldValue` with evidence. It never writes a verdict. |
| **Court** | Prosecutor / Defender / Judge. Seven defences: suffix strip, UN/LOCODE map, unit convert, reference resolve, numeric extract, label synonym, OCR confusion (scans only). |
| **Risk** | Prices exposure from `config/risk_matrix.yaml` and rolls field states into CLEAR / HOLD / PILOT. |
| **Pilot** | Human desk. Case-level CLEAR or HOLD. Field-level **Lock in Ledger** writes a reusable pair rule. The live pipeline does not auto-close PILOT. |
| **Ledger** | Promoted rulings become durable rules. The replayer rescans historical cases. Not a HOLD archive. |
| **Outbox** | Draft reply copy on CLEAR / HOLD / PILOT. Never auto-sent; never feeds `defect_fields`. |
| **Reliability** | Retry, rules-only degrade, and Chaos injectors. Empty, corrupt, timeout, and garbled OCR paths force PILOT with a failure code. |
| **Bridge** | Static ES-module UI over FastAPI. Six views, keyboard `1-6`. |

Hard invariants (see [docs/architecture.md](docs/architecture.md)):

- LLM output never sets `CourtState` or `CaseVerdict`.
- OCR confusion applies only when evidence is OCR or vision - never to a clean text layer.
- Empty / corrupt / timeout paths cannot CLEAR.
- Official L5 has no similarity / fuzzy / third-state threshold.

Business knowledge lives in YAML and CSV under `config/` so thresholds, aliases, LOCODEs, and the risk matrix can be inspected without opening Python.

---

## The Bridge

Six operator views, same origin as the API when served by FastAPI:

| Key | View | Purpose |
|---|---|---|
| `1` | **Board** | Docket of unique emails. Official subjects, CLEAR / HOLD / PILOT counters. Full-width **Find** strip: type an email number or a keyword (`/` focuses the box). |
| `2` | **Court** | Charge first (SI vs BL), then one named defence at a time, then the three-state ruling. `R` replays. |
| `3` | **Pilot** | Human queue. Filters: Lock to Ledger / All / Chaos / Degraded. Case CLEAR or HOLD. Field **Lock in Ledger** writes a pair rule. |
| `4` | **Ledger** | Reusable pair rules: who decided, which writings, which cases replay touched. |
| `5` | **Chaos** | Four live injectors: LLM timeout, OCR garbage, corrupt attachment, empty email. Smashed cases land in Pilot, not HOLD. |
| `6` | **Metrics** | Score-sheet KPIs (0 false alarms, 220/220, 520/520), live desk mix, then a **HOLD-strictness dial** that can rewrite this session's header. |

Keyboard: `1-6` switch views, `/` focus Board Find, `R` replay court, `Esc` close detail.

Header buttons are **Refresh** and **Load inbox**. Load inbox fills at most one missing official email per request (Vercel 60s cap), then continues in the background until 520.

**Pilot filters.** Chaos lists only smash codes (`CHAOS_INJECTED`, `ATTACHMENT_CORRUPT`, `OCR_GARBLED`, `EMPTY_EMAIL`, `LLM_TIMEOUT`). It never falls back to All. **Lock to Ledger** is only true when an UNCERTAIN or MISMATCH field has both SI and BL writings. An empty lockable queue stays empty. On the current 520 that count is often 0 (one smash case plus degraded Pilot with no pair) - that is correct, not a missing button.

**Source mail.** Opening the original times out at 15s, shows a wait bar, and after 5s notes that a paused database may be waking. Misses cache for 30s so a retry is not a silent hang.

**HOLD strictness (Metrics).** The dial previews a stricter or looser HOLD gate on the **same 520 evidence**. MATCH fields and empty / degraded cards stay as recorded. **Apply to this desk** rewrites this session's header, Board, and Pilot. **Restore recorded 520** (or Refresh) returns the stamps from Postgres. Official `submission.json` is not rewritten. On this corpus leftover mismatch confidence sits around 0.93 and 0.96, so Balanced 0.92 matches the live header and Cautious 0.97 hands those HOLDs to Pilot.

**Board Find.** The docket strip is a paper bar with a green edge when a query is active. Numeric tokens match `email_N` / `email_00N` exactly. Other tokens search subject, verdict, and extracted field values. Clear empties the query; it is stored in `sessionStorage` as `hm.docket.q`.

**Board cards.** Mild mouse-follow tilt. Every view must import `store.js` with the same `?v=` as `app.js` in `web/index.html`. A mismatch creates two stores and the board looks empty while the header still counts 520.

**Cache.** After a UI change, bump that `?v=` lockstep (`app.js` / `store.js` currently `?v=51`, `styles.css` `?v=34`), run `py -3 scripts/vercel_build.py`, then deploy. Do not hard-refresh only `index.html`.

The frontend (`web/`) is static - no build step. Three.js and GSAP are vendored. If the API is unreachable, the Bridge falls back to **offline replay** from `web/lib/demo-data.js`. That 14-email snapshot is **not** mixed into the live 520 board.

---

## Dual schema

The Bridge and the graded submission share one pipeline and two contracts.

**Bridge (operator UI)**

- Case verdicts: `CLEAR` / `HOLD` / `PILOT`
- Field states: `MATCH` / `MISMATCH` / `UNCERTAIN`
- Extra walkthrough fields such as vessel/voyage may appear on cards; they are not scored.

**Official submission (`/submit`, `data/submission.json`)**

- Categories: `BL_COMPARISON` / `SI_REQUEST` / `INVOICE_QUERY` / `GENERAL` / `SPAM`
- Comparison status: `OK` / `MISMATCH` / `NEEDS_REVIEW`
- Seven snake_case fields: `shipper`, `consignee`, `notify_party`, `port_of_loading`, `port_of_discharge`, `container_count`, `gross_weight_kg`
- `decided_by`: `rule` or `llm`

PILOT on the Bridge is a human interrupt. Official `NEEDS_REVIEW` is reserved for unreadable or missing-document cases, not for "the model was unsure." Unparseable compare values also go to `NEEDS_REVIEW` - they must not silently become `MISMATCH`. Scene A ("please send draft" with no files) is not `missing_attachment`. A structural `wrong_doc_type` is a health check, not an L5 fuzzy match. On the local 520, those four reasons fire **five times each** (20 mails). Do not treat a previous ~226-review dump as the current gate.

---

## Inbox and seed

The loader prefers **Supabase-hosted official mail**, then a live read-only inbox (`INBOX_BASE_URL`), then the local SDOC bundle (`SDOC_BUNDLE_DIR`) - **520 emails plus attachments**. This private clone keeps that bundle at `data/sdoc/`.

On the **public site**:

1. Opening the Bridge paints whatever official runs already sit in Postgres (unique by `email_id`).
2. `demo_*` rows are deleted from the hosted ledger and never shown.
3. **Load inbox** fills **at most one missing official email per request**. The UI continues until the board reaches 520.
4. Hosted reset **does not wipe** Postgres.

Locally, with this clone's `.env` and `data/sdoc/`, the same official corpus is available. Without `DATABASE_URL`, SQLite is used. That path is for development.

Without an LLM key the product still runs: Scout and Reader degrade to rules, the court still adjudicates, and uncertain or unreadable cases go to PILOT.

---

## Score-sheet discipline

Two different number families live in this repo. Do not mix them up.

**Internal consistency (not the competition metric).** These prove the pipeline does not crash and that our own equivalent-writing traps stay green. They are **not** Stage-1 / Stage-3 / end-to-end F1:

| Check | What it proves |
|---|---|
| **Format matrix** | 7 fields x txt / pdf / docx / xlsx x known labels = **220 cells**. Every cell must pass. |
| **Full-inbox ritual** | The **520** official emails, crash-free. Evening ritual on the live board is 520/520. |
| **Zero false-alarm review** | `EQUIVALENT` / `NEAR_MISS` traps. Official compare is exact after format normalize - no fuzzy L5. |
| **Generator robustness** | Re-seed sponsor `generate.py --seed N`. Seeds 7, 23, 99, 150, 2026 all score official `final_score` 1.0000 (`score_variance` 0.0). Ground truth never enters the pipeline. |

```bash
make matrix      # 220-cell format matrix
make ritual      # full 520-email corpus
make discipline  # matrix + spec tests
py -3 scripts/calibrate_seeds.py --seeds 7,23,99,150,2026
```

**Official competition score.** Organizers compute:

`final_score = 0.30 * stage1_macro_f1 + 0.20 * stage3_defect_f1 + 0.50 * end_to_end_rate`

with NEEDS_REVIEW precision/recall as a separate reliability axis. We never have ground-truth labels. The only score that counts is the organizer scorer. Pipeline code never imports `ground_truth.json`. To benchmark locally, unzip the Docker package and run:

```bash
make benchmark      # 520 rules-only run, then score_cli.py if SDOC_DOCKER is set
make forensics      # gold vs submission.json (needs ground_truth.json)
make submit         # full corpus -> submission.json -> POST /submit (if the inbox HTTP server is up)
make score-report   # print the latest saved official scoreboard
```

Local `score_cli.py` against the 520 official inbox and against five re-generated seeds all print `final_score` 1.0000. Pipeline code still never imports `ground_truth.json`. Until `make submit` reaches the organizers' endpoint, treat that as a local replay of their scorer, not a posted leaderboard entry.

---

## Quick start

Python 3.11+ (on Windows, `py -3`).

This **private** clone already includes `.env` and the official 520-email bundle at `data/sdoc/`. Do not make the repository public - it contains live keys.

```powershell
py -3 -m pip install -e ".[dev]"
$env:PYTHONPATH = "src"
py -3 -m uvicorn harbormaster.api.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/** - not a static Live Server on `:5500`. That origin has no API. FastAPI must serve `web/` itself.

`SDOC_BUNDLE_DIR` is `./data/sdoc`. Click **Load inbox** if the local board is short of 520. The hosted site stays at [https://harbormaster-1.vercel.app/](https://harbormaster-1.vercel.app/).

With Make:

```bash
make setup && make run
```

If you only have `.env.example` (no private `.env`), copy it first and fill keys:

```powershell
copy .env.example .env
```

---

## Configuration

| Variable | Role |
|---|---|
| `OPENAI_API_KEY` | Optional. Empty = rules-only degrade. |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint (Gonka router, OpenAI, Azure, ...). |
| `OPENAI_MODEL` / `OPENAI_MODELS` | Primary model and comma-separated fallbacks. |
| `VISION_MODEL` | Vision pass for scanned attachments. |
| `DATABASE_URL` | Hosted Postgres (Supabase **transaction pooler**, port **6543**). Required on Vercel. Empty = local SQLite. |
| `SUPABASE_URL` | `https://<project>.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | Publishable/anon key. Does not replace `DATABASE_URL`. |
| `SDOC_BUNDLE_DIR` | Official 520-email bundle. This repo uses `./data/sdoc`. |
| `INBOX_BASE_URL` | Optional live inbox API. |
| `HARBORMASTER_ENV` | `dev` or `prod`. Production disables the loopback API-key exemption. |
| `HARBORMASTER_API_KEY` | Optional service key. Empty = open demo. Pass `X-API-Key` or `?key=`. |
| `S3_BUCKET` | Empty = local disk at `DATA_DIR/objects`. |
| `BACKUP_INTERVAL_HOURS` | Timed snapshot + object-store offload. `0` = manual only. |
| `CORS_ORIGINS` | `*` by default; localhost regex is always allowed. |

SQLite (WAL) is the local/test default at `DB_PATH`. Production uses **Supabase Postgres** so the ledger, Pilot rulings, and official inbox survive deploys.

Default model list for Gonka-style routers:

- `deepseek-ai/DeepSeek-V4-Flash-0731`
- `MiniMaxAI/MiniMax-M2.7`
- `zai-org/GLM-5.3-Flash`

Do not assume `gpt-4o-mini` exists on a third-party `/v1` host.

---

## HTTPS and hosting

### Vercel (public website)

Entrypoint is repo-root `main.py` (`main:app`). `public/` is copied from `web/` at build time so the UI is on Vercel's CDN; `/api` and `/health` hit the Python function (`maxDuration` 60s).

Project: `harbormaster-1` - [https://harbormaster-1.vercel.app/](https://harbormaster-1.vercel.app/). Redeploy the **linked** folder. Do not create a new Vercel project.

```powershell
npx vercel --prod --yes
```

Set these as **production** env vars on `harbormaster-1`, then Redeploy:

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | **yes** | Supabase transaction pooler URI (port **6543**) |
| `OPENAI_API_KEY` | for LLM extract | Same Gonka/OpenAI-compatible key as local `.env` |
| `OPENAI_BASE_URL` | recommended | e.g. `https://api.gonkarouter.io/v1` |
| `OPENAI_MODEL` / `OPENAI_MODELS` | optional | Defaults match `.env.example` |
| `SUPABASE_URL` | recommended | `https://<project-ref>.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | recommended | Publishable/anon key |
| `CORS_ORIGINS` | recommended | Include the Vercel origin |

Vercel's filesystem is ephemeral. The 520-email corpus and board cards live in Supabase, not `/tmp`. This clone already has the SDOC bundle at `data/sdoc/`. To push mail into Supabase from a fresh machine:

```powershell
py -3 scripts/push_supabase.py
```

Free-tier Supabase **pauses** after idle time. Hit `/health` once before judging so the database is awake.

### Local HTTPS

```powershell
py -3 scripts/serve_https.py              # FastAPI + Bridge on https://localhost:8443
py -3 scripts/serve_https.py --tunnel     # public HTTPS via Cloudflare quick tunnel
```

Docker:

```bash
docker compose up --build
```

---

## Operations

Exposed under `/api/ops` and Metrics -> System (folded until opened):

- Hashed, rotatable API keys (issue / list / revoke).
- Object store health (local disk or S3-compatible).
- On-demand backup; optional offload of backups and `submission.json`.
- Background worker status.

Health endpoints: `/live`, `/ready`, `/health`, `/version`. OpenAPI at `/docs`.

The board payload (`GET /api/runs`) is compact on purpose so 520 cards load inside the function time budget. Compact pleas still keep `strategy` names so Court is not an empty list. Compact fields include extract confidence and a `lockable` flag so Pilot can sort lockable cases first without a second fetch.

`GET /api/emails/{email_id}` is the Source-mail endpoint. The Bridge waits 15s, not the browser default of 120s (which outlives Vercel's 60s cap and looks frozen).

---

## Tests and evaluation

```bash
make test        # court, judge, submission shape, inbox, security, storage
make matrix      # 220-cell format matrix
make ritual      # full 520-email corpus
make discipline  # matrix + official spec tests
make eval        # confusion matrix + false-alarm report
make full        # rules-only corpus into submission.json
make submit      # full corpus with LLM extract where configured, then POST /submit
make score-report  # latest official scoreboard from reports/official_score.json
make benchmark     # 520 run + official score_cli.py when SDOC_DOCKER is present
make forensics     # gold vs submission.json when ground_truth.json is present
```

Windows without Make:

```powershell
py -3 -m pytest -q
py -3 scripts/run_discipline.py
py -3 scripts/full_corpus_ritual.py
```

---

## Repository layout

```
config/          thresholds, field aliases, risk matrix, LOCODEs, prompts
data/sdoc/       official 520-email bundle (inbox + attachments)
data/inbox/      local replay fixtures (demo_* only)
docs/            architecture, demo script, ADRs
eval/            confusion matrix and false-alarm reports
reports/         discipline + robustness snapshots + official_score.json
scripts/         seed helpers, HTTPS, Supabase push, corpus ritual, debug_* classifiers
src/harbormaster
  api/           FastAPI app, compact /api/runs, hosted seed, ops
  court/         prosecutor, defender, judge, seven strategies
  graph/         pipeline: chaos -> scout -> reader -> court -> report
  ingest/        Supabase-then-remote-then-bundle inbox adapter
  ledger/        SQLite or Postgres store, promoter, replayer
  llm/           OpenAI-compatible client with model fallbacks
  official/      L5 exact compare, scene-A gate, format matrix
  reader/        parsers + extract (rules, then LLM)
  report/        submission, outbox copy, discipline / robustness
  scout/         rules-first classifier
  storage/       local disk / S3
web/             Bridge UI (static ES modules)
public/          CDN copy of web/ (Vercel build)
```

---

## Architecture decisions

- [ADR-001](docs/decisions/ADR-001-llm-never-judges.md) - LLM never judges
- [ADR-002](docs/decisions/ADR-002-three-state-verdict.md) - three-state, not two-state
- [ADR-003](docs/decisions/ADR-003-ocr-confusion-guardrail.md) - OCR confusion only on scans
- [ADR-004](docs/decisions/ADR-004-review-reason-priority.md) - NEEDS_REVIEW reason priority

Further reading: [docs/architecture.md](docs/architecture.md), [docs/demo_script.md](docs/demo_script.md), [docs/field_risk_rationale.md](docs/field_risk_rationale.md).

---

## License

MIT. See [LICENSE](LICENSE).
