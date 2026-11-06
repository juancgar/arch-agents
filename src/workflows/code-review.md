---
name: code-review
description: Judge existing code, a diff or a PR — correctness, regressions, edge cases, error handling, security, maintainability, test adequacy. Evidence-based findings and a verdict; no code changes unless the user asks to fix findings.
argument-hint: "<diff, branch, PR or files to review>"
---

# Code review

1. **Scope:** what to review (working-tree diff, a branch vs main, a PR, specific files) and against what intent. Use the PR/issue description or the user's statement as the spec; if there is none, say the review is against general correctness.
2. **Small review (S):** {{agent:reviewer}} directly on the diff.
3. **Deep review (M/L):** {{agent:explore}} gathers the surrounding context (callers, contracts, tests); Git history or GitHub PR/issue context when relevant; then {{agent:reviewer}}.
4. Optionally have {{agent:tester}} run the existing tests so the reviewer has real check results.

The reviewer grades a spec-derived checklist PASS/FAIL with evidence and reports findings by severity with `file:line`, ending with **APPROVE**, **APPROVE WITH MINOR ISSUES** or **CHANGES REQUIRED**.

Don't modify code. If the user asked to "review and fix", continue with: coder fixes the evidenced findings → tester → reviewer (max 2 rounds).
