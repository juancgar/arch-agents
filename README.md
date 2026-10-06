# arch-agents v2

A multi-agent system for software engineering and academic research. An orchestrator routes each request to a workflow, delegates to 18 specialist agents, and only reports results that pass **evidence gates**: tests for code, verified citations and claim checks for research.

Each session can run with a different brain:
- Claude Fable, Opus or Sonnet, through your Claude subscription in **Claude Code**;
- local open models through the llama.cpp router, free and offline, in **OpenCode** or Claude Code.

The design follows published evidence; see [docs/architecture-v2.md](docs/architecture-v2.md) and the [literature survey](docs/research/2026-10-literature-survey.md). In short:
- **Evidence-gated review instead of self-critique.** Models rarely fix their own reasoning without external feedback.
- **Effort per role instead of chain-of-thought prompting.** Reasoning models already think; extra "think step by step" text costs tokens and can hurt.
- **One writer, tests written before the fix, a reviewer with a fresh context.**
- **Claim-level grounding for research,** and novelty answered with a closest-prior-work table rather than a verdict.

## Plans

| Plan | Harness | Brain | Judgment | Work | Bounded tasks |
|---|---|---|---|---|---|
| `max` | Claude Code | Fable 5.1 | Opus 5.5 | Sonnet 5.5 | Haiku 4.5 |
| `daily` *(default)* | Claude Code | Opus 5.5 | Opus 5.5 | Sonnet 5.5 | Haiku 4.5 |
| `saver` | Claude Code | Sonnet 5.5 | Sonnet 5.5 (Opus for architect and reviewer) | Sonnet 5.5 | Haiku 4.5 |
| `local` *(experimental)* | Claude Code → llama.cpp | Qwen3.6-35B | Qwen3.6-35B | KAT-Coder / MiroThinker | Laguna-XS |
| `offline` | OpenCode → llama.cpp | Qwen3.6-35B | Qwen3.6-35B | KAT-Coder / MiroThinker | Laguna-XS |

- **Subscription:** Claude plans use your Claude subscription, which only covers Anthropic's own apps such as Claude Code.
- **Local models:** the `local` and `offline` plans need the local model server (`llm-server`, see below). The `local` plan works but isn't supported by Anthropic.

## Usage

```bash
aa                        # interactive session, default plan (daily), current directory
aa max ~/code/project   # a plan and a project directory
aa offline              # fully local, no internet needed
aa daily -p "explain how the cache layer works"   # one-shot, prints the answer
aa plans                # list plans
aa build                # rebuild after editing src/
```

**Talking to it:** just describe what you want. The orchestrator classifies the request into a route and a difficulty (S/M/L) and runs the matching workflow. Workflows can also be invoked directly:
- Claude Code: `/arch:implement …`, `/arch:debug …`, `/arch:research-cycle …`
- OpenCode: `/implement …`, `/debug …`, `/research-cycle …`

| Coding | Research |
|---|---|
| quick-fix · explain · debug · implement (`--hard` for sample-and-select) · refactor · architecture-change · code-review · verify · document · repo-map | research-discovery · paper-analyze · paper-compare · literature-review · novelty-check · research-proposal · research-cycle · full-cycle |

## How a task flows

1. **Intake:**
   - route × difficulty (S/M/L);
   - one batched clarifying question, asked only if the answer changes the plan; otherwise assumptions are written down;
   - a spec with checkable acceptance criteria (M/L).
2. **Workflow** with gates, for M/L tasks (S tasks take a fast path):
   - **G2:** the tester writes a failing reproduction test **from the spec, without seeing the fix**;
   - **G3:** the coder, the only writer, makes the change; then tests, lint and types must pass;
   - **G4:** a reviewer with a fresh context grades a spec checklist, and every finding must cite evidence;
   - **G5 (research):** citations are verified to exist, and each claim is checked against the passage it cites;
   - **G6:** after 3 failed fix attempts, stop, summarize, and restart fresh.
