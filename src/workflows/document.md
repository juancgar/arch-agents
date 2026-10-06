---
name: document
description: Write or update persistent technical documentation (README, API docs, setup and deployment guides, architecture notes, docstrings) that must match the actual implementation.
argument-hint: "<what to document>"
---

# Document

Documentation must describe **verified** behaviour — never invent features.

1. {{agent:explore}} gathers the facts from the actual code, configuration and tests (with `file:line`).
2. {{agent:documenter}} writes or updates the docs from those facts, preserving user-written content unless asked to change it, and confirms the files written.
3. M/L (public docs, setup or deployment instructions, architecture docs): {{agent:reviewer}} checks the docs against the code — every command and claim must match the repository.

If the user just wants something explained in chat, use **explain** instead.
