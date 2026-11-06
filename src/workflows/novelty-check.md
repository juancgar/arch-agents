---
name: novelty-check
description: Adversarial check of whether a research idea or contribution already exists — facet-by-facet search for the closest prior work, ending in retain / narrow / abandon / unclear per claim, never a bare "novel".
argument-hint: "<the idea or contribution to check>"
---

# Novelty check

1. **G1 Spec:** state the claimed contribution precisely, split into facets: problem · mechanism · data/setting · claimed result. If the idea is too vague to search, ask the user one batched question.
2. {{agent:novelty-checker}} searches per facet (local library → arXiv → OpenReview → web). For broad ideas, run one {{agent:researcher}} per facet in parallel first and give the novelty-checker their verified results.
3. **G5 Grounding:**
   - every prior-work citation passes `verify_citations`;
   - {{agent:claim-checker}} checks the "what it does" and "what remains different" statements for the closest 3–5 papers.
4. Present the closest-prior-work table and the per-claim verdict: **retain · narrow (to what) · abandon · unclear (and what search would settle it)**.

LLM novelty judgments are unreliable without retrieved evidence, so the table *is* the answer. Never summarize it as just "this is novel".
