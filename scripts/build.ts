// arch-agents v2 build: src/ (single source of truth) → build/claude/<plan>/ (Claude Code plugins)
// and build/opencode/ (OpenCode config dir). Run: npm run build   (or: npx tsx scripts/build.ts [--check])
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync, chmodSync } from "node:fs"
import { homedir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import YAML from "yaml"

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const SRC = path.join(ROOT, "src")
const BUILD = path.join(ROOT, "build")
const PLUGIN_NAME = "arch"
const VERSION = JSON.parse(readFileSync(path.join(ROOT, "package.json"), "utf8")).version ?? "2.0.0"
const CHECK_ONLY = process.argv.includes("--check")

type Harness = "claude" | "opencode"
interface Plan { harness: Harness; description: string; tiers: Record<string, string>; roles?: Record<string, string>; brain_effort?: string; experimental?: boolean; route_samples?: number }
interface Plans {
  models: { claude: Record<string, string>; local: Record<string, { name: string; context: number; output: number; reasoning: boolean }> }
  plans: Record<string, Plan>
  default_plan: string
  capabilities: Record<string, { claude: { tools: string[] }; opencode: Record<string, unknown> }>
  claude_managed_tools: string[]
}
interface Doc { file: string; meta: Record<string, any>; body: string }

const errors: string[] = []
const fail = (msg: string) => errors.push(msg)

// ---------- loading ----------
const expandHome = (p: string) => (p.startsWith("~/") ? path.join(homedir(), p.slice(2)) : p)

function loadYaml<T>(file: string): T {
  return YAML.parse(readFileSync(file, "utf8")) as T
}

function parseDoc(file: string): Doc {
  const raw = readFileSync(file, "utf8")
  const m = raw.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/)
  if (!m) throw new Error(`${file}: missing YAML frontmatter`)
  return { file, meta: YAML.parse(m[1]) ?? {}, body: m[2].trim() + "\n" }
}

function loadDir(dir: string): Doc[] {
  return readdirSync(dir).filter((f) => f.endsWith(".md")).sort().map((f) => parseDoc(path.join(dir, f)))
}

const plans = loadYaml<Plans>(path.join(SRC, "plans.yaml"))
const configFile = existsSync(path.join(ROOT, "config.local.yaml")) ? "config.local.yaml" : "config.example.yaml"
const config = loadYaml<any>(path.join(ROOT, configFile))
const pathsCfg: Record<string, string> = Object.fromEntries(Object.entries(config.paths ?? {}).map(([k, v]) => [k, expandHome(String(v))]))
const agents = loadDir(path.join(SRC, "agents"))
const workflows = loadDir(path.join(SRC, "workflows"))
const shared: Record<string, string> = Object.fromEntries(loadDir(path.join(SRC, "shared")).map((d) => [path.basename(d.file, ".md"), d.body]))
const agentNames = new Set(agents.map((a) => a.meta.name))
const workflowNames = new Set(workflows.map((w) => w.meta.name))

