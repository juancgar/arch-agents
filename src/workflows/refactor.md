---
name: refactor
description: Restructure code while preserving behaviour — reduce coupling, remove duplication, move responsibilities, change abstractions, reorganize modules. Behaviour is pinned by tests before anything moves.
argument-hint: "<what to restructure and why>"
---

# Refactor

1. **G1 Spec:** the demonstrated problem (why refactor), the target structure, and the behaviours and contracts that must not change.
2. **Context:** `AGENTS.md`/`REPOSITORY_MAP.md`, {{agent:explore}}, structural search; Git history when the original intent matters. Memory (optional): `architecture_decision`, `interface_contract`, `repo_constraint`.
3. **Plan:** {{agent:planner}} must:
   - name the demonstrated problems;
   - compare alternatives and justify any pattern (no pattern for its own sake);
   - define safe phases that keep the system working, and the contract checks for each;
   - L: {{agent:reviewer}} reviews the plan first.
4. **G2 Characterization tests:** {{agent:tester}} pins current behaviour with tests that pass **before** the refactor.
5. **Refactor:** {{agent:coder}} works phase by phase; after each phase the characterization tests and regression suite must still pass (G3).
6. **G4 Review:** {{agent:reviewer}} confirms the problem was solved and behaviour preserved.

The architect is not needed for a normal refactor. Use **architecture-change** only if the refactor crosses major system boundaries or needs a new architectural model.

Answer with the before/after structure, evidence that behaviour is preserved, and the review verdict.
