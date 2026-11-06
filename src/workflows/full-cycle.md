---
name: full-cycle
description: Research an idea, validate novelty, then design, implement, test, review and document a minimal prototype — research gates first, coding gates after.
argument-hint: "<idea to research and prototype>"
---

# Full cycle: research → prototype

1. **Research:** run **research-cycle** for the idea (parallel discovery → synthesis → novelty check → claim-level grounding). Produce the defensible scope: prior art, what is actually new, constraints, realistic prototype size.
2. **Decision point:** if the evidence says the prototype isn't justified (already done, or not testable), stop and report — don't build to justify the research.
3. **Design:** if architecture choices are open, run {{agent:architect}}. Then {{agent:planner}} plans a **minimal** prototype whose acceptance tests correspond to the research claims it should demonstrate.
4. **Build:** run **implement**: tests first ({{agent:tester}}) → {{agent:coder}} → checks → {{agent:reviewer}}. Debugging follows the **debug** cap.
5. **Document:** {{agent:documenter}} records the research evidence, architecture decision, implementation, test results, limitations and next experiments.

Never exaggerate novelty or implementation success. Report:
- what is demonstrated (with test evidence);
- what is only claimed;
- the remaining limitations.
