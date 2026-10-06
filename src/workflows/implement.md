---
name: implement
description: Add substantial new behaviour — a feature, integration, API, data path or subsystem. Spec → plan → tests first → single-writer implementation → checks → independent review.
argument-hint: "<what to build> [--hard]"
---

# Implement

1. **G1 Spec:** goal · checkable acceptance criteria · constraints · assumptions · out of scope. Ask one batched clarifying question only if the answer changes the plan.
2. **Context:** read `AGENTS.md`/`CLAUDE.md` and `REPOSITORY_MAP.md` if present; {{agent:explore}} for the areas involved. Memory (optional): search `architecture_decision`, `interface_contract` and `repo_constraint` when prior design could change the plan; verify what you use.
3. **Unresolved architecture?** If the work needs a genuine *whether/what* decision, run **architecture-change** first. Otherwise continue.
4. **Plan:** {{agent:planner}} produces steps, each with an acceptance test.
   - L: {{agent:reviewer}} reviews the plan before any code is written.
5. **G2 Tests first:** {{agent:tester}} (mode A) writes behaviour tests from the spec and plan, and confirms they fail for the right reason.
6. **Build:** {{agent:coder}} implements in plan order, phase by phase for large plans, running the tests after each phase (G3).
7. **G4 Review:** {{agent:reviewer}} receives the spec, the diff and the logs. CHANGES REQUIRED → coder fixes → tester re-runs → reviewer re-checks. At most 2 rounds, then report what remains.
8. **Docs:** if user-facing behaviour or persistent docs changed, {{agent:documenter}} updates them.

**Hard mode** (the user passes `--hard`, or G6 failed once) — sample-and-select:
1. Run 3 independent coder attempts from the same spec, plan and tests,{{#claude}} each in an isolated git worktree (`isolation: worktree`),{{/claude}}{{#opencode}} each on its own git branch,{{/opencode}} without sharing their reasoning.
2. Select the attempt that passes the most tests.
3. Break ties with {{agent:reviewer}} comparing the finalists in both orders.

Only use hard mode where tests can tell the attempts apart.

Answer with what was built, which acceptance criteria are verified (and how), review verdict, and open issues.
