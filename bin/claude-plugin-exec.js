#!/usr/bin/env node
// Runs the Claude Code CLI with the arch-agents plugin and orchestrator injected into its arguments.
// bin/arch-acp points CLAUDE_CODE_EXECUTABLE at this file, so ACP clients (Zed's agent panel) that
// drive Claude Code through the official adapter get the arch-agents orchestrator instead of plain Claude.
// A .js wrapper works whether the SDK spawns the executable directly or through `node` (ESM: package.json is "type": "module").
import { spawn } from "node:child_process"

const plugin = process.env.ARCH_PLUGIN_DIR
if (!plugin) {
  process.stderr.write("claude-plugin-exec: ARCH_PLUGIN_DIR is not set (run through bin/arch-acp)\n")
  process.exit(2)
}
const claude = process.env.ARCH_CLAUDE_BIN || "claude"
const args = ["--plugin-dir", plugin, "--agent", "arch:orchestrator", ...process.argv.slice(2)]
const child = spawn(claude, args, { stdio: "inherit" })
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) process.on(sig, () => child.kill(sig))
child.on("error", (err) => {
  process.stderr.write(`claude-plugin-exec: cannot start ${claude}: ${err.message}\n`)
  process.exit(127)
})
child.on("exit", (code, sig) => process.exit(code ?? (sig ? 1 : 0)))
