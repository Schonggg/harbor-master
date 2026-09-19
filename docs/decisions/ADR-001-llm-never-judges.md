# ADR-001: LLM never judges

## Status
Accepted

## Context
LLMs are strong at reading messy shipping text and weak at consistent equality under legal/ops risk.

## Decision
LLM may classify (Scout) and extract (Reader) only.  
`CourtState` and `CaseVerdict` are produced solely by deterministic Python in `court/` + `risk/`.

## Consequences
- Auditable transcripts for every field
- Strategies are unit-testable without mocking an LLM
- Degraded mode (rules-only) still yields a principled PILOT/HOLD path