// ---------- templating ----------
// {{agent:x}} {{skill:x}} {{path:key}} {{include:x}} {{plan}} and {{#claude}}…{{/claude}} / {{#opencode}}…{{/opencode}} blocks
function render(text: string, harness: Harness, planName: string, origin: string): string {
  let out = text
  for (let i = 0; i < 3; i++) {
    out = out.replace(/\{\{include:([\w-]+)\}\}/g, (_, name) => {
      if (!(name in shared)) fail(`${origin}: unknown include '${name}'`)
      return shared[name] ?? ""
    })
  }
  out = out.replace(/\{\{#(claude|opencode)\}\}([\s\S]*?)\{\{\/\1\}\}/g, (_, h, inner) => (h === harness ? inner : ""))
  out = out.replace(/\{\{agent:([\w-]+)\}\}/g, (_, name) => {
    if (!agentNames.has(name) && name !== "explore") fail(`${origin}: unknown agent '${name}'`)
    return harness === "claude" ? `${PLUGIN_NAME}:${name}` : name
  })
  out = out.replace(/\{\{skill:([\w-]+)\}\}/g, (_, name) => {
    if (!workflowNames.has(name)) fail(`${origin}: unknown workflow '${name}'`)
    return harness === "claude" ? `${PLUGIN_NAME}:${name}` : name
  })
  out = out.replace(/\{\{path:([\w-]+)\}\}/g, (_, key) => {
    if (!(key in pathsCfg)) fail(`${origin}: unknown path '${key}'`)
    return pathsCfg[key] ?? key
  })
  out = out.replace(/\{\{plan\}\}/g, planName)
  out = out.replace(/\n{3,}/g, "\n\n")
  const leftover = out.match(/\{\{[^}]*\}\}/)
  if (leftover) fail(`${origin}: unresolved template ${leftover[0]}`)
  return out
}

// ---------- model resolution ----------
function modelFor(agent: Doc, planName: string): string {
  const plan = plans.plans[planName]
  const name = agent.meta.name as string
  const key = plan.roles?.[name] ?? plan.tiers[agent.meta.tier]
  if (!key) fail(`plan ${planName}: no model for tier '${agent.meta.tier}' (agent ${name})`)
  if (plan.harness === "claude" && !plan.tiers.brain.match(/^(fable|opus|sonnet|haiku)$/)) return key // local plan: router model ids
  if (key in plans.models.claude) return plans.models.claude[key]
  if (key in plans.models.local) return key
  fail(`plan ${planName}: unknown model '${key}'`)
  return key
}

function capList(agent: Doc): string[] {
  const caps: string[] = agent.meta.capabilities ?? []
  for (const c of caps) if (!(c in plans.capabilities)) fail(`${agent.file}: unknown capability '${c}'`)
  return caps
}

// ---------- YAML frontmatter writer ----------
function frontmatter(meta: Record<string, unknown>): string {
  const clean = Object.fromEntries(Object.entries(meta).filter(([, v]) => v !== undefined && v !== null))
  return `---\n${YAML.stringify(clean, { lineWidth: 0 }).trim()}\n---\n\n`
}

const GENERATED = "<!-- Generated by scripts/build.ts from src/ — edit the source, not this file. -->\n\n"

// ---------- Claude Code plugin per plan ----------
// env for the arch-tools MCP server; plan_route votes with the plan's brain model when route_samples > 0
function archToolsEnv(planName: string): Record<string, string> {
  const plan = plans.plans[planName]
  return {
    ARCH_LLM_BASE: config.llm.chat_base,
    ARCH_RETRIEVAL_BASE: config.llm.retrieval_base,
    ARCH_LLM_KEY_FILE: expandHome(config.llm.api_key_file),
    ARCH_MEMORY_CLI: pathsCfg.memory_cli,
    ARCH_LIBRARY_DIRS: `${pathsCfg.research_hub}:${pathsCfg.research_workspace}`,
    ARCH_ROUTE_SAMPLES: String(plan.route_samples ?? 0),
    ARCH_ROUTE_MODEL: plan.tiers.brain in plans.models.local ? plan.tiers.brain : "",
  }
}

function mcpServersClaude(planName: string): Record<string, unknown> {
  const env = archToolsEnv(planName)
  const servers: Record<string, unknown> = {
    "arch-tools": { type: "stdio", command: pathsCfg.uv, args: ["run", "--script", path.join(ROOT, "mcp/arch-tools/server.py"), "serve"], env },
  }
  for (const [name, s] of Object.entries<any>(config.mcp ?? {})) {
    if (!s.enabled) continue
    if (s.url) {
      servers[name] = { type: "http", url: s.url, headers: s.token_env ? { Authorization: `Bearer \${${s.token_env}}` } : undefined }
    } else {
      const cmd = (s.command as string[]).map((c) => expandHome(c.replace(/\{(\w+)\}/g, (_, k) => pathsCfg[k] ?? k)))
      servers[name] = { type: "stdio", command: cmd[0], args: cmd.slice(1), env: s.env }
    }
  }
  return servers
}

function buildClaudePlugin(planName: string) {
  const plan = plans.plans[planName]
  const out = path.join(BUILD, "claude", planName)
  rmSync(out, { recursive: true, force: true })
  mkdirSync(path.join(out, ".claude-plugin"), { recursive: true })
  writeFileSync(path.join(out, ".claude-plugin/plugin.json"), JSON.stringify({
    name: PLUGIN_NAME, version: VERSION, author: { name: "juancgar" },
    description: `arch-agents v2 — ${planName} plan: ${plan.description}`,
  }, null, 2) + "\n")

  const isLocal = !plan.tiers.brain.match(/^(fable|opus|sonnet|haiku)$/)
  mkdirSync(path.join(out, "agents"), { recursive: true })
  for (const a of agents) {
    if (a.meta.harness && a.meta.harness !== "claude") continue
    const granted = new Set(capList(a).flatMap((c) => plans.capabilities[c]?.claude.tools ?? []))
    const disallowed = plans.claude_managed_tools.filter((t) => !granted.has(t))
    const effort = a.meta.mode === "primary" ? plan.brain_effort : a.meta.effort
    const fm = frontmatter({
      name: a.meta.name,
      description: a.meta.description,
      model: modelFor(a, planName),
      effort: isLocal ? undefined : effort,
      disallowedTools: disallowed.length ? disallowed.join(", ") : undefined,
      maxTurns: a.meta.steps,
      color: a.meta.color,
    })
    writeFileSync(path.join(out, "agents", `${a.meta.name}.md`), fm + GENERATED + render(a.body, "claude", planName, a.file))
  }

  for (const w of workflows) {
    const dir = path.join(out, "skills", w.meta.name)
    mkdirSync(dir, { recursive: true })
    const fm = frontmatter({ name: w.meta.name, description: w.meta.description, "argument-hint": w.meta["argument-hint"] })
    writeFileSync(path.join(dir, "SKILL.md"), fm + GENERATED + render(w.body, "claude", planName, w.file))
  }

  // hooks (deterministic gates) — scripts are referenced via ${CLAUDE_PLUGIN_ROOT}
  cpSync(path.join(ROOT, "hooks"), path.join(out, "hooks"), { recursive: true })
  for (const f of readdirSync(path.join(out, "hooks"))) if (f.endsWith(".py") || f.endsWith(".sh")) chmodSync(path.join(out, "hooks", f), 0o755)
  writeFileSync(path.join(out, "hooks", "paths.json"), JSON.stringify({
    repo_root: ROOT,
    uv: pathsCfg.uv,
    arch_tools_server: path.join(ROOT, "mcp/arch-tools/server.py"),
    writable: [pathsCfg.research_hub, pathsCfg.research_workspace],
  }, null, 2) + "\n")

  writeFileSync(path.join(out, ".mcp.json"), JSON.stringify({ mcpServers: mcpServersClaude(planName) }, null, 2) + "\n")
  return out
}

// ---------- OpenCode config dir ----------
function deepMerge(a: any, b: any): any {
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return b
  const out = { ...a }
  for (const [k, v] of Object.entries(b)) out[k] = k in out ? deepMerge(out[k], v) : v
  return out
}

function opencodePermission(agent: Doc): Record<string, unknown> {
  // files outside the project are off limits, except the research locations (notes, papers, reviews live
  // there and sessions are often started from a code project) and /tmp
  const external = Object.fromEntries([["*", "deny"], ...[pathsCfg.research_hub, pathsCfg.research_workspace, "/tmp"].flatMap((d) => [[`${d}/**`, "allow"], [`${d}/*`, "allow"]])])
  let perm: Record<string, unknown> = { "*": "deny", doom_loop: "deny", external_directory: external }
  // later capabilities win for bash patterns (shell is broader than git_read)
  const caps = capList(agent).sort((x, y) => (x === "shell" ? 1 : y === "shell" ? -1 : 0))
  for (const c of caps) perm = deepMerge(perm, plans.capabilities[c].opencode)
  if (agent.meta.opencode_permission) perm = deepMerge(perm, agent.meta.opencode_permission)
  return perm
}

function buildOpencode() {
  const planName = Object.entries(plans.plans).find(([, p]) => p.harness === "opencode")?.[0]
  if (!planName) return
  const out = path.join(BUILD, "opencode")
  rmSync(out, { recursive: true, force: true })
  mkdirSync(path.join(out, "agents"), { recursive: true })
  mkdirSync(path.join(out, "commands"), { recursive: true })

  for (const a of agents) {
    if (a.meta.harness && a.meta.harness !== "opencode") continue
    const isPrimary = a.meta.mode === "primary"
    const perm = opencodePermission(a)
    if (isPrimary) {
      // the orchestrator may delegate only to the defined specialists
      perm.task = Object.fromEntries([["*", "deny"], ...[...agentNames].filter((n) => n !== a.meta.name).map((n) => [n, "allow"])])
      // only our workflow skills: OpenCode also lists every skill in ~/.claude and ~/.agents, which bloats the
      // prompt of a small local model with unrelated options (art, slides, documents…)
      perm.skill = Object.fromEntries([["*", "deny"], ...workflows.map((w) => [w.meta.name, "allow"])])
    }
    const fm = frontmatter({
      description: a.meta.description,
      mode: isPrimary ? "primary" : "subagent",
      model: `llamacpp/${modelFor(a, planName)}`,
      temperature: a.meta.temperature ?? 0.1,
      steps: a.meta.steps,
      permission: perm,
    })
    writeFileSync(path.join(out, "agents", `${a.meta.name}.md`), fm + GENERATED + render(a.body, "opencode", planName, a.file))
  }
  for (const w of workflows) {
    const fm = frontmatter({ description: w.meta.description, agent: "orchestrator" })
    const body = `Run the **${w.meta.name}** workflow for:\n\n$ARGUMENTS\n\n` + render(w.body, "opencode", planName, w.file)
    writeFileSync(path.join(out, "commands", `${w.meta.name}.md`), fm + GENERATED + body)
    const dir = path.join(out, "skills", w.meta.name)
    mkdirSync(dir, { recursive: true })
    writeFileSync(path.join(dir, "SKILL.md"), frontmatter({ name: w.meta.name, description: w.meta.description }) + GENERATED + render(w.body, "opencode", planName, w.file))
  }

  // opencode.json
  const models = Object.fromEntries(Object.entries(plans.models.local).map(([id, m]) => [id, {
    name: m.name, tool_call: true, reasoning: m.reasoning, temperature: true, limit: { context: m.context, output: m.output },
  }]))
  const mcp: Record<string, unknown> = {
    "arch-tools": {
      type: "local", command: [pathsCfg.uv, "run", "--script", path.join(ROOT, "mcp/arch-tools/server.py"), "serve"], enabled: true,
      environment: archToolsEnv(planName),
    },
  }
  for (const [name, s] of Object.entries<any>(config.mcp ?? {})) {
    if (s.url) {
      mcp[name] = { type: "remote", url: s.url, enabled: !!s.enabled, oauth: false, headers: s.token_env ? { Authorization: `Bearer {env:${s.token_env}}`, "X-MCP-Readonly": "true" } : undefined }
    } else {
      const cmd = (s.command as string[]).map((c) => expandHome(c.replace(/\{(\w+)\}/g, (_, k) => pathsCfg[k] ?? k)))
      mcp[name] = { type: "local", command: cmd, enabled: !!s.enabled, environment: s.env, timeout: s.timeout }
    }
  }
  const opencodeJson = {
    $schema: "https://opencode.ai/config.json",
    model: `llamacpp/${plans.plans[planName].tiers.brain}`,
    // titles/summaries use the brain model too: with one model in VRAM, a separate small model would force a
    // swap (and a full re-read of the system prompt) at the start of every session
    small_model: `llamacpp/${plans.plans[planName].tiers.brain}`,
    default_agent: "orchestrator",
    // hide OpenCode's built-in primary agents so sessions always start in the v2 orchestrator
    agent: { build: { disable: true }, plan: { disable: true } },
    provider: {
      llamacpp: {
        npm: "@ai-sdk/openai-compatible", name: "llama.cpp router (llm-server)",
        options: { baseURL: `${config.llm.chat_base}/v1`, apiKey: `{file:${config.llm.api_key_file}}`, timeout: 900000 },
        models,
      },
    },
    mcp,
    permission: {
      memory_remember: "deny", memory_forget: "deny", memory_propose: "deny", memory_inspect: "deny", memory_decide: "deny",
      "zotero_*": "deny", lsp: "deny", ast_grep: "deny",
    },
    lsp: true,
  }
  writeFileSync(path.join(out, "opencode.json"), JSON.stringify(opencodeJson, null, 2) + "\n")

  // custom tools (Phase 2A memory, local papers, ast-grep) + their library and deps
  cpSync(path.join(ROOT, "tools"), path.join(out, "tools"), { recursive: true })
  cpSync(path.join(ROOT, "lib"), path.join(out, "lib"), { recursive: true })
  cpSync(path.join(ROOT, "package.json"), path.join(out, "package.json"))
  symlinkSync(path.join(ROOT, "node_modules"), path.join(out, "node_modules"))
}

// ---------- validation of sources ----------
function validateSources() {
  const tiers = new Set(["brain", "heavy", "mid", "light"])
  for (const a of agents) {
    for (const k of ["name", "description", "tier", "capabilities"]) if (!(k in a.meta)) fail(`${a.file}: missing '${k}'`)
    if (!tiers.has(a.meta.tier)) fail(`${a.file}: bad tier '${a.meta.tier}'`)
    if (a.meta.effort && !["low", "medium", "high", "xhigh", "max"].includes(a.meta.effort)) fail(`${a.file}: bad effort`)
    if (path.basename(a.file, ".md") !== a.meta.name) fail(`${a.file}: file name must match name '${a.meta.name}'`)
  }
  for (const w of workflows) {
    for (const k of ["name", "description"]) if (!(k in w.meta)) fail(`${w.file}: missing '${k}'`)
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(w.meta.name)) fail(`${w.file}: workflow name must be kebab-case`)
    if (path.basename(w.file, ".md") !== w.meta.name) fail(`${w.file}: file name must match name`)
  }
  for (const [p, plan] of Object.entries(plans.plans)) for (const t of tiers) if (!plan.tiers[t]) fail(`plan ${p}: missing tier ${t}`)
  if (!agents.some((a) => a.meta.mode === "primary")) fail("no primary (orchestrator) agent")
}

// ---------- resolved plans for the launcher (bin/arch) ----------
function writeLauncherPlans() {
  const orchestrator = agents.find((a) => a.meta.mode === "primary")!
  const resolved: Record<string, unknown> = {}
  for (const [name, plan] of Object.entries(plans.plans)) {
    const isLocal = !plan.tiers.brain.match(/^(fable|opus|sonnet|haiku)$/)
    const env: Record<string, string> = {}
    if (plan.harness === "claude" && isLocal) {
      // Claude Code → llama.cpp router (Anthropic Messages API). Unsupported by Anthropic; marked experimental.
      Object.assign(env, {
        ANTHROPIC_BASE_URL: config.llm.chat_base,
        ANTHROPIC_MODEL: plan.tiers.brain,
        ANTHROPIC_DEFAULT_OPUS_MODEL: plan.tiers.heavy,
        ANTHROPIC_DEFAULT_SONNET_MODEL: plan.tiers.mid,
        ANTHROPIC_DEFAULT_HAIKU_MODEL: plan.tiers.light,
        CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS: "1",
        CLAUDE_CODE_MAX_CONTEXT_TOKENS: String(plans.models.local[plan.tiers.brain]?.context ?? 65536),
        DISABLE_INTERLEAVED_THINKING: "1",
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
      })
    }
    resolved[name] = {
      harness: plan.harness,
      description: plan.description,
      experimental: !!plan.experimental,
      local_models: isLocal,
      model: plan.harness === "claude" ? modelFor(orchestrator, name) : `llamacpp/${plan.tiers.brain}`,
      effort: isLocal ? null : plan.brain_effort ?? null,
      plugin_dir: plan.harness === "claude" ? path.join(BUILD, "claude", name) : null,
      env,
      api_key_file: isLocal ? expandHome(config.llm.api_key_file) : null,
    }
  }
  writeFileSync(path.join(BUILD, "plans.json"), JSON.stringify({ default_plan: plans.default_plan, opencode_dir: path.join(BUILD, "opencode"), plans: resolved }, null, 2) + "\n")
}

validateSources()
if (!CHECK_ONLY) {
  mkdirSync(BUILD, { recursive: true })
  for (const [name, plan] of Object.entries(plans.plans)) if (plan.harness === "claude") buildClaudePlugin(name)
  buildOpencode()
  writeLauncherPlans()
} else {
  // render everything once per harness to surface template errors without writing
  for (const h of ["claude", "opencode"] as Harness[]) for (const d of [...agents, ...workflows]) render(d.body, h, plans.default_plan, d.file)
}

if (errors.length) {
  console.error(`✗ build failed with ${errors.length} error(s):\n  - ` + [...new Set(errors)].join("\n  - "))
  process.exit(1)
}
console.log(`✓ ${CHECK_ONLY ? "checked" : "built"} ${agents.length} agents, ${workflows.length} workflows, plans: ${Object.keys(plans.plans).join(", ")} (config: ${configFile})`)
