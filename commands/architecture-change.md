---
description: Deep repository-aware architecture and environment design before implementation
agent: orchestrator
---

ARCHITECTURE CHANGE: $ARGUMENTS

DO NOT IMPLEMENT THE CHANGE.

PHASE 1 — CURRENT SYSTEM INTELLIGENCE

Delegate to Explore.

Explore should inspect:

- AGENTS.md
- README/docs
- project structure
- dependencies and manifests
- configuration
- important entry points
- LSP symbol/dependency relationships
- ast_grep structural architecture patterns
- test architecture
- git status
- git remote
- recent commits
- relevant module/file history

If the project has a GitHub remote and GitHub MCP is available, selectively inspect:
- repository description
- relevant PRs
- relevant issues
- historical decisions visible in those discussions

Do not scan GitHub indiscriminately.

Produce a concise CURRENT SYSTEM CONTEXT containing:

SYSTEM PURPOSE
COMPONENTS
BOUNDARIES
DEPENDENCIES
DATA/CONTROL FLOW
VERIFICATION SYSTEM
RECENT RELEVANT HISTORY
KNOWN DESIGN INTENT
GITHUB CONTEXT
CONSTRAINTS
UNKNOWNS

PHASE 2 — ARCHITECTURE THINKING

Delegate the requested change plus CURRENT SYSTEM CONTEXT to Architect.

Architect must produce:

1. Problem and goals
2. Current architecture
3. Constraints and assumptions
4. Target architecture
5. Components and responsibilities
6. Data/control flow
7. Integration points
8. Viable alternatives
9. Tradeoffs
10. Chosen approach and rationale
11. Security implications
12. Reliability/failure modes
13. Performance implications
14. Migration phases
15. Compatibility concerns
16. Rollback/recovery
17. Testing strategy
18. Deployment/rollout
19. Observability
20. ADR-worthy decisions
21. Open questions

Architecture must solve demonstrated problems.
Do not introduce unnecessary patterns, services, frameworks, or infrastructure.

PHASE 3 — INDEPENDENT REVIEW

Delegate the architecture proposal to Reviewer.

Reviewer should challenge:
- unnecessary complexity
- incorrect assumptions
- migration risk
- security
- failure modes
- testability
- compatibility
- operational burden

Return the reviewed architecture proposal.

Do NOT run Coder.

After approval, implementation should happen separately through /implement.
