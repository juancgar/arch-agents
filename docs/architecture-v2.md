# arch-agents v2: architecture

Status: **design for review**, October 2026. Branch `v2-redesign` (worktree `~/workspace/me/arch-agents-v2`).
Evidence references `[S#]` point to [`research/2026-10-literature-survey.md`](research/2026-10-literature-survey.md); harness facts come from [`research/2026-10-harness-facts.md`](research/2026-10-harness-facts.md).

## 1. Goals

1. **More accurate results.** Use only techniques with published evidence, and drop techniques whose benefit disappeared with reasoning models.
2. **Choose the brain per session.** Fable, Opus or Sonnet through the Claude subscription, or local models with no cost and no internet.
3. **Spend tokens where they buy accuracy.** Use cheap tiers for bounded work and strong tiers for judgment.
4. **One source of truth for both harnesses.** Claude Code is used for Claude plans; OpenCode is used for the offline plan.
5. **Keep what works in v1.** That includes the 12 routes, *Architect decides whether / Planner decides how*, read-only intent safety, evidence rules for papers, and the Phase 2A shadow-memory pilot.

## 2. What the evidence says, and what we do about it

| # | Finding | v2 mechanism | Evidence |
|---|---|---|---|
| 1 | A model critiquing its own work without new information rarely fixes reasoning. Checks against **external** signals do help: tests, execution, retrieved sources. | **Evidence-gated review.** Every review must cite external evidence. No "re-read your answer" loops. | S36–S45 |
| 2 | With reasoning models, "think step by step", reasoning demos and personas add cost and sometimes hurt. Depth is controlled with **effort**, and more thinking is not monotonically better. | Remove CoT, persona and scaffold text from prompts. Set **effort per role**, escalated by failure signals. Local Qwen3.6 uses a think / no-think preset. | S8–S31 |
| 3 | Multi-agent helps for **read-heavy breadth** and **clean-context review**. It hurts for parallel writing and for debate. Strong orchestrators with much weaker workers underperform. | **Single writer** for code. Fan-out only for retrieval and research breadth. A clean-context reviewer. Workers at most one tier below the orchestrator. No debate. | S62–S80 |
| 4 | Tests are the best verifier for code. Reproduction tests written **without seeing the patch** catch more bugs. Debugging decays after 2–3 attempts, and a fresh restart helps. "Tests pass" is not the same as "mergeable". | Coding gates: **spec → blind reproduction test → patch → regression/lint/types → clean review**. At most 3 debug rounds, then a fresh restart with a failure summary. | S88–S99 |
| 5 | Citations from LLMs and deep-research agents are often wrong or post-hoc. Checking **atomic claims** against sources works and is cheap. | **Claim grounding**: deterministic citation checks (ID, DOI, URL, title), a cheap claim-checker that compares each claim with its cited span, and an explicit *insufficient evidence* outcome. | S103–S114 |
| 6 | LLM novelty judgments and review scores have low precision. Facet-based retrieval helps. | The novelty-checker outputs a **closest-prior-work table** per facet. A bare "novel" verdict is never allowed. Reviewer opinions are inputs, never scores. | S115–S126 |
| 7 | Underspecified tasks fail. Models assume early and rarely ask. Clarifying is useful only **early** in the task. | **Intake gate**: check inputs, acceptance criteria and constraints. Ask one batched question only when the answer changes the plan; otherwise record assumptions. | S100, S165, S166 |
| 8 | Long or irrelevant context degrades accuracy. Lean prompts and masking old observations help. | **Lean orchestrator** (about 300 lines instead of 1,731). Workflows load on demand as skills. Handoffs are structured and short. Long tasks keep notes files. | S129–S135, S81 |
| 9 | Stored memory errors propagate. Plain retrieval beats heavy memory frameworks. | Keep the **Phase 2A verified-only shadow pilot** unchanged. Use hybrid BM25 + embedding + reranker retrieval over papers. | S136–S149 |
| 10 | Judges are biased by position, length and self-preference, and are near chance on hard pairs. Checklists help. | Reviews use a **pass/fail checklist derived from the spec**. Pairwise comparisons are judged in **both orders**. Each finding must cite file:line, a log or a source. | S53–S59 |
| 11 | Sampling plus selection helps **only when a verifier exists**. Aggregating samples from the best model beats mixing in weaker ones. | **Sample-and-select** (k=3) is opt-in for hard coding tasks, where tests select. It is not used where nothing can verify the result. | S34, S64–S71, S92 |
| 12 | You can't improve what you don't measure. | An **eval suite**: routing cases, small coding tasks with hidden tests, and research questions with citation checks. Full traces are logged. | S79, S101 |

