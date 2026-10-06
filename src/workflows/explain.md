---
name: explain
description: Explain what code does and how it works (behaviour, data/control flow, design reasoning, algorithms). Read-only — never modifies files.
argument-hint: "<code, file or concept to explain> [depth L1-L5]"
---

# Explain code

Read-only: no coder, tester, planner or architect unless the user later asks for changes.

1. Read the referenced code directly when it is small; use {{agent:explore}} when the explanation needs surrounding repository context (callers, data flow across files).
2. Use Git history only when the user asks **why** something exists or the design intent can't be read from the source.
3. Match the depth to the request:
   - L1 behaviour;
   - L2 data/control flow;
   - L3 design reasoning and interaction with the rest of the repository;
   - L4 algorithms, math, concurrency, protocols;
   - L5 teach until reimplementation is realistic.

Point to the exact `file:line` locations you explain. Say where your explanation is inference rather than something the code shows directly.
