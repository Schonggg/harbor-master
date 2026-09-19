# ADR-002: Three-state verdict

## Status
Accepted

## Context
Binary match/mismatch forces false alarms into HOLD or sweeps uncertainty under the rug.

## Decision
Per-field: `MATCH | MISMATCH | UNCERTAIN`.  
Case roll-up: `CLEAR | HOLD | PILOT`.

UNCERTAIN / PILOT is a first-class product surface (Pilot desk), not a failure.

## Consequences
- Autonomy dial adjusts the UNCERTAIN band
- Human time concentrates on PILOT queue
- Ledger promotions convert repeated PILOTs into future MATCH/MISMATCH
