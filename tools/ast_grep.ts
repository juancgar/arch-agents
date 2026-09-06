import { tool } from "@opencode-ai/plugin"
import path from "path"

const LANGUAGES = new Set([
  "python",
  "javascript",
  "typescript",
  "tsx",
  "jsx",
  "rust",
  "go",
  "java",
  "cpp",
  "c",
  "csharp",
  "ruby",
  "swift",
  "kotlin",
])

export default tool({
  description:
    "Read-only structural code search using ast-grep. Returns concise file, line, and code previews. Prefer this over text grep for syntax patterns, functions, calls, classes, and refactoring targets.",

  args: {
    pattern: tool.schema
      .string()
      .describe("Structural ast-grep pattern"),

    language: tool.schema
      .string()
      .describe("Programming language"),

    path: tool.schema
      .string()
      .optional()
      .describe("Path inside the current project. Defaults to project root."),
  },

  async execute(args, context) {
    if (!LANGUAGES.has(args.language)) {
      return `Unsupported language: ${args.language}`
    }

    const root = path.resolve(context.directory)
    const target = path.resolve(root, args.path ?? ".")
    const relative = path.relative(root, target)

    if (relative.startsWith("..") || path.isAbsolute(relative)) {
      return "Rejected: path must stay inside the current project."
    }

    const process = Bun.spawn(
      [
        "ast-grep",
        "run",
        "--lang",
        args.language,
        "--pattern",
        args.pattern,
        "--json",
        target,
      ],
      {
        cwd: root,
        stdout: "pipe",
        stderr: "pipe",
      },
    )

    const stdout = await new Response(process.stdout).text()
    const stderr = await new Response(process.stderr).text()
    const exitCode = await process.exited

    if (!stdout.trim()) {
      if (stderr.trim() && exitCode !== 0) {
        return `ast-grep error: ${stderr.trim()}`
      }
      return "No structural matches."
    }

    try {
      const matches = JSON.parse(stdout)

      if (!Array.isArray(matches) || matches.length === 0) {
        return "No structural matches."
      }

      const results = matches.slice(0, 100).map((match: any) => {
        const file = match.file ?? "unknown"
        const line = (match.range?.start?.line ?? 0) + 1
        const column = (match.range?.start?.column ?? 0) + 1

        const preview = String(match.text ?? "")
          .trim()
          .split("\n")[0]
          .trim()
          .slice(0, 180)

        return `${file}:${line}:${column}\n  ${preview}`
      })

      const truncated =
        matches.length > 100
          ? `\n\nShowing first 100 of ${matches.length} matches.`
          : ""

      return `Found ${matches.length} structural match${matches.length === 1 ? "" : "es"}:\n\n${results.join("\n\n")}${truncated}`
    } catch {
      return `ast-grep returned unexpected output:\n${stdout.slice(0, 10000)}`
    }
  },
})
