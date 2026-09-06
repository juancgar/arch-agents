---
description: Deep repository-aware refactoring using architecture, history, design patterns, tests, and review
agent: orchestrator
---

REFACTOR: $ARGUMENTS

This is a DEEP repository task.

PHASE 1 — REPOSITORY INTELLIGENCE

Delegate to Explore before planning.

Explore should build the minimum useful repository context from:

1. AGENTS.md and README/documentation.
2. Relevant source files and configuration.
3. LSP:
   - definitions
   - references
   - types
   - implementations
   - call relationships when useful.
4. ast_grep:
   - structural patterns
   - duplicated structures
   - candidate refactoring targets.
5. Read-only Git history:
   - git status
   - remote
   - recent commits
   - relevant file/module history
   - blame only when design intent is unclear.
6. If a GitHub remote exists and GitHub MCP is available:
   inspect repository metadata and only relevant PRs/issues/history.

Do NOT search all GitHub history blindly.

Explore must summarize:

CURRENT STRUCTURE
VERIFIED DEPENDENCIES
RECENT RELEVANT CHANGES
KNOWN DESIGN INTENT
OPEN/RELATED GITHUB WORK
IMPORTANT CONSTRAINTS
UNCERTAINTIES

PHASE 2 — DESIGN

Delegate to Planner.

Planner must:
- identify actual code smells and coupling
- consider appropriate design patterns
- compare alternatives
- avoid patterns that add unnecessary complexity
- create a target design
- identify affected modules/interfaces
- create small migration phases
- specify regression risks and required tests

PHASE 3 — PLAN REVIEW

Delegate the proposed plan to Reviewer.

If Reviewer finds a material problem, revise the plan before coding.

PHASE 4 — IMPLEMENTATION

Delegate implementation to Coder in small coherent phases.

Use LSP and ast_grep when they provide better semantic/structural precision than text search.

PHASE 5 — VERIFICATION

Delegate verification to Tester after meaningful phases.

Use Debugger for non-trivial failures.

PHASE 6 — FINAL REVIEW

Reviewer checks:
- correctness
- regressions
- architecture consistency
- unnecessary complexity
- whether the original behavior/contracts remain correct

Return:
- repository context used
- design decision
- files changed
- tests performed
- review result
- remaining risks
