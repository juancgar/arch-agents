# arch-agents

An OpenCode configuration for coordinated software engineering and academic research: 18 custom agents, 17 slash commands, and three custom tool modules.

The orchestrator routes requests to specialists, selects workflows according to intent, and separates implementation from verification. Agent permissions and routing instructions live in Markdown, so the architecture can be inspected and customized directly.

## Architecture

| Component | Responsibility |
| --- | --- |
| `agents/orchestrator.md` | Primary coordinator, workflow routing, model selection, and selective memory retrieval |
| `architect`, `planner` | Architecture decisions and implementation planning |
| `coder`, `debugger`, `tester`, `reviewer`, `documenter` | Implementation, diagnosis, verification, review, and documentation |
| `researcher`, `synthesizer`, `novelty-checker` | Literature discovery, synthesis, and adversarial evaluation of novelty |
| `paper-analyst`, `paper-comparator`, `literature-reviewer`, `proposal-designer` | Paper analysis, comparisons, literature reviews, and research proposals |
| `browser-agent` | Browser-based investigation |
| `local-worker` | Bounded generation using supplied context and a local Ollama model |
| `memory-manager` | Inspects coding-memory candidates and records shadow decisions |
| Built-in `explore` agent | Read-only repository exploration, with configuration overrides |

Coding workflows use selective memory retrieval and a Phase 2A shadow candidate pipeline. Automatic inserts and deletion are paused for all memory collections, including research. Research documents still save normally. Shadow recommendations always have `applied: false` and never enter memory retrieval. See [the shadow pilot guide](docs/memory-shadow-pilot.md).

## Install on another machine

This configuration was inspected with OpenCode **1.18.29** and pins `@opencode-ai/plugin` to **1.18.16**. Use OpenCode 1.18.29 or newer for GPT-6 Astra with ChatGPT/Codex authentication; older versions can filter Astra out of the model list. It also needs Node.js/npm for the locked dependencies and integrations that use `npx`.

1. Install [OpenCode](https://opencode.ai/docs/) and clone this repository:

   ```bash
   mkdir -p ~/workspace/me
   git clone https://github.com/juancgar/arch-agents.git ~/workspace/me/arch-agents
   cd ~/workspace/me/arch-agents
   npm ci
   cp -n opencode.example.json opencode.json
   chmod 600 opencode.json
   ```

2. Customize `opencode.json` and authenticate your model provider with OpenCode. Agents and commands previously using GPT-5.6 Sol now use `openai/gpt-6-astra`, retaining `-fast` for workloads configured for fast mode. Other model assignments are unchanged. Replace model IDs in agent and command frontmatter with IDs available to your account where necessary. The local worker expects the Ollama model `qwen2.5-coder:7b-16k`, which must be provisioned separately or replaced with a model you have installed.

3. Connect this checkout to OpenCode's global configuration location. If `~/.config/opencode` already exists, back it up and reconcile its settings first. The following command only creates the link when the destination is absent, including absent as a dangling symlink:

   ```bash
   mkdir -p ~/.config
   if [ ! -e ~/.config/opencode ] && [ ! -L ~/.config/opencode ]; then
     ln -s ~/workspace/me/arch-agents ~/.config/opencode
   else
     echo 'Existing OpenCode configuration found; back it up and reconcile it first.'
   fi
   ```

4. Configure the optional integrations below, then check discovery:

   ```bash
   opencode agent list
   ```

   Start OpenCode in the project you want to work on and select the `orchestrator` agent. The global symbolic link makes edits in this checkout available to OpenCode across projects; project configuration can still override global settings.

## Integrations and external dependencies

The example configuration keeps MCP servers disabled until configured. Enable only the integrations you have installed and authenticated. No external helper programs, provider credentials, research collections, or memory databases are included in this repository.

| Integration | Required setup |
| --- | --- |
| `tools/ast_grep.ts` | Install the `ast-grep` executable on `PATH`; the tool constrains searches to the current project |
| `tools/memory.ts` | Supply the Phase 2A memory CLI at `~/.local/bin/memory`, with its service and collections configured; the wrapper requires JSON `propose`, `inspect`, and `decide` operations in addition to Phase 1 search/stats |
| `tools/local_paper.ts` | Supply `~/AI-Workspace/system/research-tools/pdf_reader.py` and its `.venv/bin/python`, or adjust the wrapper's paths to your installation |
| Playwright MCP | Node.js/npm, `@playwright/mcp`, and the browsers required by that server |
| GitHub MCP | Set `GITHUB_TOKEN` in the environment that launches OpenCode; the example references it as `{env:GITHUB_TOKEN}` and requests read-only toolsets |
| arXiv MCP | Install `arxiv-mcp-server` on `PATH` and replace the example storage directory |
| OpenReview MCP | Install `openreview-mcp` on `PATH` and configure its prerequisites |
| Zotero MCP | Install `zotero-mcp` on `PATH` and configure the local Zotero service |
| Ollama | A local server at `http://localhost:11434/v1` and the selected local model |

The custom tools execute inside OpenCode's Bun runtime. MCP services and local helper programs remain separate dependencies. Workflows that call missing tools require those dependencies or corresponding changes to agent permissions and routing.

## Commands

Use these slash commands inside OpenCode with your task as the argument:

| Workflow | Commands |
| --- | --- |
| Software engineering | `/quick-fix`, `/implement`, `/debug`, `/refactor`, `/architecture-change`, `/code-review`, `/explain`, `/document`, `/repo-map` |
| Research | `/research-discovery`, `/paper-analyze`, `/paper-compare`, `/literature-review`, `/novelty-check`, `/research-proposal`, `/research-cycle` |
| Combined research and implementation | `/full-cycle` |

For example: `/repo-map describe this project's entry points and main interfaces`.

## Local configuration and version control

`opencode.example.json` is the shareable template. The active `opencode.json` and `opencode.jsonc`, secrets, dependencies, runtime state, and backups are ignored by Git. Copy intentional shareable configuration changes into the example after removing credentials and machine-specific values.

The example uses the current agent and workflow definitions, including the GPT-6 Astra model assignments and shadow-memory permissions. It uses environment credential references and placeholder paths and disables unconfigured MCP integrations. Configuration discovery does not demonstrate successful model requests. Memory-specific validation and pilot review are described in the guide and checks below.

See the [OpenCode configuration documentation](https://opencode.ai/docs/config/) for global settings, environment references, and configuration precedence. No license has been selected for this repository.

## Development checks

```bash
npm ci
npm run typecheck
npm test
```

The memory-tool tests use an injected subprocess runner and isolated temporary directories. They cover role enforcement, write guards, argument compatibility, repository provenance, JSON transport, timeouts, and cancellation. `tsx` provides the test loader even on Node builds without native TypeScript support. The separately installed Python memory service has its own unit and adapter tests.
