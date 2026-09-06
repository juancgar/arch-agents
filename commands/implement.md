---
description: Large repository-aware feature implementation with history, planning, phased coding, testing, and review
agent: orchestrator
---

IMPLEMENT: $ARGUMENTS

Do not immediately start coding.

PHASE 1 — DEEP REPOSITORY CONTEXT

Search project memory when previous architecture decisions or constraints may matter.

Delegate repository investigation to Explore.

Explore should inspect:

- AGENTS.md
- README and relevant documentation
- project/module structure
- relevant manifests/configuration
- existing similar implementations
- tests
- LSP definitions/references/types
- ast_grep structural patterns
- git status
- git remote
- recent git history
- relevant file/module history

If a GitHub remote exists and GitHub MCP is available, inspect only relevant:
- repository metadata
- pull requests
- issues
- prior changes connected to this feature

Look specifically for evidence that:
- the feature already exists partially
- another implementation is in progress
- current strange behavior is intentional
- compatibility/migration constraints exist

Summarize:

CURRENT SYSTEM
REUSABLE COMPONENTS
RELEVANT HISTORY
GITHUB CONTEXT
CONSTRAINTS
UNKNOWN QUESTIONS

PHASE 2 — PLAN

Delegate to Planner.

Define:
- intended behavior
- affected modules
- interfaces
- dependencies
- data/config changes
- implementation phases
- tests
- compatibility concerns
- failure risks
- DONE criteria

PHASE 3 — REVIEW PLAN

Reviewer independently checks the plan.

PHASE 4 — IMPLEMENT

Coder implements one verifiable phase at a time.

PHASE 5 — VERIFY

Tester verifies each meaningful phase.
Debugger investigates non-trivial failures.

PHASE 6 — FINAL REVIEW

Reviewer checks the integrated implementation.

Use Documenter when developer-facing or user-facing behavior changed.

Return:
- context discovered
- implementation summary
- files changed
- tests
- review result
- documentation impact
- unresolved risks
