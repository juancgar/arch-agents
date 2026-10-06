# arch-agents v2: quick user guide

## 1. Start a session

```bash
cd ~/my-project
aa                 # default plan (daily: Opus 5.5 brain) in the current folder
aa max             # hardest problems (Fable 5.1 brain; uses your limits fastest)
aa saver           # long sessions, stretches your Claude limits
aa offline         # local models only: free, private, no internet (OpenCode)
aa local           # Claude Code on local models (experimental)
aa plans           # list the plans
```

`aa` is the short name; `arch-agents` works too. (`arch` is a built-in Linux command, so it isn't used.)

**One-shot** (no interactive session): `aa daily -p "explain how the cache layer works"`

## 2. Which plan should I use?

| Situation | Plan |
|---|---|
| Normal coding and research work | `daily` |
| A hard bug, an architecture decision, an important proposal | `max` |
| Long session, or you're near your Claude usage limit | `saver` |
| No internet, private data, or you want zero cost | `offline` |

Claude plans use your **Claude subscription**. Local plans use the GPU, so close GPU notebooks first.

## 3. How to ask

Just describe what you want, in any language. The orchestrator picks the workflow, judges the size of the task, and tells you what it verified.

- *"The login page crashes since yesterday's deploy, find out why and fix it"* → debug
- *"Add CSV export to the reports page"* → implement (tests first, then code, then review)
- *"Should we move to Docker? Just analyze"* → architecture (nothing gets changed)
- *"Is my idea new: …"* → novelty check, answered with a table of the closest existing papers

**Tips:**
- **Say what "done" means** ("all tests pass", "works with the existing login"). It becomes the acceptance criteria.
- **"Analyze only" / "don't change anything"** is respected strictly: no file gets edited.
- **If it asks you a question,** it's because your answer changes the plan. It asks once, at the start.

## 4. Workflows you can call directly

In Claude Code type `/arch:<name> …`; in OpenCode, `/<name> …`.

| Coding | What it does |
|---|---|
| `quick-fix` | Small, obvious change, plus a quick check |
| `debug` | Reproduce → root cause → fix → tests (max 3 fix attempts, then a fresh look) |
| `implement` | Spec → plan → tests first → code → checks → review. Add `--hard` for 3 competing attempts picked by tests |
| `refactor` | Restructure without changing behaviour (behaviour is pinned by tests first) |
| `architecture-change` | Options, trade-offs and a recommendation; code only if you ask |
| `code-review` | Evidence-based review: APPROVE / CHANGES REQUIRED |
| `verify` | Run tests, lint and types; report only |
| `explain` · `document` · `repo-map` | Explain code · update docs · map the repository |

| Research | What it does |
|---|---|
| `research-discovery` | Find papers: library first, then arXiv, OpenReview and the web |
| `paper-analyze` | Deep read of one paper → a saved note |
| `paper-compare` | Compare 2–5 analysed papers |
| `literature-review` | Thematic review from your analysed papers |
| `novelty-check` | Closest prior work per facet: retain / narrow / abandon |
| `research-proposal` | Proposal with a falsifiable hypothesis, reviewed and novelty-checked |
| `research-cycle` | Full investigation, saved to ResearchHub |
| `full-cycle` | Research, then a tested prototype |

## 5. What you get back

Every answer ends with:
- **what was verified, and how** (tests run, citations checked);
- **what was not verified**;
- **confidence** (high / medium / low);
- **open issues**;
- **paths of saved files**.

Research citations are checked to exist before they reach you.

**Where research files go:**

| Kind | Folder |
|---|---|
| Paper notes, reviews, comparisons, proposals | `~/AI-Workspace/research/…` |
| Syntheses, reports, ideas | `~/ResearchHub/…` |

## 6. The local model server

Runs as a background service and needs nothing from you:
- **Models load on demand,** one at a time (about 10 s to switch).
- **They unload after 10 idle minutes,** which frees the GPU.

| Task | Command |
|---|---|
| Status | `systemctl --user status llm-server` |
| Stop it (before heavy GPU training) | `systemctl --user stop llm-server` |
| Start it again | `systemctl --user start llm-server` |
| Browser chat | `http://omen:8080` (key: `cat ~/.config/llama-server/api-key`) |

## 7. Working from your Mac

1. **Tailscale on:** check the menu bar says Connected.
2. **Terminal:** `ssh juanki@omen`, then `aa daily ~/workspace/me/<project>`.
3. **Zed:** *projects: open remote* → `juanki@omen`, then run `aa` in its terminal.
4. **Notebooks:** `http://omen:8888`.
5. **Omen asleep?**
   - At home: `omen-wake`.
   - Away: ASUS Router app → Wake on LAN.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `CUDA out of memory` | `nvidia-smi` to see who uses the GPU; `ollama stop <model>`; close notebook kernels |
| Local plan very slow or not answering | `systemctl --user restart llm-server` |
| "aa: not built yet" | `aa build` |
| A Claude plan says you're not logged in | run `claude` once and log in |
| Answer seems wrong | ask *"show me the evidence for that"*, or rerun with `aa max` |

## 9. Changing the agents

Edit `src/agents/*.md`, `src/workflows/*.md` or `src/plans.yaml` (models per plan), then run `aa build`. Never edit `build/`; it gets overwritten. The design rationale is in [architecture-v2.md](architecture-v2.md).
