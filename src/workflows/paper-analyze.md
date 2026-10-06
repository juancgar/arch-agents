---
name: paper-analyze
description: Deeply analyse one paper (arXiv ID or local PDF) from its full text and save a standardized, claim-checked research note.
argument-hint: "<arXiv ID or local PDF path>"
---

# Paper analysis

1. {{agent:paper-analyst}} reads the actual paper (downloaded arXiv full text or the local PDF) — never only the title or abstract — and returns the structured analysis with section/page locations for key claims and numbers.
2. Check the analysis for missing major sections or unsupported claims. If critical evidence is missing, ask the paper-analyst for **one** focused follow-up rather than restarting.
3. **G5 Grounding:** {{agent:claim-checker}} checks the analysis against the paper, prioritising the method description, every quantitative result and the novelty-relevant claims. Fix or remove what fails.
4. {{agent:documenter}} saves the note with the paper-analysis metadata block:
   ```
   ---
   type: paper-analysis
   arxiv_id: <id>
   title: <title>
   date_analyzed: <today>
   status: analyzed
   ---
   ```
   Keep the full structured analysis, including "Reusable research facts".{{#opencode}} Automatic research-memory persistence is paused (Phase 2A pilot): don't delegate memory writes or create coding candidates for research.{{/opencode}}

{{include:research-locations}}

Report: the paper analysed · note path (as confirmed by the documenter) · claim-check summary · any evidence that remained incomplete.
