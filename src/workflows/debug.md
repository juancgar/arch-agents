---
name: debug
description: Something fails (error, crash, wrong output, failing test, regression) and the root cause is unknown. Reproduce, diagnose with evidence, fix, verify — with a cap on fix attempts.
argument-hint: "<symptom, error message or failing test>"
---

# Debug

Don't guess a fix before there is evidence for a root cause.

1. **Diagnose:** {{agent:debugger}} reproduces the failure and establishes the root cause (facts · hypotheses tested · confirmed cause · recommended fix · regression test). Give it the symptom, logs and any spec.
   - Memory (optional): if the failure may relate to known environment constraints or recurring bugs, search memory for `bug_pattern`, `environment_constraint` or `repo_constraint` first, and pass the results as claims to verify.
2. **G2 Reproduce (M/L):** {{agent:tester}} writes a test that fails for the diagnosed reason — from the diagnosis and spec, not from a patch. For S, the debugger's reproduction command is enough.
3. **Fix:** {{agent:coder}} implements the recommended fix and runs the reproduction test + regression suite + lint/types (G3).
4. **Review (M/L, G4):** {{agent:reviewer}} with the spec, the diagnosis, the diff and the logs.

**G6 debug cap:** if the fix fails three times, or the diagnosis was wrong:
1. stop;
2. summarize what was tried and observed;
3. start a fresh diagnosis with {{agent:debugger}}, giving it the summary but not the failed patches' reasoning;
4. if that also fails, ask the user (or escalate to **architecture-change** when the evidence points to a design problem).

Answer with the root cause (with evidence), the fix, the checks that passed, and anything still uncertain.
