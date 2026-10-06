import { tool, type ToolContext } from "@opencode-ai/plugin/tool"
import { spawn } from "node:child_process"
import { readFile, realpath, stat } from "node:fs/promises"
import { homedir } from "node:os"
import path from "node:path"

type RunOptions = { cwd?: string; input?: string; signal?: AbortSignal; timeoutMs?: number }
export type Runner = (argv: string[], options?: RunOptions) => Promise<string>

export const runProcess: Runner = (argv, options = {}) => new Promise((resolve, reject) => {
  if (options.signal?.aborted) {
    reject(new Error("memory_process_aborted"))
    return
  }
  const grouped = process.platform !== "win32"
  const child = spawn(argv[0], argv.slice(1), {
    cwd: options.cwd, stdio: ["pipe", "pipe", "pipe"], shell: false, detached: grouped,
    // The memory service loads its embedding model on the GPU when one is visible, which runs out of memory
    // while a local LLM (llm-server) holds the VRAM. Run it on the CPU unless MEMORY_USE_GPU=1.
    env: process.env.MEMORY_USE_GPU === "1" ? process.env : { ...process.env, CUDA_VISIBLE_DEVICES: "" },
  })
  let stdout = "", stderr = "", settled = false
  const finish = (error?: Error, output?: string) => {
    if (settled) return
    settled = true
    clearTimeout(timer)
    options.signal?.removeEventListener("abort", onAbort)
    if (error) reject(error)
    else resolve(output ?? "")
  }
  const terminate = () => {
    if (!child.pid) return
    try {
      if (grouped) process.kill(-child.pid, "SIGKILL")
      else child.kill("SIGKILL")
    } catch { /* The process may have already exited. */ }
  }
  const onAbort = () => {
    terminate()
    finish(new Error("memory_process_aborted"))
  }
  const timer = setTimeout(() => {
    terminate()
    finish(new Error("memory_process_timeout"))
  }, options.timeoutMs ?? 90_000)
  options.signal?.addEventListener("abort", onAbort, { once: true })
  if (options.signal?.aborted) onAbort()
  child.stdout.setEncoding("utf8")
  child.stderr.setEncoding("utf8")
  child.stdout.on("data", (data) => {
    stdout += data
    if (stdout.length > 2_000_000) {
      terminate()
      finish(new Error("memory_output_too_large"))
    }
  })
  child.stderr.on("data", (data) => { stderr = (stderr + data).slice(-16_000) })
  child.on("error", (error) => finish(error))
  child.stdin.on("error", (error) => { terminate(); finish(error) })
  child.on("close", (code) => {
    if (code !== 0) finish(new Error(stderr.trim() || `memory_process_failed:${code}`))
    else finish(undefined, stdout.trim())
  })
  child.stdin.end(options.input ?? "")
})

const collections = ["project_memory", "research_memory", "task_memory", "knowledge_memory"] as const
const durableTypes = ["architecture_decision", "repo_constraint", "interface_contract", "environment_constraint", "bug_pattern", "command_recipe"] as const
const memoryTypes = [...durableTypes, "task_state"] as const
const statuses = ["active", "stale", "superseded", "closed"] as const
const shortText = () => tool.schema.string().trim().min(1).max(2000)
const identifier = () => tool.schema.string().trim().min(1).max(200)
const evidence = tool.schema.object({
  kind: tool.schema.enum(["test", "repository", "environment", "review"]),
  reference: shortText().describe("file:relative/path, git:commit:relative/path, or session:sessionID/messageID/partID; never a shell command"),
  result: shortText(),
  outcome: tool.schema.enum(["passed", "confirmed", "failed", "unknown"]),
  verification_source: tool.schema.enum(["tester", "reviewer", "repository", "runtime", "coder", "orchestrator"]),
}).strict()

