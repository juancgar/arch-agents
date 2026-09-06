---
description: Full academic research cycle with discovery, adversarial novelty checking, synthesis, and persistent documentation
agent: orchestrator
---

Run a complete academic research workflow for:

$ARGUMENTS

Required stages:

1. Inspect ~/ResearchHub first.
2. Read:
   - ~/ResearchHub/INDEX.md
   - ~/ResearchHub/01_topics/current.md
   - relevant existing paper notes and syntheses

3. Delegate literature discovery to researcher.

4. Independently delegate novelty checking to novelty-checker.

5. Delegate evidence integration to synthesizer.

6. Determine:
   - strongest prior work
   - methodological patterns
   - closest competing approaches
   - novelty risks
   - unresolved research gaps
   - defensible research directions

7. Delegate the COMPLETE validated findings to documenter.

8. documenter MUST save the final report under:

   ~/ResearchHub/04_syntheses/

   Use filename format:

   YYYY-MM-DD_short-descriptive-topic.md

9. Update ~/ResearchHub/INDEX.md with a link to the new synthesis if the
   investigation is substantial.

The final response must tell the user the exact saved file path.

Do not stop after synthesis.
Do not merely print the document in the terminal.
Do not claim the file exists unless documenter confirms writing it.

Do not implement software unless explicitly requested.