**Dropped or deprioritized:** tree/graph-of-thought controllers, multi-agent debate, mixture-of-agents with weaker models, process reward models, persona prompts, long self-reflection loops, heavyweight memory frameworks, and treating LLM novelty or review scores as decisions.

## 3. System overview

```
             ┌──────────────────────── aa <plan> ────────────────────────┐
             │ max / daily / saver  → Claude Code (subscription)           │
             │ local                → Claude Code → llama.cpp (experimental)│
             │ offline              → OpenCode    → llama.cpp router        │
             └──────────────────────────────┬──────────────────────────────┘
                                            ▼
   ┌───────────────────────── ORCHESTRATOR (brain) ─────────────────────────┐
   │ 1. Intake: route (12 routes) × difficulty (S/M/L); clarification gate  │
   │ 2. Spec: goal · acceptance criteria · constraints · assumptions        │
   │ 3. Run workflow skill (stages + gates + budgets)                       │
   │ 4. Integrate verified results → answer with evidence + confidence      │
   └───────┬───────────────┬──────────────────┬────────────────┬────────────┘
           ▼               ▼                  ▼                ▼
     judgment (heavy)  work (mid)        bounded (light)   verification
     architect         coder (writer)    explore           tester (blind)
     planner           debugger          documenter        reviewer (clean ctx)
     reviewer          researcher ×N     browser-agent     claim-checker
     synthesizer       paper-analyst     memory-manager    + deterministic checks
     novelty-checker                     claim-checker       (tests, citations,
     proposal-designer                                        lint/types)
     paper-comparator / literature-reviewer
           │
           ▼ shared tools (MCP "arch-tools" + existing MCP servers)
     verify_citations · paper_search (BM25+embed+rerank) · local_llm · memory_search
     arXiv · OpenReview · Zotero · GitHub (read-only) · Playwright · ast-grep
```

## 4. Plans: which model plays which role

Agents declare a **tier**. A plan maps tiers to models. The build generates one Claude Code plugin per plan and one OpenCode config.

| Tier | max | daily (default) | saver | local / offline |
|---|---|---|---|---|
| **brain** (orchestrator) | Fable 5.1 | Opus 5.5 | Sonnet 5.5 | Qwen3.6-35B (think) |
| **heavy** (judgment) | Opus 5.5 | Opus 5.5 | Sonnet 5.5 (Opus for architect and reviewer) | Qwen3.6-35B (think) |
| **mid** (work) | Sonnet 5.5 | Sonnet 5.5 | Sonnet 5.5 | coding: KAT-Coder · research: MiroThinker |
| **light** (bounded) | Haiku 4.5 | Haiku 4.5 | Haiku 4.5 | Laguna-XS (no think) |
| bulk text offload | `local_llm` tool | `local_llm` tool | `local_llm` tool (encouraged) | native |

Notes:
- Fable is used **only as the brain**: it costs 2.5× Opus per token. Workers stay at most one tier below the brain, because much weaker workers hurt accuracy (S72).
- Claude plans run in **Claude Code**, because the subscription only covers Anthropic's apps. The **offline** plan runs in **OpenCode**, with its native per-agent models.
- The **local** plan is Claude Code pointed at the llama.cpp router. It works technically, but Anthropic doesn't support it, so it's marked *experimental*.
- In the local plans, the reviewer uses a **different model** from the coder (Qwen3.6 vs KAT-Coder), which reduces self-preference bias (S57).

## 5. Agents

All prompts are rewritten. They are lean, with no CoT boilerplate. Each has a fixed **report schema** and states what evidence it must produce. Effort is set per role (Claude Code `effort`; for local models, the think or no-think model).

