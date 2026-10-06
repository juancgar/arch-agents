---
description: Generate a thematic literature review from analyzed papers
agent: orchestrator
model: openai/gpt-6-astra
subtask: false
---

Literature review question:

$ARGUMENTS

Workflow:

1. Search:
   research/notes/papers/
   research/literature-reviews/comparisons/

2. Identify the analyzed papers relevant to the question.

3. Do NOT use papers merely because they exist.
   Include only papers materially relevant to the review question.

4. If critical prior work appears to be missing, report the gap in coverage.
   Do not silently invent evidence.

5. Delegate the thematic synthesis to `literature-reviewer`.

6. Check that:
   - synthesis is thematic, not paper-by-paper;
   - important factual claims contain paper-ID citations;
   - verified evidence and inference are distinguished;
   - research gaps are actually supported by the reviewed literature.

7. Delegate the finalized review to `documenter`.

Save under:

research/literature-reviews/

Use a short descriptive filename ending in:

-literature-review.md

8. Keep "Reusable Findings" in the saved review. Automatic research-memory
   persistence is paused during the Phase 2A shadow pilot. Do not delegate
   memory writes or create coding-memory candidates for this research.

Finish with:
- papers included
- review path
- strongest consensus
- strongest contradiction
- highest-confidence research gap
- that automatic research-memory persistence is paused
