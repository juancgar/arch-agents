---
name: quick-fix
description: Small, localized code change with an obvious cause (typo, simple condition, null check, small validation, small rename). Fast path with the cheapest meaningful check.
argument-hint: "<the small change to make>"
---

# Quick fix

1. If the needed context isn't already in the request, use {{agent:explore}} to locate the code (skip when the user pointed at it).
2. Brief {{agent:coder}}: the change, the file(s), and the check to run afterwards (the nearest existing test, or a one-line check). No unrelated changes.
3. Difficulty M (touches shared code or behaviour others rely on): have {{agent:tester}} run the module's tests after the change.

Escalate instead of pushing on:
- the cause turns out to be unclear → **debug**;
- substantial new behaviour is needed → **implement**;
- structural redesign is needed → **refactor**.

Answer with the change, the check that ran and its result.