| Agent | Tier | Effort | Writes? | Must return as evidence |
|---|---|---|---|---|
| orchestrator | brain | plan default | no | spec, route, gate results, final answer with confidence |
| architect | heavy | high | no | options table, trade-offs, decision and reversibility |
| planner | heavy | medium | plan files | task graph with **acceptance tests per step** |
| reviewer | heavy | high | no | spec-checklist PASS/FAIL, findings with file:line + evidence |
| synthesizer | heavy | high | no | claims tagged EXPLICIT/SYNTHESIS/SPECULATION, each with citation |
| novelty-checker | heavy | high | no | per-facet closest-prior-work table, retain/narrow/abandon |
| proposal-designer | heavy | high | proposal | hypotheses, falsifiable experiments, risks |
| paper-comparator | heavy | medium | no | comparison grid with cited spans, both-order judgments |
| literature-reviewer | heavy | medium | review doc | thematic review, every claim cited |
| coder | mid | medium | **yes (only writer)** | diff summary, commands run + results |
| debugger | mid | high | no | facts / hypotheses / confirmed root cause + reproduction |
| tester | mid | medium | tests only | **blind** reproduction tests from the spec, run logs |
| researcher | mid | medium | no | sources with IDs + passage spans, coverage of planned questions |
| paper-analyst | mid | medium | notes | EXPLICIT vs INFERENCE, quantitative results with locations |
| claim-checker *(new)* | light | low | no | per-claim SUPPORTED / UNSUPPORTED / UNVERIFIABLE |
| explore | light | low | no | file:line pointers, ≤1–2K-token summary |
| documenter | light | low | docs | file paths written (verified) |
| browser-agent | light | low | no | URLs visited + extracted facts |
| memory-manager | light | low | shadow decisions | unchanged Phase 2A contract |

`local-worker` is retired in Claude plans and replaced by the `local_llm` tool, which any agent can use for free bulk text work. In the offline plan, the light tier *is* the local worker.

## 6. Workflows and gates

**Intake (always, and cheap):** classify the route (the 12 v1 routes are kept) × difficulty:
- **S:** single file or answer, low risk. Minimal workflow, no extra review.
- **M:** multi-file, or ambiguous. Standard workflow: tests and review gate.
- **L:** architectural, high-stakes, or novelty. Spec review, high effort, optional sample-and-select.

Ask one batched clarifying question **only** if the answer would change the plan; otherwise write assumptions into the spec. Read-only requests ("analyze only", "don't change") stay hard constraints.

**Gates** are the checkpoints a workflow must pass before moving on:

| Gate | What must be true | Applied in |
|---|---|---|
| G1 Spec | goal, acceptance criteria, constraints, assumptions written down | M, L |
| G2 Reproduce | a test that fails for the right reason, written by the tester **from the spec, without the patch** | debug, implement (M/L) |
| G3 Checks | reproduction test + full regression + lint/types pass; logs attached | every code change |
| G4 Review | clean-context reviewer, spec checklist, evidence-cited findings; CHANGES REQUIRED → coder, max 2 rounds | M, L code; plans for L |
| G5 Grounding | citation check passes; unsupported claims removed or flagged | every research output |
| G6 Debug cap | ≤3 debug rounds, then a fresh restart with a failure summary, then escalate tier or ask the user | debug |

Coding example (IMPLEMENT, M): intake → G1 spec → explore (light) → planner → tester writes blind tests (G2) → coder → checks (G3) → reviewer (G4) → done, or one revision round.

Research example (RESEARCH CYCLE): intake → researcher plans perspectives/questions (STORM-style, S102) → parallel retrieval (library first, then arXiv/OpenReview/web) → rerank → synthesizer with cited spans → novelty-checker per facet → claim-checker + verify_citations (G5) → documenter saves → answer with confidence and gaps.

## 7. Verification layer

- **Deterministic first:** tests, linters, type checkers, `verify_citations` (arXiv ID/DOI exists and title matches; URL is live), and file-exists checks for "saved to …" claims. These are cheap, and an LLM can't fool them.
- **Claim-checker** (light tier): splits an answer into atomic claims and compares each with the cited source span. Output: SUPPORTED / UNSUPPORTED / UNVERIFIABLE. One call per ~10 claims.
- **Reviewer protocol:** starts from a fresh context with the spec, the diff and the logs; it never sees the coder's reasoning (S35). It returns a pass/fail checklist plus findings, each citing evidence; findings without evidence are dropped. Comparisons are judged in both orders and only consistent verdicts are kept.
- **Claude Code hooks** add guards the model can't skip:
  - `SubagentStop` for coder, tester and debugger: the report must contain the required evidence sections (for example, the commands run and their results). Otherwise the subagent continues with a reason.
  - `SubagentStop` for researcher, synthesizer and literature-reviewer: a deterministic citation scan; hallucinated IDs block completion.
  - `PreToolUse`: blocks `sudo`, `rm -rf`, `git push`, and writes outside the project.
  - Hooks never call a strong model; a hook that is cheap and deterministic is a gate that actually gets run.
