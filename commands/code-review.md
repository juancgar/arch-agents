---
description: Repository-aware code review using implementation, semantic context, history, tests, and GitHub context when relevant
agent: orchestrator
---

CODE REVIEW: $ARGUMENTS

Do not modify code.

First determine whether the review is LOCAL or DEEP.

LOCAL:
Small isolated change with obvious intent.

Use:
- source
- LSP
- tests

DEEP:
Multi-file change, architecture change, unfamiliar behavior, surprising legacy code, or unclear intent.

For DEEP review delegate to Explore first.

Explore may inspect:
- AGENTS.md
- surrounding implementation
- LSP definitions/references/types
- ast_grep patterns
- relevant tests
- git diff
- git log for affected files
- git blame only where intent is unclear
- relevant GitHub PR/issues when a GitHub remote exists

Then delegate review to Reviewer.

Review:
- correctness
- regressions
- edge cases
- error handling
- security
- maintainability
- unnecessary complexity
- duplicated logic
- API consistency
- state/type safety
- performance when relevant
- tests
- architecture consistency
- consistency with known repository intent

Distinguish:
CODE EVIDENCE
HISTORY/INTENT EVIDENCE
INFERENCE

Finish with:
APPROVE
APPROVE WITH MINOR ISSUES
or
CHANGES REQUIRED
