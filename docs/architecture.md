# Architecture

## Layers

```
Email → Scout → Reader → Court → Risk → Report → Bridge
                              ↑
                         Ledger ← Pilot
```

1. **Scout** — rules first, LLM second, unknown last. Saves tokens.
2. **Reader** — parsers by mime; LLM extracts `FieldValue` with evidence. Never verdicts.
3. **Court** — Prosecutor files charges; Defender runs 7 strategies; Judge emits MATCH / MISMATCH / UNCERTAIN.
4. **Risk** — prices exposure from `config/risk_matrix.yaml`, rolls up to CLEAR / HOLD / PILOT.
5. **Ledger** — pilot decisions become permanent rules; Replayer rescans history.
6. **Reliability** — retry, degrade, chaos injectors for live demo.
7. **Bridge** — static web UI over FastAPI.

## Hard invariants

- LLM output never sets `CourtState` or `CaseVerdict`.
- OCR confusion strategy only when `EvidenceSource` is OCR/VISION.
- Empty / corrupt / timeout paths force PILOT with failure codes.

## Config as product

All business knowledge lives under `config/` so judges can open YAML live.
