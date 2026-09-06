---
description: Build or refresh a deep repository map using source, LSP, AST, Git history, and GitHub context
agent: orchestrator
---

BUILD DEEP REPOSITORY MAP

Do not modify production source code.

Delegate repository discovery to Explore.

Use AGENTS.md as initial guidance, but VERIFY important claims independently.

Inspect the repository in a bounded, evidence-driven way.

1. PROJECT IDENTITY
- README and important documentation
- manifests/package files
- repository purpose
- languages/frameworks
- important configuration

2. STRUCTURE
- major directories
- production modules
- entry points
- libraries/packages/services
- important interfaces
- shared infrastructure

3. SEMANTIC CODE INTELLIGENCE
Use LSP where useful for:
- workspace symbols
- definitions
- references
- implementations
- types
- call relationships

4. STRUCTURAL INTELLIGENCE
Use ast_grep where useful for:
- important classes/functions
- repeated architectural structures
- handlers/controllers/services/adapters
- structural patterns
- likely module boundaries

Do not dump every symbol.

5. DEPENDENCY FLOW
Identify:
- module dependencies
- important external dependencies
- data flow
- control flow
- service boundaries
- persistence/storage
- external integrations

6. TEST AND VERIFICATION ARCHITECTURE
Identify:
- unit/integration/e2e tests
- test locations
- test frameworks
- lint/typecheck/static-analysis commands
- build commands
- run/development commands
- CI when visible

7. LOCAL GIT CONTEXT
Inspect read-only:
- git status
- branches
- remote
- recent meaningful commits
- relevant history for central modules

Do not scan every historical commit.

8. GITHUB CONTEXT

If a GitHub remote exists and GitHub MCP is available, selectively inspect:
- repository description
- important recent PRs
- relevant open issues
- architecture/migration discussions
- recent major development

Do not crawl GitHub indiscriminately.

9. ARCHITECTURAL INTENT

Identify:
- important design decisions
- compatibility constraints
- migrations in progress
- intentionally unusual code
- technical debt
- known boundaries
- likely extension points

Separate verified evidence from inference.

10. OUTPUT

Delegate final writing to Documenter.

Create or update:

REPOSITORY_MAP.md

Use this structure:

# Repository Map

## 1. Project Purpose
## 2. Technology Stack
## 3. High-Level Architecture
## 4. Directory and Module Map
## 5. Entry Points
## 6. Major Components and Responsibilities
## 7. Important Interfaces and APIs
## 8. Dependency and Data Flow
## 9. Storage and External Integrations
## 10. Test and Verification Architecture
## 11. Build / Run / Development Commands
## 12. Coding and Architectural Conventions
## 13. Recent Relevant Git History
## 14. Relevant GitHub PRs and Issues
## 15. Known Constraints and Migrations
## 16. Technical Debt / Risks
## 17. Extension Points
## 18. Unknowns and Inferences
## 19. Evidence Sources
## 20. Last Refresh

Keep it useful rather than exhaustive.

Prefer concise maps and relationships over long file listings.

Do not invent architecture from filenames alone.
