---
description: Compare 2-5 analyzed papers and produce a research-gap/novelty matrix
agent: orchestrator
model: openai/gpt-6-astra
subtask: false
---

Compare these papers:

$ARGUMENTS

Workflow:

1. Interpret the arguments as 2-5 paper identifiers or note filenames.

2. Locate their structured analyses under:

   research/notes/papers/

3. If an analysis is missing:
   - report which paper is missing;
   - do not invent its contents;
   - use paper-analyst only if the underlying paper is available.

4. Delegate the evidence-based comparison to `paper-comparator`.

5. The comparison must be grounded in the analyzed notes.
   Unsupported details must be marked unknown.

6. Delegate the final result to `documenter`.

Save it under:

research/literature-reviews/comparisons/

Filename:

<first-paper>_vs_<second-paper>[_and_more].md

7. Keep "Reusable Findings" in the saved comparison. Automatic research-memory
   persistence is paused during the Phase 2A shadow pilot. Do not delegate a
   memory write or create a coding-memory candidate for it.

Finish by reporting:
- papers compared
- report path
- strongest overlap
- strongest research gap
- that automatic research-memory persistence is paused
