import { tool } from "@opencode-ai/plugin"

const MEMORY = `${process.env.HOME}/.local/bin/memory`

const collections = [
  "project_memory",
  "research_memory",
  "task_memory",
  "knowledge_memory",
] as const

const memoryTypes = [
  "architecture_decision",
  "repo_constraint",
  "interface_contract",
  "environment_constraint",
  "bug_pattern",
  "command_recipe",
  "task_state",
] as const

const memoryStatuses = [
  "active",
  "stale",
  "superseded",
  "closed",
] as const

async function run(args: string[]) {
  const p = Bun.spawn([MEMORY, ...args], {
    stdout: "pipe",
    stderr: "pipe",
  })

  const stdout = await new Response(p.stdout).text()
  const stderr = await new Response(p.stderr).text()
  const code = await p.exited

  if (code !== 0) {
    throw new Error(stderr || `memory exited with code ${code}`)
  }

  return stdout.trim()
}

export const search = tool({
  description:
    "Search persistent semantic memory. For coding work, prefer project-scoped searches and relevant memory types/status filters instead of broad unfiltered retrieval.",
  args: {
    collection: tool.schema.enum(collections),
    query: tool.schema.string(),

    project: tool.schema.string().optional(),
    source: tool.schema.string().optional(),
    tags: tool.schema.array(tool.schema.string()).optional(),

    memory_types: tool.schema
      .array(tool.schema.enum(memoryTypes))
      .optional(),

    source_path: tool.schema.string().optional(),
    source_commit: tool.schema.string().optional(),

    scope_paths: tool.schema
      .array(tool.schema.string())
      .optional(),

    status: tool.schema.enum(memoryStatuses).optional(),

    limit: tool.schema.number().int().min(1).max(10).default(5),
  },

  async execute(args) {
    const cmd = [
      "search",
      args.collection,
      args.query,
      "--limit",
      String(args.limit),
    ]

    if (args.project) {
      cmd.push("--project", args.project)
    }

    if (args.source) {
      cmd.push("--source", args.source)
    }

    if (args.tags?.length) {
      cmd.push("--tags", args.tags.join(","))
    }

    if (args.memory_types?.length) {
      cmd.push("--memory-types", args.memory_types.join(","))
    }

    if (args.source_path) {
      cmd.push("--source-path", args.source_path)
    }

    if (args.source_commit) {
      cmd.push("--source-commit", args.source_commit)
    }

    if (args.scope_paths?.length) {
      cmd.push("--scope-paths", args.scope_paths.join(","))
    }

    if (args.status) {
      cmd.push("--status", args.status)
    }

    return run(cmd)
  },
})

export const remember = tool({
  description:
    "Store one important durable memory. Coding memories may include type, repository provenance, scope, status, and verification time. Do not store routine outputs, temporary logs, secrets, speculation, or obvious repository facts.",
  args: {
    collection: tool.schema.enum(collections),
    text: tool.schema.string(),

    project: tool.schema.string().optional(),
    source: tool.schema.string().optional(),
    tags: tool.schema.array(tool.schema.string()).optional(),

    memory_type: tool.schema.enum(memoryTypes).optional(),

    source_path: tool.schema.string().optional(),
    source_commit: tool.schema.string().optional(),

    scope_paths: tool.schema
      .array(tool.schema.string())
      .optional(),

    status: tool.schema.enum(memoryStatuses).optional(),

    last_verified_at: tool.schema.string().optional(),
  },

  async execute(args) {
    const cmd = [
      "remember",
      args.collection,
      args.text,
    ]

    if (args.project) {
      cmd.push("--project", args.project)
    }

    if (args.source) {
      cmd.push("--source", args.source)
    }

    if (args.tags?.length) {
      cmd.push("--tags", args.tags.join(","))
    }

    if (args.memory_type) {
      cmd.push("--memory-type", args.memory_type)
    }

    if (args.source_path) {
      cmd.push("--source-path", args.source_path)
    }

    if (args.source_commit) {
      cmd.push("--source-commit", args.source_commit)
    }

    if (args.scope_paths?.length) {
      cmd.push("--scope-paths", args.scope_paths.join(","))
    }

    if (args.status) {
      cmd.push("--status", args.status)
    }

    if (args.last_verified_at) {
      cmd.push("--last-verified-at", args.last_verified_at)
    }

    return run(cmd)
  },
})

export const forget = tool({
  description:
    "Delete one persistent memory by collection and memory ID.",
  args: {
    collection: tool.schema.enum(collections),
    id: tool.schema.string(),
  },

  async execute(args) {
    return run([
      "forget",
      args.collection,
      args.id,
    ])
  },
})

export const stats = tool({
  description:
    "Show the number of stored memories in each collection.",
  args: {},

  async execute() {
    return run(["stats"])
  },
})
