# ADR-004: Review-reason priority

## Status
Accepted

## Context
`health_check()` can match more than one NEEDS_REVIEW signal on the same mail
(missing attachment, unreadable file, wrong document type, missing value).
Only one `review_reason` is allowed. The order is short-circuiting if/return
in `src/harbormaster/reader/health_check.py`. Judges may ask why that order.

## Decision
Evaluate signals in this order, stop at the first hit:

1. `missing_attachment`
2. `unreadable`
3. `wrong_doc_type`
4. `missing_value`

Business reasons:

- Missing attachment beats a damaged file. If the pair never arrived, there is
  nothing whose OCR quality or emptiness can be judged.
- Unreadable beats wrong type. A scan with no text layer cannot be classified
  as an invoice, packing list, or SI/BL.
- Wrong type beats a missing field. If the file is not an SI or BL, asking
  which compare field is blank is meaningless.

## Consequences
- Tests in `tests/test_health_check.py` (`test_priority_when_multiple_conditions_hit`)
  lock the three pairwise overlaps above.
- Changing the order is an official-schema change, not a style tweak.
