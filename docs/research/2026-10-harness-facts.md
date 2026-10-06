# Claude Code + OpenCode: verified harness facts (2026-10-06)

**Method:** I read the raw doc markdown from `code.claude.com/docs/en/<page>.md` and `opencode.ai/docs/<page>.md`, the OpenCode source at tag `v1.18.34` (github.com/anomalyco/opencode), and the local `--help` output. I changed no configuration and made no model requests.
**What's installed locally:**
- OpenCode `1.18.34` is at `~/.opencode/bin/opencode`. That's the latest release (2026-09-30).
- `claude` isn't on PATH. The only Claude Code binary is `2.1.286`, bundled with Zed's ACP adapter: `~/.local/share/zed/external_agents/registry/npx/claude-acp/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64/claude`. The docs mention versions up to v2.1.288, so a few documented items may be newer than this binary.

---

## CLAUDE CODE

### 1. Subagents (https://code.claude.com/docs/en/sub-agents)
- **Locations, highest priority first:** managed `.claude/agents/` > `--agents` JSON > `.claude/agents/` > `~/.claude/agents/` > plugin `agents/`. When two share a name, the higher one wins.
  - Project agents are found by walking up from the working directory to the repo root.
  - Directories are scanned recursively, but subfolders don't change the agent's name.
- **Frontmatter:** keys are camelCase and only `name` and `description` are required. Unknown keys are silently ignored, and a file without `name` is skipped.
  - `name` can't contain `:`.
  - `tools` takes a comma string or a YAML list; leaving it out inherits all tools. `disallowedTools` removes tools.
  - `model`, `permissionMode` (`default|acceptEdits|auto|dontAsk|bypassPermissions|plan`, with `manual` as an alias), `maxTurns`.
  - `skills` preloads the full skill content. `mcpServers` takes server names or inline `.mcp.json`-style entries. `hooks`.
  - `memory` (`user|project|local`), `background`, `omitClaudeMd`, `effort` (`low|medium|high|xhigh|max`), `isolation: worktree`.
  - `color` (`red|blue|green|yellow|purple|orange|pink|cyan`), `initialPrompt`, `experimental: {cacheTtl: 5m|1h}`.
- **`model`:** `sonnet`, `opus`, `haiku`, **`fable`** (it exists), a full ID such as `claude-opus-5-5`, or `inherit`.
  - Resolution order: the per-call `model` parameter, then frontmatter, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the main model.
  - A family alias that matches the main model's family resolves to the main model itself.
- **Plugin agents ignore** `hooks`, `mcpServers`, `permissionMode` and `initialPrompt`.
- **Nesting is supported.** By default subagents can go 3 layers below the main conversation.
  - Change the depth with `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; `1` turns nesting off.
  - To stop one agent from spawning others, leave `Agent` out of its `tools`.
  - The `tools: Agent(worker, researcher)` allowlist only works for an agent running as the main thread (`claude --agent <name>` or settings `"agent": "<name>"`). Inside a subagent the list in parentheses is ignored.
  - At most 20 subagents run at once (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`). `Task(...)` still works as an alias of `Agent`.
