---
description: Generate or update technical documentation from the actual implementation
agent: orchestrator
---

DOCUMENT: $ARGUMENTS

Documentation must be derived from the actual repository, not assumptions.

1. Use Explore when necessary to inspect source code, tests, APIs, configuration, examples, setup, and runtime behavior.
2. Delegate documentation creation or updates to Documenter.
3. Documentation may include README, setup guides, architecture docs, API docs, usage examples, deployment instructions, troubleshooting, developer onboarding, docstrings, and migration notes depending on the request.
4. Delegate accuracy review to Reviewer.
5. Correct documentation that contradicts the implementation.
6. Do not describe unsupported behavior as fact.

Return documents changed, what was documented, sources inspected, and any behavior that could not be verified.