async function projectOrigin(context: ToolContext, runner: Runner, supplied?: { project?: string; project_reference?: string }) {
  // OpenCode can use '/' as a worktree sentinel outside Git repositories.
  // Start at the actual session directory; Git supplies its root when present.
  let root = await realpath(context.directory || context.worktree)
  let basis: "git_root" | "directory" | "repository_guidance" = "directory"
  let commit: string | null = null
  let dirty: boolean | null = null
  const gitOptions = { cwd: root, signal: context.abort, timeoutMs: 5000 }
  try {
    root = await realpath(await runner(["git", "-C", root, "rev-parse", "--show-toplevel"], gitOptions))
    basis = "git_root"
  } catch (error) {
    if (context.abort.aborted) throw error
  }
  if (basis === "git_root") {
    const [head, status] = await Promise.allSettled([
      runner(["git", "-C", root, "rev-parse", "--verify", "HEAD"], gitOptions),
      runner(["git", "-C", root, "status", "--porcelain=v1", "--untracked-files=normal"], gitOptions),
    ])
    if (head.status === "fulfilled" && /^[0-9a-f]{40,64}$/.test(head.value)) commit = head.value
    if (status.status !== "fulfilled") throw new Error("repository_status_unavailable")
    dirty = status.value.length > 0
  }
  let project = path.basename(root)
  let reference: string | null = null
  const guidanceName = (supplied?.project_reference ?? "AGENTS.md").replace(/^file:/, "").split("#", 1)[0]
  const lexical = path.resolve(root, guidanceName)
  if (path.isAbsolute(guidanceName) || !inside(root, lexical)) throw new Error("project_reference_outside_repository")
  let guidancePath: string | null = null
  try { guidancePath = await realpath(lexical) } catch (error: any) {
    if (supplied?.project_reference || error.code !== "ENOENT") throw error
  }
  if (guidancePath) {
    if (!inside(root, guidancePath)) throw new Error("project_reference_outside_repository")
    const info = await stat(guidancePath)
    if (!info.isFile() || info.size > 256_000) throw new Error("invalid_project_reference")
    const content = await readFile(guidancePath, "utf8")
    const ids = [...content.matchAll(/^\s*memory_project:\s*([A-Za-z0-9_.-]+)\s*$/gm)].map((m) => m[1])
    if (ids.length > 1) throw new Error("ambiguous_project_identity")
    if (ids.length === 1) {
      project = ids[0]
      basis = "repository_guidance"
      reference = `file:${path.relative(root, guidancePath)}`
    } else if (supplied?.project_reference) throw new Error("project_declaration_missing")
  }
  if (supplied?.project && supplied.project !== project) throw new Error("project_identity_mismatch")
  return {
    project,
    origin: {
      session_id: context.sessionID, message_id: context.messageID, agent: context.agent,
      repository_root: root, source_commit: commit, worktree_dirty: dirty,
      project_basis: basis, project_reference: reference,
    },
  }
}

function inside(root: string, target: string) {
  const relative = path.relative(root, target)
  return relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative)
}

function requireAgent(context: ToolContext, agent: string) {
  if (context.agent !== agent) throw new Error("memory_actor_not_allowed")
}

