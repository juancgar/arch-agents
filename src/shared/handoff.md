---
name: handoff
---
## Report format

End with this report (it is what the orchestrator sees; keep it under ~1,500 tokens, put long material in files and reference them):

```
## Result
<the answer / outcome in a few lines>

## Evidence
<commands + key output, file:line references, or sources with IDs and passages>

## Changes
<files created or modified, or "none">

## Open issues
<risks, unverified points, follow-ups, or "none">

## Confidence
<high | medium | low> — <one line on why>
```

## Turn budget

Keep track of the turns you have left. When about 5 remain, or the work can't be finished, stop and deliver the report anyway: what's done, what's left, the evidence so far, marked **PARTIAL** at the top of `## Result`. Always deliver it through SubagentHandback; never end on a tool call.
