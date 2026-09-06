---
description: Build a defensible research proposal from verified literature gaps
agent: orchestrator
model: openai/gpt-6-astra
subtask: false
---

Develop a research proposal for:

$ARGUMENTS

Workflow:

1. Retrieve relevant prior context from research_memory.

2. Inspect:
   research/notes/papers/
   research/literature-reviews/
   research/literature-reviews/comparisons/

3. Identify the strongest evidence-supported research gap.

4. If the proposed idea appears substantially occupied by existing work,
   do NOT force novelty.
   Explain the overlap and reformulate toward a defensible gap.

5. Delegate proposal design to `proposal-designer`.

6. After receiving the proposal, delegate to `novelty-checker` for an
   independent adversarial novelty review.

7. If novelty-checker identifies serious overlap:
   send the evidence back to proposal-designer for ONE revision.

8. Delegate the final result to `reviewer` to check:
   - internal consistency
   - falsifiability
   - experiment-method alignment
   - baseline adequacy
   - master's-level scope

9. Save the finalized proposal through `documenter` under:

   research/proposals/

Use a short descriptive filename ending:
-proposal.md

10. Send only genuinely durable final research decisions to memory-manager.

Finish with:
- proposal path
- research question
- hypothesis
- closest prior work
- strongest novelty distinction
- biggest scientific risk
- novelty verdict
- scope verdict

## Revision staging rule

When proposal-designer must produce a complete revised proposal after novelty review:

- Do not request `/tmp` or any external-directory path.
- Write the complete revised draft to:
  `research/.staging/revised-proposal.md`
- proposal-designer may write only inside `research/.staging/`.
- The staging file is NOT the final proposal.
- reviewer must review the staged draft.
- documenter performs the final save under `research/proposals/`.
