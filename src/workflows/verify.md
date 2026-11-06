---
name: verify
description: Run tests, type checks and linters, or check whether something works — without modifying code. Reports exact results.
argument-hint: "<what to verify>"
---

# Verify

1. {{agent:tester}} (mode B) runs the relevant tests, type checks and linters, and checks browser-facing behaviour in the browser when relevant.
2. Report the commands run · passes/failures with the exact failing assertions/errors · anything that couldn't be run.

No coder unless the user explicitly asks to fix failures (then switch to **debug** or **quick-fix**). No planner, no architect, no broad exploration.
