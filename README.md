# Harbormaster

**Shipping-document verification with a three-state court.** The language model extracts values. Deterministic Python decides whether they match. A human closes the cases the system cannot.

The live product is the **official SDOC inbox ΓÇö 520 emails** ΓÇö on a public HTTPS Bridge. Replay fixtures (`demo_*`) are not the demo.

Harbormaster reads operational mail ΓÇö shipping instructions, bills of lading, invoices, and noise ΓÇö extracts the seven scored fields, and returns one of three operational verdicts:

| Verdict | Meaning |
|---|---|
| **CLEAR** | Release. The documents agree, or the message is not a comparison case. |
| **HOLD** | Stop. A priced discrepancy survived every defence. |
| **PILOT** | Hand off. The system raised a hand; a **human** must rule. |

That third state is the product. Binary match/mismatch either manufactures false holds or buries uncertainty. PILOT is a first-class desk, not an error.

> *The LLM extracts. It never sits on the bench.*

Public site: [https://harbormaster-1.vercel.app/](https://harbormaster-1.vercel.app/)

---

## Why this shape

| Typical pipeline | Harbormaster |
|---|---|
| Two outcomes: same / different | Three: release / stop / **human** |
| The model writes the verdict | The model reads values; **Python adjudicates** |
| Review is a dead end | Each Pilot ruling can become a **permanent ledger rule** and replay history |
| Demo shows 14 happy-path mails | Live board is the **520-email official corpus** |
| ΓÇ£Looks similarΓÇ¥ scoring | Official L5 is **exact match after format normalize only** ΓÇö no fuzzy threshold |

Three courtroom roles exist. They are deterministic Python, not three extra model calls:

1. **Prosecutor** ΓÇö files a charge per compared field.
2. **Defender** ΓÇö tries seven strategies in order until one plea is accepted.
3. **Judge** ΓÇö emits `MATCH`, `MISMATCH`, or `UNCERTAIN`, then Risk rolls the case up to CLEAR / HOLD / PILOT.

---

## Architecture

```
Email ΓåÆ Scout ΓåÆ Reader ΓåÆ Court ΓåÆ Risk ΓåÆ Report ΓåÆ Bridge
                              Γåæ
                         Ledger ΓåÉ Pilot (human)
```

| Layer | Responsibility |
|---|---|
| **Scout** | Rules first, LLM second. Commits to one official category: `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, `SPAM`. |
| **Reader** | MIME-aware parsers (PDF via PyMuPDF, DOCX, XLSX, text, vision). The LLM extracts `FieldValue` with evidence. It never writes a verdict. |
| **Court** | Prosecutor / Defender / Judge. Seven defences: suffix strip, UN/LOCODE map, unit convert, reference resolve, numeric extract, label synonym, OCR confusion (scans only). |
| **Risk** | Prices exposure from `config/risk_matrix.yaml` and rolls field states into CLEAR / HOLD / PILOT. |
| **Pilot** | Human desk. Case-level CLEAR or HOLD. The live pipeline does not auto-close PILOT. |
| **Ledger** | Promoted rulings become durable rules. The replayer rescans historical cases. |
| **Outbox** | Draft reply copy on CLEAR / HOLD / PILOT. Never auto-sent; never feeds `defect_fields`. |
| **Reliability** | Retry, rules-only degrade, and Chaos injectors. Empty, corrupt, timeout, and garbled OCR paths force PILOT with a failure code. |
| **Bridge** | Static ES-module UI over FastAPI. Six views, keyboard `1ΓÇô6`. |

Hard invariants (see [docs/architecture.md](docs/architecture.md)):

- LLM output never sets `CourtState` or `CaseVerdict`.
- OCR confusion applies only when evidence is OCR or vision ΓÇö never to a clean text layer.
- Empty / corrupt / timeout paths cannot CLEAR.
- Official L5 has no similarity / fuzzy / third-state threshold.

Business knowledge lives in YAML and CSV under `config/` so thresholds, aliases, LOCODEs, and the risk matrix can be inspected without opening Python.

---

## The Bridge

Six operator views, same origin as the API when served by FastAPI:

| Key | View | Purpose |
|---|---|---|
| `1` | **Board** | Docket of unique emails. Official subjects, CLEAR / HOLD / PILOT counters. |
| `2` | **Court** | Animated transcript: charge ΓåÆ seven defences ΓåÆ three-state field verdict. `R` replays. |
| `3` | **Pilot** | Human queue. Side-by-side values; stamp CLEAR or HOLD. Counts move immediately (optimistic), then persist. |
| `4` | **Ledger** | Rule provenance ΓÇö who decided, which pair, which cases the replay touched. |
| `5` | **Chaos** | Four live injectors: LLM timeout, OCR garbage, corrupt attachment, empty email. |
| `6` | **Metrics** | Confusion matrix, false-alarm report, autonomy dial, score-sheet / robustness, system / keys / backup. |

Keyboard: `1ΓÇô6` switch views, `R` replay court, `Esc` close detail.

The frontend (`web/`) is static ΓÇö no build step. Three.js and GSAP are vendored. If the API is unreachable, the Bridge falls back to **offline replay** from `web/lib/demo-data.js` so the walkthrough still works on a static host. That 14-email snapshot is **not** mixed into the live 520 board.

Refresh the snapshot with:

```powershell
py -3 scripts/capture_demo_data.py --api http://127.0.0.1:8000
```

---

## Dual schema

The Bridge and the graded submission share one pipeline and two contracts.

**Bridge (operator UI)**

- Case verdicts: `CLEAR` ┬╖ `HOLD` ┬╖ `PILOT`
- Field states: `MATCH` ┬╖ `MISMATCH` ┬╖ `UNCERTAIN`
- Extra walkthrough fields such as vessel/voyage may appear on cards; they are not scored.

**Official submission (`/submit`, `data/submission.json`)**

- Categories: `BL_COMPARISON` ┬╖ `SI_REQUEST` ┬╖ `INVOICE_QUERY` ┬╖ `GENERAL` ┬╖ `SPAM`
- Comparison status: `OK` ┬╖ `MISMATCH` ┬╖ `NEEDS_REVIEW`
- Seven snake_case fields: `shipper`, `consignee`, `notify_party`, `port_of_loading`, `port_of_discharge`, `container_count`, `gross_weight_kg`
- `decided_by`: `rule` or `llm`

PILOT on the Bridge is a human interrupt. Official `NEEDS_REVIEW` is reserved for unreadable or missing-document cases, not for ΓÇ£the model was unsure.ΓÇ¥ Scene A (ΓÇ£please send draftΓÇ¥ with no files) is not `missing_attachment`.

---

## Inbox and seed

The loader prefers **Supabase-hosted official mail**, then a live read-only inbox (`INBOX_BASE_URL`), then the local SDOC bundle (`SDOC_BUNDLE_DIR`) ΓÇö **520 emails plus attachments**.

On the **public site**:

1. Opening the Bridge paints whatever official runs already sit in Postgres (unique by `email_id`).
2. `demo_*` rows are deleted from the hosted ledger and never shown.
3. **Seed and run** fills **at most one missing official email per request** so Vercel stays under the 60s function cap. The UI then continues in the background until the board reaches 520.
4. **Reset does not wipe** a hosted Postgres ledger.

Locally (SQLite, no hosted inbox) Seed can still run the 14 replay fixtures and a background worker. That path is for development, not the judged demo.

Without an LLM key the product still runs: Scout and Reader degrade to rules, the court still adjudicates, and uncertain or unreadable cases go to PILOT.

---

## Score-sheet discipline

Hackathon scoring punishes false alarms harder than misses. Harbormaster treats that as a product constraint, not a slide:

| Ritual | What it proves |
|---|---|
| **Format matrix** | 7 fields ├ù txt / pdf / docx / xlsx ├ù known labels = **220 cells**. Every cell must pass. |
| **Full-corpus ritual** | The **520** official emails, twice daily when judging. |
| **Zero false-alarm review** | `EQUIVALENT` / `NEAR_MISS` traps. Official compare is exact after format normalize ΓÇö no fuzzy L5. |
| **Generator robustness** | Re-seed `generate.py --seed N` when the sponsor generator is present. Ground truth never enters the pipeline. |

```bash
make matrix      # 220-cell format matrix
make ritual      # full 520-email corpus
make discipline  # matrix + spec tests
```

---

## Quick start

Python 3.11+ (on Windows, `py -3`).

```powershell
copy .env.example .env
py -3 -m pip install -e ".[dev]"
$env:PYTHONPATH = "src"
py -3 -m uvicorn harbormaster.api.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/** ΓÇö not a static Live Server on `:5500`. That origin has no API. The supported path is FastAPI serving `web/` itself.

Point `SDOC_BUNDLE_DIR` at the official inbox directory (the folder that contains `inbox/email_*.json`). Then click **Seed and run** once.

With Make:

```bash
make setup && make run
```

---

## Configuration

Copy `.env.example` to `.env`. Nothing operational is hardcoded.

| Variable | Role |
|---|---|
| `OPENAI_API_KEY` | Optional. Empty = rules-only degrade. |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint (Gonka router, OpenAI, Azure, ΓÇª). |
| `OPENAI_MODEL` / `OPENAI_MODELS` | Primary model and comma-separated fallbacks. |
| `VISION_MODEL` | Vision pass for scanned attachments. |
| `DATABASE_URL` | Hosted Postgres (Supabase **transaction pooler**, port **6543**). Required on Vercel. Empty = local SQLite. |
| `SUPABASE_URL` | `https://<project>.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | Publishable/anon key. Does not replace `DATABASE_URL`. |
| `SDOC_BUNDLE_DIR` | Official 520-email bundle. Used locally when the HTTP inbox is down. |
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

Entrypoint is repo-root `main.py` (`main:app`). `public/` is copied from `web/` at build time so the UI is on VercelΓÇÖs CDN; `/api` and `/health` hit the Python function (`maxDuration` 60s).

Project: `harbormaster-1` ΓÇö [https://harbormaster-1.vercel.app/](https://harbormaster-1.vercel.app/). Redeploy the **linked** folder. Do not create a new Vercel project.

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

VercelΓÇÖs filesystem is ephemeral. The 520-email corpus and board cards live in Supabase, not `/tmp`. Push them once from a machine that has the SDOC bundle:

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

Exposed under `/api/ops` and the Metrics ΓåÆ System panel:

- Hashed, rotatable API keys (issue / list / revoke).
- Object store health (local disk or S3-compatible).
- On-demand backup; optional offload of backups and `submission.json`.
- Background worker status.

Health endpoints: `/live`, `/ready`, `/health`, `/version`. OpenAPI at `/docs`.

The board payload (`GET /api/runs`) is compact on purpose so 520 cards load inside the function time budget.

---

## Tests and evaluation

```bash
make test        # court, judge, submission shape, inbox, security, storage
make matrix      # 220-cell format matrix
make ritual      # full 520-email corpus
make discipline  # matrix + official spec tests
make eval        # confusion matrix + false-alarm report
make full        # rules-only corpus into submission.json
make submit      # full corpus with LLM extract where configured
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
data/inbox/      local replay fixtures (not the live 520 board)
docs/            architecture, demo script, ADRs
eval/            confusion matrix and false-alarm reports
reports/         discipline + robustness snapshots
scripts/         seed helpers, HTTPS, Supabase push, corpus ritual
src/harbormaster
  api/           FastAPI app, compact /api/runs, hosted seed, ops
  court/         prosecutor, defender, judge, seven strategies
  graph/         pipeline: chaos ΓåÆ scout ΓåÆ reader ΓåÆ court ΓåÆ report
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

- [ADR-001](docs/decisions/ADR-001-llm-never-judges.md) ΓÇö LLM never judges
- [ADR-002](docs/decisions/ADR-002-three-state-verdict.md) ΓÇö three-state, not two-state
- [ADR-003](docs/decisions/ADR-003-ocr-confusion-guardrail.md) ΓÇö OCR confusion only on scans

Further reading: [docs/architecture.md](docs/architecture.md), [docs/demo_script.md](docs/demo_script.md), [docs/field_risk_rationale.md](docs/field_risk_rationale.md).

---

## License

MIT. See [LICENSE](LICENSE).
