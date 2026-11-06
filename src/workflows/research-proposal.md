---
name: research-proposal
description: Build a defensible research proposal from verified literature gaps — design, adversarial novelty review, one revision, rigorous review of falsifiability and scope, then save.
argument-hint: "<research direction or idea>"
---

# Research proposal

1. **Evidence:** gather the relevant paper notes, literature reviews and comparisons (`paper_search` plus the folders), and memory if relevant. Identify the strongest evidence-supported gap. If the idea is already substantially occupied, say so and reformulate toward a defensible gap instead of forcing novelty.
2. **Design:** {{agent:proposal-designer}} writes the proposal. Any draft file goes only to the staging folder.
3. **Novelty review:** {{agent:novelty-checker}} independently checks the proposal's contributions facet by facet.
4. **One revision** if the novelty-checker found serious overlap: send its evidence back to the proposal-designer, which writes the complete revised draft to `{{path:research_workspace}}/.staging/revised-proposal.md`. The staging file is not the final proposal.
5. **G4 Review:** {{agent:reviewer}} checks the staged proposal for:
   - internal consistency;
   - a falsifiable hypothesis;
   - experiment–method alignment and adequate baselines;
   - experiments that can distinguish the contribution from the closest prior work;
   - master's-level scope.
6. **G5 Grounding:** `verify_citations` and {{agent:claim-checker}} on the state-of-the-art, gap and novelty-defense sections.
7. {{agent:documenter}} saves the final proposal.{{#opencode}} Automatic research-memory persistence is paused (Phase 2A pilot); keep durable decisions in the saved proposal.{{/opencode}}

{{include:research-locations}}

Report:
- proposal path;
- research question and hypothesis;
- closest prior work and the strongest novelty distinction;
- biggest scientific risk;
- novelty verdict and scope verdict;
- claim-check summary.
