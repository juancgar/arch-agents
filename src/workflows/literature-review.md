---
name: literature-review
description: Thematic literature review on a question, built from analysed paper notes and comparisons, with every paper-specific claim cited and claim-checked.
argument-hint: "<review question>"
---

# Literature review

1. **Select evidence:** search the paper notes and comparisons (and `paper_search`) for papers **materially** relevant to the question — not every paper that exists. If critical prior work seems missing, report the coverage gap; optionally run **research-discovery** to fill it before writing.
2. {{agent:literature-reviewer}} writes the thematic review (not paper-by-paper), citing every substantive claim as `[arXiv-ID]`.
3. **Check structure:**
   - the review is thematic;
   - factual claims carry citations;
   - verified synthesis is separated from inference;
   - gaps are supported by the reviewed literature.
   Send it back once if not.
4. **G5 Grounding:** `verify_citations` on the review, then {{agent:claim-checker}}. Fix or remove unsupported claims before saving.
5. {{agent:documenter}} saves it, keeping "Reusable Findings".{{#opencode}} Automatic research-memory persistence is paused (Phase 2A pilot).{{/opencode}}

{{include:research-locations}}

Report:
- papers included and missing coverage;
- review path;
- strongest consensus;
- strongest contradiction;
- highest-confidence gap;
- claim-check summary.
