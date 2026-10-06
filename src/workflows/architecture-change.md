---
name: architecture-change
description: Decide whether and what to build — architecture choices, platforms (e.g. "should we use Docker?"), service boundaries, databases, deployment, CI/CD, framework migrations, environment redesign. Architect decides, reviewer challenges; implementation only if explicitly requested.
argument-hint: "<the decision to make> [and implement]"
---

# Architecture change

The architect decides **whether/what**. The planner is never run before the architect here.

1. **G1 Spec:** the decision to make, the requirements (stated vs assumed) and the constraints (budget, team, existing systems, reversibility needs).
2. **Context:** `AGENTS.md`/`REPOSITORY_MAP.md`, {{agent:explore}} on the current system; Git/GitHub only when current design intent matters. Memory (optional): `architecture_decision`, `environment_constraint`, `repo_constraint` (`interface_contract` when contracts matter) — historical context the architect must re-evaluate, not a decision.
3. **Decide:** {{agent:architect}} produces options, trade-offs, a recommendation, migration and rollback, and a verification plan.
   - L, or high-stakes and hard to reverse: consider asking the architect for two independent proposals (separate briefs, no shared reasoning) and have the reviewer compare them in both orders.
4. **G4 Challenge:** {{agent:reviewer}} reviews the proposal against the requirements: missing options, unstated assumptions, migration risk, rollback gaps, verification gaps.
5. **Stop here** if the user asked to analyze, recommend, compare or evaluate — no planner, no coder.

If the user also asked for implementation and the recommendation is to proceed, continue with **implement** (planner → tester → coder → reviewer), passing the architect's decision as part of the spec.

Answer with the recommendation, the main trade-offs, the reviewer's challenges and how they were resolved, and what would change the decision.
