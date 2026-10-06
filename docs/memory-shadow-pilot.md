# Phase 2A shadow pilot

This increment evaluates memory candidates without changing retrievable memory.
The implementation spans this configuration and the separately installed
`memory-service`; deploy both working copies together. No new agent is required.

## Using the workflow

Start a fresh OpenCode session in the target project and select `orchestrator`.
After a completed coding task, it calls `memory_propose` with zero or one candidate.
For a candidate, `memory-manager` calls `memory_inspect` and then `memory_decide`.
For a trivial task or one without a durable lesson, the proposal carries
`candidate: null` and a skip reason. That records the denominator without searching
memory or delegating to the manager.

Eligible candidates come from tested fixes or completed investigations with
claim-specific evidence. Speculative designs, merely accepted plans, temporary
task state, raw logs, and obvious source-code restatements do not qualify.
Fixes require reported independent tester evidence. The service checks the
structure and references; the pilot must evaluate semantic truth and usefulness.

The tools derive the repository root, session/message origin, current Git commit,
and dirty-worktree state from OpenCode context. They do not infer repository
identity from the memory service's working directory. For a canonical ID differing
from the root basename, put exactly one declaration in root `AGENTS.md`:

```text
memory_project: canonical-project-id
```

The optional `project_reference` tool argument supports the same declaration in
another repository guidance file. References must remain inside the repository.

## Decision contract

| Recommendation | Meaning |
| --- | --- |
| `NOOP` | No useful addition, equivalent claim without new evidence, or uncertainty |
| `ADD` | New supported durable claim without an equivalent stored memory |
| `UPDATE` | Additional evidence for an equivalent claim; identity and claim text stay intact |
| `SUPERSEDE` | Changed claim replacing a named active memory, with historical meaning preserved |

The journal retains the manager's recommendation separately from the service's
validated operation and reason codes. A rejected `ADD` remains visible as that
recommendation even when the effective operation is `NOOP`. All results contain
`mode: "shadow"` and `applied: false`. There is no apply tool, live-mode switch, or
automatic activation threshold.

Exact comparison normalizes whitespace within a project and ignores source.
Semantic comparisons use the existing hybrid search. Similarity alone cannot
establish equivalence or contradiction. Legacy memories remain visible but are
not migrated; missing type/status prevents targeting them with `UPDATE` or
`SUPERSEDE` until reviewed. Store failures are explicit errors, not inferred adds.

Evidence references support `file:relative/path`, `git:commit:relative/path`, and
`session:sessionID/messageID/partID`. Files are checked within the repository and
hashed at inspection; Git objects must resolve. Session content and outcomes are
reported, not authenticated. Neither a resolved reference nor a Git commit proves
that the claim follows from the evidence. Do not invent IDs or verifier roles.

Candidate retries reuse the same task ID and payload; a conflicting submission
for the same task is rejected. Completed decisions are immutable. Repeated shadow
proposals are flagged separately and do not become stored facts. To test behavior
after a hypothetical prior write, the tests seed an independent memory snapshot.

## Reviewing the pilot

The journal defaults to `$XDG_STATE_HOME/memory-service/candidates.sqlite3`, or
`~/.local/state/memory-service/candidates.sqlite3`. `MEMORY_JOURNAL_PATH` selects
a separate journal for experiments. It is never searched as long-term memory.

Review the first 20 completed coding tasks, including no-candidate tasks:

```bash
memory pilot-report --json > pilot-report.json
memory candidates --project my-project --json > project-candidates.json
```

The report includes the original claims/evidence, comparisons, recommendations,
validation reasons, task denominator, duplicate proposals, errors, labels, and
timings. Service processing timings exclude process startup; candidate-to-decision
time also includes orchestration and waiting. They are not a measured comparison
against a no-memory workflow. Interruptions remain visible as unfinished candidates
or recorded errors rather than completed decisions.

Manually label every recommended `ADD`, `UPDATE`, and `SUPERSEDE`, including
recommendations rejected by the gate. Create a label JSON file containing:

```json
{
  "reviewer": "your-name",
  "expected_operation": "NOOP",
  "supported": false,
  "comment": "The test covers reconnect timing, but does not establish the broader claim."
}
```

```bash
memory pilot-label CANDIDATE_ID --json < label.json
memory pilot-report --json > pilot-report.json
```

Labels are manual CLI operations; agents have no labeling tool. `review_ready`
means the report has 20 completed task observations, decisions for their candidates,
and labels for every positive recommendation. It does not mean memory quality is
acceptable and never enables writes. The report informs the next writer design.
The automated 20-task report test uses synthetic fixtures in a temporary journal;
it is not the live pilot and does not supply human labels for real work.

## Write pause and boundaries

`memory_remember` and `memory_forget` reject calls for every collection before
starting a subprocess. Role checks restrict proposing to the Orchestrator and
inspection/decisions to the Memory Manager. Research document creation and existing
memory retrieval continue, while automatic research-memory inserts pause.

The standalone CLI retains explicit manual `remember`, `forget`, `search`, and
`stats` behavior. Agents are instructed not to use it or another agent to bypass
the write pause. Restoring automatic writes requires a separately implemented
writer with fresh candidate validation; changing a prompt cannot activate one.

Working-memory lifecycle, stale-memory mutation, graph storage, learned policies,
and agent-topology changes are outside this increment.
