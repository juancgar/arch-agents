import assert from "node:assert/strict"
import test from "node:test"
import { mkdtemp, mkdir, writeFile, rm, symlink } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { tool, type ToolContext } from "@opencode-ai/plugin/tool"
import { createMemoryTools, runProcess, type Runner } from "../lib/memory-tools.ts"

async function fixture(t: any) {
  const temp = await mkdtemp(path.join(tmpdir(), "shadow-tools-"))
  const root = path.join(temp, "sample-project")
  await mkdir(root)
  await mkdir(path.join(root, "nested"))
  t.after(() => rm(temp, { recursive: true, force: true }))
  const calls: { argv: string[]; input?: string }[] = []
  const runner: Runner = async (argv, options) => {
    calls.push({ argv, input: options?.input })
    if (argv[0] === "git") {
      if (argv.includes("--show-toplevel")) return root
      if (argv.includes("HEAD")) return "a".repeat(40)
      if (argv.includes("status")) return " M changed.py"
      throw new Error("unexpected git command")
    }
    return JSON.stringify({ mode: "shadow", applied: false, candidate_id: "candidate-one" })
  }
  const context = (agent = "orchestrator"): ToolContext => ({
    sessionID: "session-one", messageID: "message-one", agent,
    directory: path.join(root, "nested"), worktree: root, abort: new AbortController().signal,
    metadata() {}, async ask() { throw new Error("unexpected permission prompt") },
  })
  return { root, temp, calls, runner, context, tools: createMemoryTools({ runner, memoryExecutable: "/fixture/memory" }) }
}

function proposal() {
  return {
    task_id: "fix-one",
    outcome: { kind: "fix", status: "completed", verification_summary: "Tester verified the reconnect regression." },
    candidate: {
      memory_type: "bug_pattern", text: "Reset replay sequence after transport reconnect.",
      durability_reason: "The ordering matters across transports.", source_paths: [],
      evidence: [{ kind: "test", reference: "session:session-one/test-message/test-part", result: "Replay check passed.", outcome: "passed", verification_source: "tester" }],
    },
  }
}

test("proposal uses JSON stdin and stamps runtime provenance from the worktree", async (t) => {
  const f = await fixture(t)
  const args = tool.schema.object(f.tools.propose.args).parse(proposal())
  const output = JSON.parse(await f.tools.propose.execute(args, f.context()) as string)
  assert.equal(output.applied, false)
  const call = f.calls.find((c) => c.argv[0] === "/fixture/memory")!
  assert.deepEqual(call.argv, ["/fixture/memory", "propose", "--json"])
  const body = JSON.parse(call.input!)
  assert.equal(body.origin.repository_root, f.root)
  assert.equal(body.origin.agent, "orchestrator")
  assert.equal(body.origin.session_id, "session-one")
  assert.equal(body.origin.source_commit, "a".repeat(40))
  assert.equal(body.origin.worktree_dirty, true)
  assert.equal(body.project, "sample-project")
  assert.ok(!call.argv.join(" ").includes(body.candidate.text))
})

test("zero-candidate task records a skip without searching memory", async (t) => {
  const f = await fixture(t)
  const args = tool.schema.object(f.tools.propose.args).parse({
    task_id: "explain-one", candidate: null, skip_reason: "Trivial explanation.",
    outcome: { kind: "trivial", status: "completed", verification_summary: "Answered the supplied expression." },
  })
  await f.tools.propose.execute(args, f.context())
  const memory = f.calls.filter((c) => c.argv[0] === "/fixture/memory")
  assert.equal(memory.length, 1)
  assert.equal(JSON.parse(memory[0].input!).candidate, null)
  assert.equal(memory[0].argv[1], "propose")
})

test("non-Git sessions use the actual directory instead of the root worktree sentinel", async (t) => {
  const f = await fixture(t)
  const runner: Runner = (argv, options) => {
    if (argv[0] === "git") return Promise.reject(new Error("not a git repository"))
    return f.runner(argv, options)
  }
  const tools = createMemoryTools({ runner, memoryExecutable: "/fixture/memory" })
  await tools.propose.execute(proposal() as any, { ...f.context(), worktree: "/" })
  const body = JSON.parse(f.calls.find((c) => c.argv[0] === "/fixture/memory")!.input!)
  assert.equal(body.origin.repository_root, path.join(f.root, "nested"))
  assert.equal(body.project, "nested")
  assert.equal(body.origin.project_basis, "directory")
  assert.equal(body.origin.source_commit, null)
})

test("the runtime actor guard rejects every unauthorized shadow role before subprocesses", async (t) => {
  const f = await fixture(t)
  for (const role of ["coder", "tester", "researcher", "memory-manager"]) {
    await assert.rejects(f.tools.propose.execute(proposal() as any, f.context(role)), /actor_not_allowed/)
  }
  for (const name of ["inspect", "decide"] as const) {
    await assert.rejects(f.tools[name].execute({ candidate_id: "candidate-one" } as any, f.context()), /actor_not_allowed/)
  }
  assert.equal(f.calls.length, 0)
})

