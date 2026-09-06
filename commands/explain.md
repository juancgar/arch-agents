---
description: Explain code using semantic context and repository history only when necessary
agent: orchestrator
---

EXPLAIN: $ARGUMENTS

Do not modify code.

Start FAST.

Use the supplied/selected code plus LSP to understand:
- definitions
- references
- types
- implementations
- surrounding control/data flow

Use Explore when additional repository context is necessary.

Use ast_grep when structural patterns help explain the implementation.

ONLY inspect Git history or GitHub when the question involves:
- why something was designed this way
- legacy code
- migrations
- compatibility behavior
- architecture decisions
- apparently unnecessary code
- behavior whose intent cannot be determined from source

If history is needed, inspect only relevant commits/files/PRs/issues.

Explanation levels:

L1 — What does this do?
L2 — How does data/control flow?
L3 — Why is it designed this way?
L4 — Deep algorithms/math/concurrency/protocols/architecture.
L5 — Teach it until the user could reimplement it.

Clearly distinguish:
VERIFIED CODE BEHAVIOR
REPOSITORY HISTORY
INFERENCE