- **OpenCode** has no stop hooks, so the same gates exist as explicit workflow stages. They are harness-neutral by design.

## 8. Reasoning and compute policy

- Reasoning is native (Claude adaptive thinking; Qwen3.6 think mode). Prompts state **goal, constraints, acceptance criteria and output schema** only.
- Effort per role (table in §5). Escalation is triggered by **external failure signals**: tests fail, claim check fails, or samples disagree. Being "unsure" is not a trigger.
- Visible reasoning artifacts are **decisions, not monologues**: spec, assumptions, plan with acceptance tests, evidence log. They are kept in `.arch/tasks/<id>/` for M/L tasks, so long tasks survive context limits (S150).
- **Sample-and-select** is opt-in (`--hard` or after G6 fails once). It runs k=3 coder attempts in isolated git worktrees, selects by the tests, and breaks ties by a both-order review. In the offline plan these attempts are free.

## 9. Context and memory

- **Orchestrator ≤ ~300 lines:** a routing table, the gates and the handoff rules. Workflow details live in skills that load only when used.
- **Handoff schema** (every subagent): `Result` · `Evidence` · `Changes` · `Open issues` · `Confidence (high/medium/low + why)`, in ≤1–2K tokens.
- **Memory:** the Phase 2A shadow pilot continues **unchanged in OpenCode**. Claude Code gets **read-only** `memory_search` first; porting the proposal pipeline is a later, separate step.
- **Paper retrieval:** BM25 + Qwen3-Embedding over contextual chunks of ResearchHub and local PDFs, then the Qwen3-Reranker on the top ~50, keeping the best 5–10 chunks. Spans are kept for citation.

## 10. Repository layout and build

```
arch-agents/
  src/
    agents/*.md          one file per agent: neutral frontmatter (tier, effort, capabilities) + prompt
    workflows/*.md       workflows (become Claude skills + OpenCode commands)
    plans.yaml           tier → model per plan; capability → tool names per harness
  mcp/arch-tools/        MCP server: verify_citations, paper_search, local_llm, memory_search
  hooks/                 deterministic hook scripts (Claude Code)
  tools/ lib/ tests/     existing OpenCode tools + Phase 2A memory library (unchanged)
  evals/                 routing / coding / research cases + runner
  scripts/build.ts       generates build/claude/<plan>/ (plugins) and build/opencode/
  bin/arch               launcher: aa <plan> [dir]
  docs/                  this document, research reports, memory pilot guide
```

- Claude Code loads the plan's plugin per session with `--plugin-dir`, so no global install is needed and `~/.claude` is untouched.
- OpenCode: `~/.config/opencode` will point at `build/opencode/` when you switch to v2. That's a one-command switch, reversible.

## 11. Evaluation

- **Routing evals (cheap):** ~40 requests mapped to the expected route, difficulty, and forbidden agents.
- **Coding evals:** ~10 small tasks in fixture repos with hidden tests, scored by pass rate, cost and time.
- **Research evals:** ~8 questions scored by citation validity rate, unsupported-claim rate and coverage.
- **Usage:** run on the offline plan for free at any time; Claude plans only when you choose (they spend subscription usage). Compare v1-style vs v2 prompts on the same cases before declaring victory.

## 12. Rollout

1. **Core:** source format, build script, rewritten agents and workflows, plans, launcher, hooks, OpenCode offline config, smoke tests.
2. **Tools:** `arch-tools` MCP server (citations, paper search, local_llm, memory_search) wired into the gates.
3. **Evals:** suite plus first baseline (offline plan).
4. **Optional:** sample-and-select; port the Phase 2A proposals to Claude Code.

## 13. Open decisions (for you)

1. **Claude Code CLI.** Claude Code is only bundled inside Zed today. Install the standalone CLI for the `arch` launcher, or use Zed's copy?
2. **Review strictness.** Gates on M/L tasks only (recommended), or on every task?
3. **Where v2 lives when done.** Replace v1 in the same repo (after review), or keep both?