test("legacy writes fail for all collections and agents without invoking the CLI", async (t) => {
  const f = await fixture(t)
  for (const collection of ["project_memory", "research_memory", "task_memory", "knowledge_memory"]) {
    for (const agent of ["orchestrator", "memory-manager", "coder", "researcher"]) {
      await assert.rejects(f.tools.remember.execute({ collection, text: "write" } as any, f.context(agent)), /writes_paused/)
      await assert.rejects(f.tools.forget.execute({ collection, id: "id" } as any, f.context(agent)), /writes_paused/)
    }
  }
  assert.deepEqual(f.calls, [])
})

test("explicit project guidance takes precedence and mismatched project IDs fail", async (t) => {
  const f = await fixture(t)
  await writeFile(path.join(f.root, "AGENTS.md"), "memory_project: canonical-project\n")
  const args = tool.schema.object(f.tools.propose.args).parse({ ...proposal(), project: "canonical-project" })
  await f.tools.propose.execute(args, f.context())
  const body = JSON.parse(f.calls.find((c) => c.argv[0] === "/fixture/memory")!.input!)
  assert.equal(body.project, "canonical-project")
  assert.equal(body.origin.project_basis, "repository_guidance")
  assert.equal(body.origin.project_reference, "file:AGENTS.md")
  await assert.rejects(f.tools.propose.execute({ ...args, project: "parent-workspace" }, f.context()), /identity_mismatch/)
})

test("guidance references cannot escape via traversal or symlinks", async (t) => {
  const f = await fixture(t)
  await writeFile(path.join(f.temp, "outside.md"), "memory_project: outside\n")
  await symlink(path.join(f.temp, "outside.md"), path.join(f.root, "linked.md"))
  for (const reference of ["../outside.md", "linked.md"]) {
    await assert.rejects(f.tools.propose.execute({ ...proposal(), project_reference: reference } as any, f.context()), /outside_repository/)
  }
  assert.ok(f.calls.every((c) => c.argv[0] === "git"))
})

test("existing search filters and limits preserve CLI argument compatibility", async (t) => {
  const f = await fixture(t)
  await f.tools.search.execute({
    collection: "project_memory", query: "reconnect", project: "sample-project", source: "debug",
    tags: ["network", "retry"], memory_types: ["bug_pattern", "environment_constraint"],
    source_path: "src/client.py", source_commit: "abc", scope_paths: ["src", "tests"], status: "active", limit: 3,
  }, f.context("researcher"))
  assert.deepEqual(f.calls[0].argv, [
    "/fixture/memory", "search", "project_memory", "reconnect", "--limit", "3",
    "--project", "sample-project", "--source", "debug", "--tags", "network,retry",
    "--memory-types", "bug_pattern,environment_constraint", "--source-path", "src/client.py",
    "--source-commit", "abc", "--scope-paths", "src,tests", "--status", "active",
  ])
})

test("service responses must be valid shadow JSON and never claim applied=true", async (t) => {
  const f = await fixture(t)
  for (const response of ["Loading model...\n{}", '{"mode":"live","applied":true}', "null"]) {
    const runner: Runner = (argv, options) => argv[0] === "git" ? f.runner(argv, options) : Promise.resolve(response)
    const tools = createMemoryTools({ runner })
    await assert.rejects(tools.inspect.execute({ candidate_id: "id" }, f.context("memory-manager")), /invalid_(memory_service_json|shadow_service_result)/)
  }
})

test("decision tool supplies manager runtime context and cannot send arbitrary patches", async (t) => {
  const f = await fixture(t)
  const raw = {
    candidate_id: "id", recommendation: {
      operation: "NOOP", rationale: "Evidence is uncertain.", evidence_indexes: [],
      assessment: { supported: false, durable: true, atomic: true, non_obvious: true, non_speculative: false, relation: "uncertain" },
    },
  }
  const schema = tool.schema.object(f.tools.decide.args)
  const parsed = schema.parse(raw)
  await f.tools.decide.execute(parsed, f.context("memory-manager"))
  const call = f.calls.find((c) => c.argv[0] === "/fixture/memory")!
  assert.equal(call.argv[1], "decide")
  assert.equal(JSON.parse(call.input!).origin.agent, "memory-manager")
  assert.throws(() => schema.parse({ ...raw, recommendation: { ...raw.recommendation, patch: { text: "overwrite" } } }))
})

test("process runner sends literal stdin and drains diagnostics concurrently", async () => {
  const input = 'literal $(echo forbidden) `echo forbidden`\nsecond line'
  const output = await runProcess([process.execPath, "-e", "process.stderr.write('x'.repeat(100000)); process.stdin.pipe(process.stdout)"], { input })
  assert.equal(output, input)
})

test("process runner reports nonzero exits, cancellation, and timeouts", async () => {
  await assert.rejects(runProcess([process.execPath, "-e", "process.stderr.write('fixture failure'); process.exit(4)"]), /fixture failure/)
  await assert.rejects(runProcess([process.execPath, "-e", "setTimeout(() => {}, 10000)"], { timeoutMs: 30 }), /timeout/)
  const abort = new AbortController()
  abort.abort()
  await assert.rejects(runProcess([process.execPath, "-e", "setTimeout(() => {}, 10000)"], { signal: abort.signal }), /abort/i)
  const duringRun = new AbortController()
  const running = runProcess([process.execPath, "-e", "setTimeout(() => {}, 10000)"], { signal: duringRun.signal })
  setTimeout(() => duringRun.abort(), 30)
  await assert.rejects(running, /abort/i)
})
