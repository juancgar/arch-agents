import { tool } from "@opencode-ai/plugin"

const HOME = process.env.HOME!
const PROJECT = `${HOME}/AI-Workspace/system/research-tools`
const PYTHON = `${PROJECT}/.venv/bin/python`
const READER = `${PROJECT}/pdf_reader.py`

async function run(args: string[]) {
  const p = Bun.spawn([PYTHON, READER, ...args], {
    stdout: "pipe",
    stderr: "pipe",
  })

  const stdout = await new Response(p.stdout).text()
  const stderr = await new Response(p.stderr).text()
  const code = await p.exited

  if (code !== 0) {
    throw new Error(stderr || stdout || `PDF reader exited ${code}`)
  }

  return stdout.trim()
}

export const info = tool({
  description:
    "Inspect metadata and page count of a PDF located in research/papers/inbox.",
  args: {
    file: tool.schema.string().describe(
      "PDF filename or path inside research/papers/inbox"
    ),
  },
  async execute(args) {
    return run(["info", args.file])
  },
})

export const read = tool({
  description:
    "Read text from a bounded page range of a PDF in research/papers/inbox.",
  args: {
    file: tool.schema.string(),
    start_page: tool.schema.number().int().min(1).default(1),
    end_page: tool.schema.number().int().min(1).optional(),
  },
  async execute(args) {
    const cmd = [
      "read",
      args.file,
      "--start-page",
      String(args.start_page),
    ]

    if (args.end_page) {
      cmd.push("--end-page", String(args.end_page))
    }

    return run(cmd)
  },
})
