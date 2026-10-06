---
name: repo-map
description: Map or refresh the whole repository's structure into REPOSITORY_MAP.md — entry points, modules, interfaces, data flow, build/test commands — generated from the actual repository.
argument-hint: "[focus or questions the map should answer]"
---

# Repository map

Only for whole-repository understanding or when the map is missing/stale for major work — not for quick fixes, ordinary questions or small reviews.

1. {{agent:explore}} (in parallel on separate top-level areas for large repositories) collects:
   - entry points and the build/test/lint commands;
   - modules and their responsibilities, the main interfaces and data flow;
   - external services and configuration;
   - conventions;
   - recent major changes (from local Git).
   It works from `AGENTS.md`, the README/docs, the source, LSP/structural search and local Git; GitHub only when it adds something.
2. {{agent:documenter}} writes `REPOSITORY_MAP.md` (or updates the existing one, keeping user-written sections), with `path` references for every component.
3. Memory may supply historical context only; don't copy a memory into the map without verifying it in the repository.

Keep the map compact: it is cached context for future tasks, and every line of it is paid for in every task that reads it.
