---
description: Make the smallest correct code fix and verify it
agent: orchestrator
---

QUICK FIX: $ARGUMENTS

Goal: make the smallest correct change with minimal risk.

Workflow:
1. Use the provided or IDE-selected code as primary context.
2. If important repository context is missing, delegate only the necessary read-only investigation to Explore.
3. Do not perform unrelated refactoring.
4. Delegate the change to Coder.
5. Delegate focused verification to Tester.
6. If verification reveals a non-trivial failure, use Debugger, then Coder, then Tester again.
7. Local Worker may be used once only for a genuinely self-contained tool-less task.

Return: problem, change, files changed, verification, result, remaining concerns.
