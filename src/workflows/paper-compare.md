---
name: paper-compare
description: Compare 2–5 analysed papers on a fixed grid and produce an overlap / contradiction / research-gap matrix grounded in their notes.
argument-hint: "<2–5 paper IDs or note filenames>"
---

# Paper comparison

1. Locate each paper's analysis note in the paper-notes folder. If a note is missing:
   - say which;
   - never invent its contents;
   - run **paper-analyze** for it first if the paper itself is available.
2. {{agent:paper-comparator}} compares them grounded in the notes ("Not established in analysed note" where evidence is missing).
3. **G5 Grounding:** {{agent:claim-checker}} checks the comparison matrix and the "Overlap", "Remaining Gaps" and "Novelty Opportunities" sections against the notes.
4. {{agent:documenter}} saves the comparison, keeping "Reusable Findings".{{#opencode}} Automatic research-memory persistence is paused (Phase 2A pilot).{{/opencode}}

{{include:research-locations}}

Report:
- papers compared;
- report path;
- strongest overlap;
- strongest evidence-backed research gap;
- claim-check summary.
