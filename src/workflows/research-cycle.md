---
name: research-cycle
description: Complete academic investigation of a research question — library check, parallel discovery, synthesis, adversarial novelty check, claim-level grounding, and a saved report with an INDEX entry.
argument-hint: "<research question>"
---

# Research cycle

1. **Context first:** read `{{path:research_hub}}/INDEX.md`, `{{path:research_hub}}/01_topics/current.md` and the relevant existing notes and syntheses; search the library (`paper_search`). Don't redo work that already exists — build on it and say so.
2. **Discovery:** split the question into facets and run one {{agent:researcher}} per facet in parallel (see **research-discovery**). Each returns verified sources with supporting passages.
3. **Synthesis:** {{agent:synthesizer}} integrates the evidence. Every claim is tagged EXPLICIT (cited), SYNTHESIS or SPECULATION, and candidate gaps come with evidence and confidence.
4. **Novelty:** {{agent:novelty-checker}} independently tests the candidate gaps and directions against prior work (closest-prior-work table).
5. **G5 Grounding:**
   - `verify_citations` on the synthesis;
   - {{agent:claim-checker}} on its factual claims;
   - remove or soften unsupported claims;
   - mark any gap the novelty-checker narrowed or rejected.
6. **Save:** {{agent:documenter}} saves the report (to `04_syntheses` for a literature synthesis, or `09_reports` for a major investigation). For a substantial investigation it also adds a link to `{{path:research_hub}}/INDEX.md`.

{{include:research-locations}}

Don't stop at a chat answer and don't print the whole document instead of saving it. Don't implement software unless asked (that's **full-cycle**).

Report:
- what was researched;
- strongest prior work and closest competing approaches;
- defensible directions and their confidence;
- novelty risks;
- claim-check summary;
- the saved path, as confirmed by the documenter.