- **Agent teams** (https://code.claude.com/docs/en/agent-teams):
  - Experimental and off by default. Turn on with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
  - A lead session runs separate Claude Code instances as teammates, with a shared task list and a mailbox.
  - `teammateMode` is `in-process|auto|tmux|iterm2`.
  - Teams can't be nested. A teammate can be started from a subagent definition.
  - Once teams are on, a subagent Claude spawns from the main conversation with a `name` becomes a teammate (unless it's a fork or passes `isolation`).
- **Dynamic workflows** are a related feature: a JavaScript script that orchestrates many subagents (https://code.claude.com/docs/en/workflows).

### 2. Model aliases and env vars (https://code.claude.com/docs/en/model-config, /env-vars)
| Variable | Effect |
|---|---|
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | Model behind `opus` (and `opusplan` in plan mode) |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Model behind `sonnet` (and `opusplan` outside plan mode) |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | Model behind `haiku`, also used for "background functionality" |
| `ANTHROPIC_DEFAULT_FABLE_MODEL` | Model behind `fable` (default is Fable 5.1) |
| `ANTHROPIC_SMALL_FAST_MODEL` | **Deprecated**; use `ANTHROPIC_DEFAULT_HAIKU_MODEL` |
| `CLAUDE_CODE_SUBAGENT_MODEL` | Default model for subagents, teammates and workflow agents. Frontmatter and per-call values still win unless `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` |
| `ANTHROPIC_MODEL` | Model for the session |
| `ANTHROPIC_DEFAULT_MODEL` | Starting model when nothing else sets one |
| `ANTHROPIC_CUSTOM_MODEL_OPTION` (+`_NAME`, `_DESCRIPTION`) | Adds one entry to the picker; the ID isn't validated |

- Values must be "a full model name, or the equivalent identifier for your API provider".
- Other alias values: `default`, `best`, `opusplan`, `opus[1m]`, `sonnet[1m]`.
- On the Anthropic API today, `opus` resolves to Opus 5.5 and `sonnet` to Sonnet 5.5.
- **Main model priority:** `/model` (saved to user settings; press `s` for this session only) > `--model` > `ANTHROPIC_MODEL` > settings `"model"` > `ANTHROPIC_DEFAULT_MODEL`.

### 3. Non-Anthropic endpoint (https://code.claude.com/docs/en/llm-gateway, /llm-gateway-connect, /llm-gateway-protocol, /authentication)
- **Variables:** set `ANTHROPIC_BASE_URL` plus a credential.
  - `ANTHROPIC_AUTH_TOKEN` is sent as `Authorization: Bearer`.
  - `ANTHROPIC_API_KEY` is sent as `x-api-key`; interactive sessions ask you to approve it once.
  - `apiKeyHelper` sends both headers.
  - `ANTHROPIC_CUSTOM_HEADERS` adds extra headers.
  - Requests go to `$ANTHROPIC_BASE_URL/v1/messages`, so the base URL has **no `/v1`**.
- **What a gateway must do** (Anthropic Messages format):
  - Serve `POST /v1/messages?beta=true`. `/v1/messages/count_tokens` is optional; without it Claude Code estimates tokens from characters.
  - Forward `anthropic-beta` and `anthropic-version` unchanged.
  - Pass SSE through without buffering: the full event sequence up to `message_delta` and `message_stop`, plus `ping` events.
  - Beta tool fields (`strict`, `defer_loading`) must travel with their headers, or requests fail with 400.
  - Model discovery (`GET /v1/models` with `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`) only keeps IDs that contain `claude` or `anthropic`.
- **Unknown model IDs:** Claude Code still sends adaptive thinking, effort and context-management fields, and assumes a 200K context window.
  - Useful settings: `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`, `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, `DISABLE_INTERLEAVED_THINKING=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`.
  - The `*_SUPPORTED_CAPABILITIES` variables have no effect behind `ANTHROPIC_BASE_URL`.
- **Non-Claude models:** Anthropic "doesn't support routing Claude Code to non-Claude models through any gateway". It's unsupported, not blocked.
- **Subscription interaction:**
  - Credential order: cloud-provider variables > `ANTHROPIC_AUTH_TOKEN` > `ANTHROPIC_API_KEY` > `apiKeyHelper` > `CLAUDE_CODE_OAUTH_TOKEN` > profiles > `/login` subscription.
  - When a gateway credential is set, it's sent instead of your subscription login. The login stays saved but unused, and the subscription's limits don't apply.
  - `ANTHROPIC_BASE_URL` **alone does not** replace the subscription: the saved login is sent to the gateway, which must forward the OAuth `anthropic-beta` value.
  - A base URL other than api.anthropic.com also turns off Remote Control, and MCP tool search by default.
- **llama.cpp** (from its own README, not Anthropic's docs):
  - `llama-server` has `POST /v1/messages` (SSE; tools need `--jinja`) and `/v1/messages/count_tokens`.
  - It makes "no strong claims of compatibility".
  - Source: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md

### 4. Plugins (https://code.claude.com/docs/en/plugins/create, /plugins/manifest-reference, /plugins/components, /plugins/create-marketplace)
- **Layout:**
  - `.claude-plugin/plugin.json` is optional and must be the only file in that folder.
  - `skills/<name>/SKILL.md`, `commands/*.md` (older format), `agents/*.md`.
  - `hooks/hooks.json` holds `{"hooks":{...}}` in the same shape as settings.
  - `.mcp.json`, plus `.lsp.json`, `output-styles/`, `workflows/`, `themes/`, `monitors/monitors.json`, `bin/`, `settings.json`.
  - A `CLAUDE.md` at the plugin root isn't loaded.
  - Path variables: `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`.
- **Load for one session without installing:**
  - `claude --plugin-dir ./p` (repeatable; a directory, a `.zip`, or a folder of plugins).
  - `--plugin-url <zip>`, or the `CLAUDE_CODE_PLUGIN_DIRS` variable.
  - Run `/reload-plugins` after editing.
- **Load every session without a marketplace:** put the plugin at `~/.claude/skills/<n>/.claude-plugin/plugin.json` (`claude plugin init <n>` does this). It loads as `<n>@skills-dir`.
- **Local marketplace:**
  1. Create `<root>/.claude-plugin/marketplace.json` = `{"name","owner":{"name"},"plugins":[{"name":"x","source":"./plugins/x"}]}`.
  2. Run `claude plugin marketplace add ./root`.
  3. Run `claude plugin install x@<marketplace>`.
  - Check it with `claude plugin validate <dir>`.
- **Naming:**
  - Skills: `/plugin:skill`.
  - Commands: `/plugin:file`, so `commands/db/migrate.md` becomes `/plugin:db:migrate`.
  - Agents: `plugin:agent`; subfolders add segments, and you mention one with `@agent-plugin:agent`.
  - MCP tools: `mcp__plugin_<plugin>_<server>__<tool>`.

### 5. Skills vs slash commands (https://code.claude.com/docs/en/skills)
- "**Custom commands have been merged into skills**": `.claude/commands/deploy.md` and `.claude/skills/deploy/SKILL.md` both create `/deploy`.
  - A command in a subfolder, `commands/frontend/component.md`, becomes `/frontend:component`.
- **Skill locations:** `~/.claude/skills/`, `.claude/skills/`, managed, and plugin.
- **Frontmatter** (hyphenated keys):
  - `name`, `description`, `when_to_use`, `argument-hint`, `arguments`.
  - `disable-model-invocation`, `user-invocable`, `allowed-tools`, `disallowed-tools`.
  - `model` (applies to the current turn; accepts `inherit`), `effort`.
  - `context: fork` with `agent: <subagent type>` and `background`.
  - `hooks`, `paths`, `shell`, `metadata`, `license`, `compatibility`.
  - Command files accept the same keys except `name` and `paths`.
- **In the body:** `$ARGUMENTS`, `$N`, `$name`, `${CLAUDE_SKILL_DIR}`, and `` !`cmd` `` to inject command output.

### 6. Hooks (https://code.claude.com/docs/en/hooks)
- **Events:** SessionStart, Setup, UserPromptSubmit, UserPromptExpansion, PreToolUse, PermissionRequest, PermissionDenied, PostToolUse, PostToolUseFailure, PostToolBatch, Notification, MessageDisplay, SubagentStart, SubagentStop, TaskCreated, TaskCompleted, Stop, StopFailure, TeammateIdle, InstructionsLoaded, ConfigChange, CwdChanged, DirectoryAdded, FileChanged, WorktreeCreate, WorktreeRemove, PreCompact, PostCompact, PreModelSwitch, PostModelSwitch, Elicitation, ElicitationResult, SessionEnd.
- **Handler types:** `command`, `http`, `mcp_tool`, `prompt`, `agent` (`agent` is experimental).
- **Blocking Stop or SubagentStop:**
  - Exit with code 2 (stderr becomes the reason), or print `{"decision":"block","reason":"..."}`. The reason is given to Claude (or the subagent) as its next instruction.
  - For non-error feedback, print `{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":"..."}}`.
  - Input includes `stop_hook_active` and `last_assistant_message`; SubagentStop also gets `agent_type` and `agent_transcript_path`.
  - After 8 continuations in a row the stop goes through anyway (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`).
  - Exit code 1 does not block.
- **Prompt hooks:** `{"type":"prompt","prompt":"... $ARGUMENTS","model":"...","timeout":30}`.
  - The model replies `{"ok":false,"reason":"..."}`. On Stop and SubagentStop the reason is fed back, unless the reply includes `"impossible":true`.
- **Agent hooks:** `"type":"agent"`, up to 50 turns, 60s default timeout.
  - Both prompt and agent hooks default to the background-functionality model.
- **Where hooks live:** `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, managed settings, a plugin's `hooks/hooks.json`, skill frontmatter, and subagent frontmatter.
  - In subagent frontmatter, `Stop` becomes `SubagentStop`.
  - Hooks in a project agent's frontmatter only run after you trust the workspace.

### 7. MCP, settings, flags (https://code.claude.com/docs/en/mcp, /settings, /cli-reference, /output-styles)
- **Adding MCP servers:**
  - `claude mcp add --transport http <name> <url> [--header "K: V"]`
  - `claude mcp add --env K=V --transport stdio <name> -- <cmd> [args]`
  - Add `--scope local|project|user` to choose where it's saved.
- **Where MCP config is stored:**
  - Local and user scope go in `~/.claude.json`.
  - Project scope goes in `.mcp.json`: `{"mcpServers":{"x":{"type":"http","url":"..."}}}`. Stdio entries use `command`, `args`, `env`.
  - `${VAR}` and `${VAR:-default}` are expanded.
  - Precedence: local > project > user > plugin > claude.ai connectors.
  - Flags: `--mcp-config <files|json>`, `--strict-mcp-config`.
- **Settings precedence:** managed > command line (`--settings <file|json>` and flags) > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`.
  - Lists are merged across files.
  - `--setting-sources user,project,local` limits which files load.
- **System prompt flags:**
  - `--system-prompt[-file]` replaces the system prompt.
  - `--append-system-prompt[-file]` appends to it.
  - `--append-subagent-system-prompt` appends to every subagent (only with `-p`).
- **Output styles:** Markdown files in `~/.claude/output-styles/`, `.claude/output-styles/`, or a plugin's `output-styles/`.
  - Frontmatter: `name`, `description`, `keep-coding-instructions`, `force-for-plugin`.
  - Choose one with the `"outputStyle"` setting.
- **`--agents`:** `'{"name":{"description":"...","prompt":"...","tools":[...],"model":"sonnet"}}'`, or a file path when used with `-p`.
  - Accepts the frontmatter fields above except `color` and `experimental`.

### 8. Effort and thinking (https://code.claude.com/docs/en/model-config#adjust-effort-level)
- **Levels:** `low|medium|high|xhigh|max`, depending on the model.
  - Default is `medium` on Opus 5.5 and Sonnet 5.5, `high` on most other models, and `xhigh` on Opus 4.7.
- **Ways to set effort:**
  - `CLAUDE_CODE_EFFORT_LEVEL` beats `--effort`, `/effort`, settings and frontmatter (a `maxEffortLevel` cap still applies); it also accepts `auto`.
  - `--effort` and `/effort`.
  - Settings `effortLevel` (`low` to `xhigh`; `max` isn't accepted) or `modelSettings`.
  - `maxEffortLevel` sets a cap; `effort` in frontmatter sets it per skill or subagent.
- **`ultracode`** is a separate setting that turns on workflow orchestration: `--effort ultracode` or `"ultracode": true`.
- **`ultrathink`** anywhere in a prompt adds a one-turn instruction in context; the effort sent to the API doesn't change. Phrases like "think hard" aren't keywords.
- **`MAX_THINKING_TOKENS`** sets a fixed thinking budget.
  - Models with adaptive reasoning ignore the number, unless `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1` (Opus and Sonnet 4.6 only).
  - `0` turns thinking off, except on Opus 5.5, Sonnet 5.5 and Fable, where it can't be turned off.
- Alt+T toggles thinking (setting: `alwaysThinkingEnabled`). Subagents inherit thinking on/off; there's no per-subagent thinking setting.

---

## OPENCODE

### 9. Agents (https://opencode.ai/docs/agents, /config)
- **Markdown locations:** `~/.config/opencode/agents/` and `.opencode/agents/`, also `~/.opencode/` and `$OPENCODE_CONFIG_DIR`.
  - The source scans `{agent,agents}/**/*.md`. The singular name is kept for backward compatibility.
  - Subfolders are allowed; the name is the relative path without the extension, and frontmatter `name` overrides it.
- **JSON:** `"agent": {"<name>": {...}}` in `opencode.json`.
- Older `{mode,modes}/*.md` files load as primary agents.
- OpenCode does **not** read `.claude/agents/`.
- **Fields (from the schema):**
  - `description` (the docs call it required).
  - `mode`: `primary|subagent|all`, default `all`.
  - `model`: `provider/model-id`. A subagent without one uses the model of the primary agent that called it.
  - `variant`, `temperature`, `top_p`, `prompt` (supports `{file:...}`).
  - `steps` (`maxSteps` is deprecated).
  - `permission`, `tools` (deprecated map of booleans), `disable`, `hidden`.
  - `color`: `#RRGGBB` or `primary|secondary|accent|success|warning|error|info`.
  - `options`.
  - **Any other key is passed to the provider as a model option**, for example `reasoningEffort: high`.
- **Permission keys:** `read, edit, glob, grep, list, bash, task, external_directory, todowrite, webfetch, websearch, lsp, skill, question, doom_loop`.
  - Values are `allow|ask|deny`, or an object of patterns where the last match wins.
  - MCP tools match as `server_*`.
- **Can subagents call subagents?** Not by default. Two things are needed (source: `agent/subagent-permissions.ts`, `tool/task.ts`):
  1. Config `"subagent_depth": 2` or more. Default is 1; `0` disables subagents entirely.
  2. A `task` rule in the subagent's own `permission`. Without one its session gets `task: deny`.
  - `permission.task` patterns limit which agents may be called.
  - Background subagents need `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true`.

### 10. Commands (https://opencode.ai/docs/commands)
- **Locations:** `~/.config/opencode/commands/` and `.opencode/commands/` (the source scans `{command,commands}/**/*.md`), or `"command": {"x": {"template": "..."}}` in JSON.
- **Frontmatter:** `description`, `agent`, `model`, `subtask` (boolean), and `variant` (in the schema, not the docs).
  - If `agent` is a subagent, the command runs as a subtask by default; `subtask: false` turns that off.
- **In the body:** `$ARGUMENTS`, `$1`, `$2`…, `` !`cmd` ``, `@file`.

### 11. Custom OpenAI-compatible provider (https://opencode.ai/docs/providers#custom-provider, #llamacpp, /config#variables)
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "llamacpp": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "llama.cpp router",
      "options": { "baseURL": "http://host:8080/v1", "apiKey": "{env:LLAMA_API_KEY}" },
      "models": {
        "qwen3-coder": {
          "name": "Qwen3 Coder",
          "tool_call": true, "reasoning": false, "temperature": true,
          "limit": { "context": 131072, "output": 32768 }
        }
      }
    }
  },
  "model": "llamacpp/qwen3-coder"
}
```
- **`npm`:** use `@ai-sdk/openai-compatible` for `/chat/completions` and `@ai-sdk/openai` for `/responses`.
  - It can be overridden per model with `provider.npm`, and defaults to openai-compatible.
- **API key:** `{env:VAR}` or `{file:~/path}`, or `/connect` → Other, which stores it in `~/.local/share/opencode/auth.json`.
- **Other provider options:** `headers`, `timeout`, `headerTimeout`, `chunkTimeout`.
- **Model fields:**
  - `name`; `id`, which overrides the model ID sent to the API.
  - `limit{context,output,input?}`.
  - `tool_call` (**defaults to true**); `reasoning`, `temperature` and `attachment` (default false).
  - `interleaved`, `modalities`, `options`, `headers`, `variants`.
- **Gotcha:** OpenCode only sends an agent's `temperature` when the model has `temperature: true`.
- **With openai-compatible** (per the AI SDK source):
  - `reasoningEffort` becomes `reasoning_effort` in the request.
  - Other unknown option keys are copied into the request body as-is.

### 12. MCP, custom tools, plugins (https://opencode.ai/docs/mcp-servers, /custom-tools, /plugins)
- **MCP servers:**
  - Local: `{"type":"local","command":["npx","-y","pkg"],"environment":{},"enabled":true,"cwd":"...","timeout":5000}`.
  - Remote: `{"type":"remote","url":"...","headers":{},"oauth":{...}|false,"timeout":...}`.
  - Tool names are prefixed with `<server>_`. Turn them on per agent with `tools` or `permission` patterns.
- **Custom tools:**
  - Put `.ts`/`.js` files in `.opencode/tools/` or `~/.config/opencode/tools/` (the source scans `{tool,tools}`).
  - Write `export default tool({description, args:{q: tool.schema.string()}, async execute(args, ctx){...}})`, importing from `@opencode-ai/plugin`.
  - Named exports become `<file>_<export>`. A tool with a built-in's name replaces the built-in.
- **Plugins:**
  - Put them in `.opencode/plugins/` or `~/.config/opencode/plugins/` (`{plugin,plugins}/*.{ts,js}`), or list npm packages in `"plugin": [...]`.
  - Shape: `export const P: Plugin = async ({project, client, $, directory, worktree}) => ({...})`.
  - Hook keys:
    - `event`, `config`, `tool`, `auth`, `provider`
    - `chat.message`, `chat.params`, `chat.headers`
    - `permission.ask`, `command.execute.before`
    - `tool.execute.before`, `tool.execute.after`, `shell.env`, `tool.definition`
    - `experimental.chat.messages.transform`, `experimental.chat.system.transform`, `experimental.session.compacting`, `experimental.compaction.autocontinue`, `experimental.text.complete`, `experimental.provider.small_model`
  - Events delivered through `event` include `session.idle`, `session.status`, `session.error`, `message.updated`, `permission.asked` and `file.edited`.
  - To block a tool, throw inside `tool.execute.before`.
- **Stop-hook equivalent:** none exists. The closest workaround (my inference, not documented) is to react to `session.idle` and call `client.session.prompt({path, body})`.

### 13. Claude Pro/Max in OpenCode (https://opencode.ai/docs/providers#anthropic)
- OpenCode's docs say plugins exist for using Claude Pro/Max, but "Anthropic explicitly prohibits this". OpenCode stopped bundling them in 1.3.0.
- **So the Anthropic provider needs an API key:** `/connect` → Anthropic → enter the API key, or set `ANTHROPIC_API_KEY`.
- Anthropic's side: subscription OAuth is "designed to support ordinary use of Claude Code and other native Anthropic applications", and third parties may not route requests through Free/Pro/Max credentials (https://code.claude.com/docs/en/legal-and-compliance).

---

## Things that differ between the two harnesses
- **Model references:** Claude Code uses aliases or full IDs; OpenCode uses `provider/model-id`.
- **Base URL:** Claude Code takes `http://host:8080` and adds `/v1/messages` itself; OpenCode takes `http://host:8080/v1`.
- **Agent directories:** neither reads the other's agents folder.
- **Sharing one agent file:** if a Claude-style file reaches OpenCode (for example via `OPENCODE_CONFIG_DIR`), `tools: Read, Grep` (a string) or `color: red` fails OpenCode's schema and raises a config `InvalidError`.
  - Claude Code silently ignores OpenCode-only keys (`mode`, `permission`, `steps`, `temperature`).
  - Claude Code skips files that have no `name`.
- **Skills can be shared:** OpenCode also reads `.claude/skills/*/SKILL.md` and `~/.claude/skills/`.
  - It only recognizes `name`, `description`, `license`, `compatibility` and `metadata`.
  - `name` must match the folder name and `^[a-z0-9]+(-[a-z0-9]+)*$`.
- **Instruction files:**
  - Claude Code (v2.1.277+) reads `AGENTS.md` when there's no `CLAUDE.md`.
  - OpenCode reads `CLAUDE.md` when there's no `AGENTS.md`; turn this off with `OPENCODE_DISABLE_CLAUDE_CODE*`.