export function createMemoryTools(options: { runner?: Runner; memoryExecutable?: string } = {}) {
  const runner = options.runner ?? runProcess
  const executable = options.memoryExecutable ?? path.join(homedir(), ".local/bin/memory")
  async function legacy(args: string[], context: ToolContext) {
    return runner([executable, ...args], { signal: context.abort })
  }
  async function shadow(command: string, body: object, context: ToolContext) {
    const started = performance.now()
    const output = await runner([executable, command, "--json"], {
      input: JSON.stringify(body), signal: context.abort,
    })
    let result: any
    try { result = JSON.parse(output) } catch { throw new Error("invalid_memory_service_json") }
    if (!result || result.mode !== "shadow" || result.applied !== false || result.error) {
      throw new Error("invalid_shadow_service_result")
    }
    context.metadata({ title: `Memory shadow: ${command}`, metadata: { mode: "shadow", applied: false, elapsed_ms: performance.now() - started } })
    return JSON.stringify(result)
  }
  const search = tool({
    description: "Search stored memories selectively. Shadow candidates are excluded. Repository evidence overrides memory.",
    args: {
      collection: tool.schema.enum(collections), query: tool.schema.string(),
      project: tool.schema.string().optional(), source: tool.schema.string().optional(),
      tags: tool.schema.array(tool.schema.string()).optional(),
      memory_types: tool.schema.array(tool.schema.enum(memoryTypes)).optional(),
      source_path: tool.schema.string().optional(), source_commit: tool.schema.string().optional(),
      scope_paths: tool.schema.array(tool.schema.string()).optional(),
      status: tool.schema.enum(statuses).optional(), limit: tool.schema.number().int().min(1).max(10).default(5),
    },
    async execute(args, context) {
      const cmd = ["search", args.collection, args.query, "--limit", String(args.limit)]
      for (const [key, value] of Object.entries(args)) {
        if (["collection", "query", "limit"].includes(key) || value === undefined) continue
        const encoded = Array.isArray(value) ? value.join(",") : String(value)
        if (encoded) cmd.push(`--${key.replaceAll("_", "-")}`, encoded)
      }
      return legacy(cmd, context)
    },
  })
  const remember = tool({
    description: "Paused during the shadow pilot. Automatic inserts are unavailable for all collections.",
    args: {
      collection: tool.schema.enum(collections), text: tool.schema.string(),
      project: tool.schema.string().optional(), source: tool.schema.string().optional(),
      tags: tool.schema.array(tool.schema.string()).optional(), memory_type: tool.schema.enum(memoryTypes).optional(),
      source_path: tool.schema.string().optional(), source_commit: tool.schema.string().optional(),
      scope_paths: tool.schema.array(tool.schema.string()).optional(), status: tool.schema.enum(statuses).optional(),
      last_verified_at: tool.schema.string().optional(),
    },
    async execute() { throw new Error("automatic_memory_writes_paused_shadow_pilot") },
  })
  const forget = tool({
    description: "Paused during the shadow pilot. Automatic memory deletion is unavailable.",
    args: { collection: tool.schema.enum(collections), id: tool.schema.string() },
    async execute() { throw new Error("automatic_memory_writes_paused_shadow_pilot") },
  })
  const stats = tool({
    description: "Count stored memories in each collection. Shadow candidates are not included.",
    args: {},
    async execute(_args, context) { return legacy(["stats"], context) },
  })
  const propose = tool({
    description: "Orchestrator only: record zero or one coding-memory candidate per completed task. Use candidate=null and a skip_reason for no-candidate tasks. Journal only; never inserts a memory.",
    args: {
      task_id: identifier().describe("Stable ID for this coding task within the originating session; reuse on retries"),
      project: identifier().optional(), project_reference: shortText().optional(),
      outcome: tool.schema.object({
        kind: tool.schema.enum(["fix", "investigation", "trivial", "other"]),
        status: tool.schema.enum(["completed", "failed", "incomplete"]), verification_summary: shortText(),
      }).strict(),
      candidate: tool.schema.object({
        memory_type: tool.schema.enum(durableTypes), text: shortText(), durability_reason: shortText(),
        evidence: tool.schema.array(evidence).min(1).max(10),
        source_paths: tool.schema.array(shortText()).max(20).default([]),
      }).strict().nullable(),
      skip_reason: shortText().optional(),
    },
    async execute(args, context) {
      requireAgent(context, "orchestrator")
      const resolved = await projectOrigin(context, runner, args)
      return shadow("propose", {
        schema_version: 1, collection: "project_memory", task_id: args.task_id,
        project: resolved.project, origin: resolved.origin, outcome: args.outcome,
        candidate: args.candidate, skip_reason: args.skip_reason ?? null,
      }, context)
    },
  })
  const inspect = tool({
    description: "Memory Manager only: inspect the canonical candidate, evidence references, and live-memory comparison. Earlier shadow proposals are not facts.",
    args: { candidate_id: identifier() },
    async execute(args, context) {
      requireAgent(context, "memory-manager")
      const { origin } = await projectOrigin(context, runner)
      return shadow("inspect", { ...args, origin }, context)
    },
  })
  const decide = tool({
    description: "Memory Manager only: record a reasoned shadow operation after inspection. The service validates the recommendation; applied is always false.",
    args: {
      candidate_id: identifier(),
      recommendation: tool.schema.object({
        operation: tool.schema.enum(["ADD", "UPDATE", "SUPERSEDE", "NOOP"]),
        rationale: shortText(), target_id: identifier().nullable().optional(),
        evidence_indexes: tool.schema.array(tool.schema.number().int().min(0).max(9)).max(10).default([]),
        assessment: tool.schema.object({
          supported: tool.schema.boolean(), durable: tool.schema.boolean(), atomic: tool.schema.boolean(),
          non_obvious: tool.schema.boolean(), non_speculative: tool.schema.boolean(),
          relation: tool.schema.enum(["new", "equivalent", "changed", "uncertain"]),
          additional_evidence: tool.schema.boolean().default(false),
        }).strict(),
      }).strict(),
    },
    async execute(args, context) {
      requireAgent(context, "memory-manager")
      const { origin } = await projectOrigin(context, runner)
      return shadow("decide", { ...args, origin }, context)
    },
  })
  return { search, remember, forget, stats, propose, inspect, decide }
}