3. **Answer:** the result, what was verified (and what wasn't), confidence, open issues, and paths of saved files.

In Claude Code, **hooks** enforce part of this without relying on the model:
- `sudo`, recursive deletes, `git push` and writes outside the project or research folders are blocked;
- the coder, tester and debugger must report the commands they ran;
- research agents can't finish with citations that don't exist;
- the final answer can't claim a saved file that doesn't exist.

## Local models (`llm-server`)

A systemd user service runs the llama.cpp **router**. Requests name a model and it loads on demand, one at a time on the 8 GB GPU (MoE experts spill to RAM). A model unloads after 10 idle minutes.

| Endpoint | Models |
|---|---|
| `http://omen:8080` | qwen3.6-35b · kat-coder · laguna-xs · mirothinker · qwen3-30b · tongyi-research |
| `http://omen:8081` (CPU) | embed · rerank |

Config: `~/.config/llama-server/{chat-models.ini,embed-models.ini,api-key}`; models live in `~/Storage/AI-Workspace/models/gguf`.

## Shared tools: `mcp/arch-tools`

An MCP server used by both harnesses:

| Tool | What it does |
|---|---|
| `verify_citations` | checks arXiv IDs, DOIs and URLs exist and that titles match |
| `paper_search` | hybrid BM25 + embedding + reranker search over ResearchHub and the paper library |
| `local_llm` | free bulk text work on the local models |
| `memory_search` | read-only memory retrieval |

See [mcp/arch-tools/README.md](mcp/arch-tools/README.md). Rebuild the paper index with:

```bash
uv run --script mcp/arch-tools/server.py index
```

Other MCP servers (arXiv, OpenReview, Zotero, Playwright, GitHub) are configured in `config.local.yaml`.

## Repository layout

```
src/agents/*.md       the 19 agents: tier, effort, capabilities and prompt (single source of truth)
src/workflows/*.md    the 18 workflows (Claude skills / OpenCode commands)
src/shared/*.md       shared prompt blocks (evidence rules, report format, research locations)
src/plans.yaml        plans → models, capabilities → tools per harness
config.local.yaml     machine-specific paths and hosts (copy from config.example.yaml)
scripts/build.ts      generates build/claude/<plan>/ plugins, build/opencode/, build/plans.json
hooks/                Claude Code hook scripts (deterministic gates)
mcp/arch-tools/       shared MCP tool server
tools/ lib/           OpenCode custom tools + the Phase 2A memory library
evals/                routing / coding / research evaluation suites
bin/arch              launcher
```

Never edit `build/`; edit `src/` and run `aa build` (`npm run build`).

## Install on another machine

1. Install [Claude Code](https://code.claude.com) (`npm install -g @anthropic-ai/claude-code`, then `claude` to log in), [OpenCode](https://opencode.ai/docs/), Node.js and [uv](https://docs.astral.sh/uv/).
2. Clone and build:
   ```bash
   git clone https://github.com/juancgar/arch-agents.git && cd arch-agents
   npm ci
   cp config.example.yaml config.local.yaml   # edit paths and hosts
   npm run build
   ln -s "$PWD/bin/arch" ~/.local/bin/aa   # short alias; `arch` itself is a coreutils command
   ```
3. For the local plans, set up llama.cpp and the `llm-server` service (see above), and download the models.
4. To make v2 your global OpenCode config, point `~/.config/opencode` at `build/opencode`.

## Memory (Phase 2A shadow pilot)

The pilot continues **unchanged in OpenCode**: coding tasks propose zero or one candidate, and `memory-manager` records shadow decisions with `applied=false`. In Claude Code, memory is read-only (`memory_search`). See [docs/memory-shadow-pilot.md](docs/memory-shadow-pilot.md).

## Development

```bash
npm run check        # validate sources (frontmatter, references, templates)
npm run build        # generate plugins and configs
npm test             # Phase 2A memory-tool tests
npm run test:hooks   # hook tests
npm run typecheck
uv run --script evals/run.py --plan offline --suite routing     # free eval run (see evals/README.md)
```

The original example code and workflows are from the v1 architecture (git tag `v1`). License: none selected.
