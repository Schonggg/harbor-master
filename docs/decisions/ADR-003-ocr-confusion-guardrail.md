# ADR-003: OCR confusion guardrail

## Status
Accepted

## Context
OCR commonly confuses 0/O, 1/I, 5/S. Applying those rewrites to clean digital text would hide real typos.

## Decision
`OcrConfusionStrategy` runs only when either side's `EvidenceSource` is `ocr` or `vision`.

## Consequences
- Text-alarm reduction on scans without weakening text-layer integrity
- Demo can show the guardrail rejecting a text-source near-miss
