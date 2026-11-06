---
name: math-check
description: Verify the mathematics and numbers of a document or paper (equations, reported results, statistics, units, consistency) and report every mismatch with the recomputation. Nothing is edited.
argument-hint: "<file path, arXiv ID or paper title>"
---

# Math check

1. Resolve the target: a file path (note, report, proposal, idea) or a paper (local library via `paper_search`, else the arXiv full text). Report-only: no file is edited.
2. {{agent:math-checker}} verifies the target following its protocol. For long documents, brief it to work **section by section** (about 150 lines or one major section at a time), recording the results of each part before moving on, so one giant reasoning pass cannot exhaust its output budget.
3. If the report comes back empty or truncated, re-run on the half of the document that was not covered, not on the whole document again.
4. Optionally (if the user asked for a full check) run {{agent:claim-checker}} in parallel on the same text for citations and factual grounding.

Report: items checked · MISMATCH items with stated vs recomputed values and whether each changes a conclusion · what could not be checked and why · the exact computations run. Offer to apply the corrections through {{agent:documenter}}; do not apply them unasked.
