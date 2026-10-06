# arch-agents redesign: what the evidence supports (survey, Oct 2026)

**Method.** Every citation was checked on 2026-10-06 against its arXiv abstract page (or the official post, docs page or Crossref record). Numbers come from the paper or post. The body is ~3,400 words; the reference list is an appendix.

**Legend.** Grades: **A** = replicated across groups and models; **B** = consistent but limited (few studies, or mostly math/QA); **C** = a single study or a vendor report. Tiers: **F** = Fable 5.1 / Opus 5.5, **S** = Sonnet 5.5, **H** = Haiku 4.5, **L** = local models (Qwen3.6, KAT-Coder, Laguna-XS, MiroThinker).

## Bottom line

1. **The most reliable accuracy lever is checking work against signals outside the model** (tests, execution, retrieved sources). A model critiquing its own output without new information rarely fixes reasoning.
2. **With thinking models, delete "think step by step" prompts, few-shot reasoning demos and personas.** Control depth with `effort` or the thinking mode, set per role and per difficulty. More thinking is not always better.
3. **Use multiple agents for parallel, read-heavy breadth and for clean-context review.** Don't use them for debate or for uncoordinated parallel code writing. Voting over independent samples captures most of what debate gains.
4. **Research outputs need grounding at the level of individual claims, and the ability to abstain.** LLM novelty judgments and LLM review scores are low-precision.
5. **Keep contexts lean.** Store in memory only what has been verified, because agents copy past experience, mistakes included.

## 1. Reasoning

**Prompted CoT family:** CoT [1], zero-shot CoT [2], Plan-and-Solve [3], least-to-most [4], self-consistency [5], ToT [6], GoT [7].

*Evidence (A, for 2022–24 non-reasoning models):* large gains on multi-step math and symbolic tasks. Self-consistency added +17.9 pts on GSM8K; ToT took Game of 24 from 4% to 74%.

*Caveats:*
- A meta-analysis of 100+ papers found the gains concentrate in math and logic; on MMLU, CoT ≈ answering directly [8].
- CoT can cost up to 36 pts on tasks where deliberating also hurts humans [9].
- ToT and GoT were demonstrated on puzzles, at many calls per problem. I found no evidence they beat native reasoning models on SE or research tasks.

*Apply:* don't build ToT/GoT controllers. Keep decomposition structural: the planner emits a task graph with acceptance tests.

**Prompting native reasoning models.**

*Evidence (B+: consistent across groups, but few tests on Claude):*
- "Step by step" prompts gave +2.9 pts (o3-mini), +3.1 (o4-mini) and −3.3 (Gemini 2.5 Flash) on GPQA, at 20–80% more latency [10].
- Older prompt-engineering techniques help less, or hurt, on o1 [11]. Few-shot prompting hinders o1 [12], and DeepSeek-R1's authors report it "consistently degrades" performance [13].
- Even optimal reasoning traces used as demos lower accuracy, because models copy their steps [14].
- Expert personas don't improve accuracy [15, 16].
- Anthropic's docs make `effort` the primary control of thinking depth [17, 18].

*Contradicting evidence:* CoT prompts helped small (1.5–32B) open reasoning models on math [19].

*Apply (lowers token cost):*
- Strip CoT incantations, scratchpad tags, reasoning demos and personas from all 14 specialist prompts.
- Keep the goal, constraints, acceptance criteria, output schema, verification steps and examples of the output format.
- For Qwen3.6, use the think/no-think switch and thinking budget [20], not prose. Note that hybrid models leak reasoning into no-think mode [21].

**Test-time compute and difficulty.**

*Evidence (A that more thinking is non-monotonic; B on effect sizes):*
- Allocating compute per prompt beats best-of-N by more than 4× in efficiency [22]. Learned allocation saves up to 50% of compute [23].
- More thinking can hurt: overthinking on easy items [24], distraction with longer reasoning [25], and standard models beating reasoning models on low-complexity puzzles (a contested setup) [26, 27].
- None of 33 models thinks optimally [28].
- On closed-book factual QA, more thinking often increases hallucination [29].
- In agentic software-engineering runs, picking the less-overthinking trajectory gained ~30% at 43% lower cost [30].
- Models fail to ration a shared budget across questions [31], so allocation belongs to the orchestrator.

*Apply:* the orchestrator sets effort per call.
- Routing, extraction, citation checks: low.
- Coder and debugger: medium, escalating on test failure.
- Architect, proposal design, novelty checks: high.
- xhigh only where evals show a gain.

**Parallel vs sequential compute.**
- At equal budget, voting over parallel samples beat extended thinking by up to 20% [32]. Contrary results favour sequential refinement [33].
- Coverage (at least one sample correct) on SWE-bench Lite rose from 15.9% to 56% with 250 samples. Only a verifier can capture that gain; majority voting and reward models plateau [34].

*Apply:* spend k parallel attempts only where a verifier exists; otherwise make one attempt at higher effort.

**Reasoning traces are weak audit evidence (B).** Reasoning models often disclose that they used a hint less than 20% of the time [35]. The Claude API returns only a summary of the thinking. Reviewers should judge artifacts and evidence, not the producer's reasoning.

## 2. Self-correction and review

**Intrinsic self-correction mostly fails (A).**
- Without external feedback, LLMs often fail to fix their reasoning, and sometimes make it worse [36].
- GPT-4's self-critique collapsed on planning tasks, while a sound external verifier helped substantially [37].
- Models can't locate their own reasoning errors, but they can fix them once the location is given [38].
- A critical survey found no success with prompted-LLM feedback outside unusually suitable tasks; reliable external feedback does work [39].
- Code self-repair gains are modest once cost is counted, and are limited by the quality of the feedback [40].
- Self-Refine's ~20% average gains [41] come mainly from open-ended generation tasks.
- Anthropic saw generators "confidently praising" mediocre work and added a separate skeptical evaluator. On tasks within the model's solo ability, that evaluator was overhead [42].

**Critique that works uses tools** (A for code, B for QA):
- CRITIC [43].
- Self-Debug with execution feedback [44].
- Reflexion: 91% on HumanEval using test feedback [45].
- Chain-of-Verification, which answers verification questions independently of the draft [46].

**Verifiers (B; mostly math).**
- Process supervision beat outcome supervision on MATH [47], but outcome supervision matched final-answer error rates on GSM8K [48].
- Process reward models (PRMs) tolerate flawed steps [49].
- At a fixed budget, self-consistency beats generative verifiers, which need up to 8× the compute to match it [50].
- Frontier models are weak verifiers out of the box, but comparing candidates side by side helps [51]. For free-form answers, pick the most consistent candidate [52].

**Biases of LLM judges (A; the mitigations are B).**
- Swapping answer order flipped 66/80 verdicts [53]; position bias peaks when candidates are close [54].
- Judges favour longer answers [55, 56] and their own outputs [57].
- Judges are near chance on hard, objective pairs [58].
- Generated yes/no checklists raised exact agreement with humans from 46.4% to 52.2% [59].
- Industrial LLM code review: in one deployment 73.8% of comments were resolved, but PRs took longer to close [60]; in another, only 7–8% of comments were accepted [61].

**Apply** (reviewer, tester, paper-comparator):
1. Drop same-model "review your answer" passes. Review only with new evidence: test, lint or type output, sources, or a clean-context reviewer from a different model family.
2. Every finding must cite its evidence; drop the rest.
3. Grade against a pass/fail checklist derived from the spec, not a 1–10 score.
4. In pairwise comparisons, judge both orders and keep only consistent verdicts.
5. Allow at most 1–2 revision rounds unless a new external signal arrives.

Cost: one cheap call (H/L) for the checklist; fewer producer re-runs.

## 3. Multi-agent design

**Debate is not a default (A).**
- Debate doesn't reliably beat self-consistency [62]. A single well-prompted agent matches the best discussion setup [63].
- Debate often loses to CoT or self-consistency despite using more compute [64]. Majority voting explains most of its gains [65].
- Agents abandon correct answers to agree with peers [66].
- Exceptions: heterogeneous models help [64]; debate helps a *weaker judge* (76% vs 48%) [67]; one equal-compute study of non-reasoning models found +1.3 pts [68].

**Voting and mixtures (B).**
- Accuracy scales with the number of sampled agents, more so on hard tasks [69].
- Mixture-of-Agents beat GPT-4o on AlpacaEval [70]. But aggregating samples from the single best model beats mixing models (+6.6 pts) [71].

*Apply:* replace debate with independent samples plus vote or selection. For high-stakes designs, aggregate 3–5 samples from the best model; don't mix in weaker local models.

**When teams help or hurt (B).**
- A controlled study of 260 configurations found −70% to +81% versus a single agent. Returns turned negative once the single agent exceeded ~45%. Independent agents amplified errors 17.2× vs 4.4× under a central coordinator. Strong orchestrators with weaker subagents underperformed all-strong teams [72].
- With thinking tokens matched, single agents match or beat multi-agent systems on multi-hop QA [73]. One model playing all roles matches same-model workflows more cheaply [74].
- Anthropic's research system (an orchestrator with parallel subagents) beat a single agent by 90.2%. It used ~15× chat tokens, and token usage explained 80% of the variance. Anthropic calls most coding a poor fit [75].
- Cognition's 2026 verdict: writes stay single-threaded, and extra agents contribute intelligence such as clean-context review. Parallel writers fail [76, 77].
- Parallel coding can work with a central planner, isolated git worktrees and test-gated merges [78].
- Failure taxonomy: 14 modes across system design, misalignment between agents, and task verification [79].
- Anthropic's guidance: start with the simplest workflow pattern (chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer) and add agency only when needed [80].

*Apply:*
- One orchestrator (F) owns decisions and final verification.
- Fan out parallel workers only for read-heavy breadth. Each returns a cited summary of 1–2K tokens [81].
- Code has one writer. Workers can be one tier down, as with Anthropic's Sonnet workers under Opus, but not much weaker [72, 75].
- Log full traces and tag failures by taxonomy.

Cost: multi-agent runs use ~15× chat tokens, so reserve fan-out for breadth that justifies it.

## 4. Coding agents

**Simple scaffolds suffice (B).**
- A purpose-built agent-computer interface raised resolve rates [82]. A fixed localize → repair → validate pipeline was competitive (32% on SWE-bench Lite) at ~$0.70 per issue [83].
- A ~100-line bash-only agent reports >74% on SWE-bench Verified [84]. One paper argues the gap between simple and complex scaffolds shrinks as models improve [85]. Still, a scaffold that adapts to issue quality added 3.6–8.4% [86].
- AGENTS.md-style context files didn't raise success rates and cost 20% more [87].

**Tests are the verifier (A).**
- Generated tests: +18.8 pts pass@1 [88]. A test-centred flow went from 19% to 44% [89].
- Reproduction tests doubled the precision of patch filtering [90]. Issue-derived tests raised precision from 60.8% to 91.9% at 33% recall [91].
- Test voting across parallel trajectories reached 57.4% on SWE-bench Verified [92].
- A separate test designer helps [93]. Tests written while viewing buggy code catch 24–47% fewer bugs [94].
- The ad-hoc tests agents write during a run add little [95].

**Bounded debugging (B).**
- Most models lose 60–80% of their debugging effectiveness within 2–3 attempts [96].
- A fresh restart, with the old diff available, raised Qwen3.6-27B from 66.6% to 71.8% [97].

**"Passing" ≠ correct (A).**
- 7.8% of "resolved" SWE-bench patches fail the developers' tests, and 29.6% behave differently from the reference fix [98].
- Maintainers would reject about half of the test-passing agent PRs [99].

**Ask when the task is underspecified (B).** Interaction improved results by up to 74%, but models rarely detect underspecification on their own [100].

*Apply:*
1. Clarify → localize (H/L).
2. The tester writes failing reproduction tests from the spec, blind to the coder's code.
3. The coder patches, then runs the reproduction tests, the full regression suite, lint and types.
4. A clean-context reviewer reads the diff and the test log.
5. Allow ≤3 debug rounds, then restart fresh with a summary of the failure.
6. Only on hard issues: generate 3–5 candidates (local coders are cheap) and select by tests, then by pairwise review.

Cost: test runtime, plus k× generation only on hard issues, mostly on L models. Keep CLAUDE.md/AGENTS.md to non-obvious conventions. Build an internal eval of 20–50 tasks from real failures [101].

## 5. Research agents

**Plan the questions first (B).** Asking questions from several perspectives and writing the outline first improved organization by 25% and coverage by 10% [102].

**Retrieval-grounded synthesis (B).**
- GPT-4o hallucinated citations 78–90% of the time. OpenScholar's retrieval plus self-feedback loop reached expert-level citation accuracy [103]. PaperQA2 matched experts [104].
- Adaptive and corrective retrieval: Self-RAG [105], CRAG [106].

**Citations are often wrong (A).**
- Only 51.5% of generative-search sentences were fully supported [107]. Deep-research agents' citation accuracy runs 40–80% [108].
- 3–13% of cited URLs never existed; a liveness check cut dead links to under 1% [109].
- Up to 57% of citations were post-rationalized: they look correct, but the model didn't actually use the source [110].

**Check atomic claims (A).**
- FActScore: only 58% of ChatGPT's facts were supported, and its automated estimate errs by under 2% [111].
- Search-augmented checking won 76% of its disagreements with crowdsourced annotators, at 20× lower cost [112].
- An 8B model reproduces VeriScore 6.6× faster (system-level r=0.94) [113, 114].

**Novelty and ideas (B).**
- LLM ideas were rated more novel than experts' (p<0.05) [115], but their scores fell more once the ideas were executed [116].
- 24% of LLM-generated research documents were paraphrased from, or heavily borrowed, existing work [117].
- The AI Scientist (v1/v2) labelled established ideas as novel [118, 119, 120]. LLM novelty judgments diverge from experts' [121].
- Facet-based retrieve-then-rerank improved agreement by ~13% [122].
- At finding serious errors in papers, LLMs reach ≤21% recall and ≤6% precision [123].

**LLM reviewers (B).**
- GPT-4's comments overlap with human reviewers' about as much as two humans overlap [124].
- LLM reviews are manipulable through hidden text [125] and through LLM rewriting of the paper [126].

**MiroThinker (C).** Trained for up to 600 tool calls [127]; H1 adds step-level and trajectory-level verification [128]. I found no published evaluation of its citation faithfulness.

*Apply:*
1. The researcher plans perspectives and questions.
2. Parallel retrieval workers search the library and the web; results are reranked.
3. The synthesizer cites passage spans (Claude's document citations return exact spans).
4. Deterministic DOI/URL checks.
5. A claim-checker (H/L) checks each atomic claim against its cited span, then removes or flags unsupported ones.

Novelty-checker: retrieve per facet (problem, method, data, claim) and output a table of the closest prior work with differences, or "novelty unclear". Never output a bare score. Paper-analyst: strip hidden text from PDFs, and treat LLM reviews as feedback, never as scores. Cost: about one H/L call per ~10 claims, plus retrieval.

## 6. Memory and context

**Long contexts degrade (A).**
- Models miss what sits mid-context [129]. At 32K tokens, 11 of 13 models fell below half of their short-context score [130].
- Length alone cut accuracy by 13.9–85%, even with perfect retrieval [131]. In Chroma's tests (18 models), focused ~300-token prompts beat ~113K-token ones [132].
- Irrelevant context shortens reasoning by up to 74% and reduces self-checking [133].
- Adding more retrieved passages helps, then hurts [134].
- Masking old tool observations halves cost and matches LLM summarization [135].

**Memory errors propagate (B).**
- Agents copy retrieved experiences, so stored errors compound [136]. Memory systems accumulate hallucinations during extraction and updates [137].
- On MemoryAgentBench (GPT-4o-mini backbone), plain BM25 retrieval (41.5) beat Mem0 (21.1), Zep (24.0) and MemGPT (28.3) [138].
- Rewriting memory wholesale causes "context collapse"; curated, incremental playbooks gained 10.6% [139].
- MemGPT [140], reflection in Generative Agents [141], A-MEM [142] and Mem0 [143] were evaluated mainly on conversational memory or social simulation, not on task-solving agents.

**Retrieval (A/B).**
- BM25 is a strong baseline, and rerankers score best [144]. Single-vector embeddings have hard limits, which favours hybrid retrieval [145].
- Contextual chunks plus hybrid retrieval cut retrieval failures by 49%; adding reranking brings that to 67% [146].
- Qwen3 rerankers add 4–8 pts on MTEB-R [147]. Reranking too many documents degrades results [148], and reasoning rerankers do worse than plain ones [149].

*Apply:*
- Give each call a context budget and hand subagents complete, lean specs.
- For long tasks, use observation masking, compaction and NOTES files [81, 150].
- Write to memory only verified outcomes, with provenance. Store failures as lessons and prune regularly.
- Retrieval pipeline: BM25 + dense with contextual chunks → Qwen3 reranker with thinking off, on the top ~50 → 5–10 chunks.

## 7. Routing and cost

**Evidence (B).**
- Cascades and routers cut cost at equal quality: up to 98% [151], more than 2× [152], or 40% fewer large-model calls [153].
- Adaptive sampling stops once samples agree, using up to 7.9× fewer samples [154].
- Confidence-weighted voting saves 40% [155]. DeepConf saves up to 84.7% of tokens, but needs logprobs, so it applies only to the local models [156].
- Anthropic recommends `low` effort for subagents and sweeping effort per route [17].

*Caveats:* router studies are mostly chat and QA. Cascades need a trustworthy failure signal, and verbalized confidence is overconfident [157].

*Apply:*
- A cheap intake classifier (H, or Qwen with thinking off) maps task type × difficulty to a model and effort level.
- Escalate on external failure: failing tests, a failed claim check, or disagreement among samples.
- Hold effort constant per conversation, or use per-message effort, to keep the prompt cache.

## 8. Uncertainty, abstention, clarification

**Calibration (B).**
- Models "mostly know what they know" [158]. Reasoning models are better calibrated [159], but reasoning fine-tuning degrades abstention by 24% [160] and RL fine-tuning cut refusals on unanswerable problems by over 80% [161].
- With insufficient context, strong models answer wrongly instead of abstaining [162].
- Grading that rewards guessing sustains hallucination. Stating explicit confidence targets helps: "answer only if >t confident; errors cost t/(1−t)" [163].
- Sampling consistency flags hallucinations [164].

**Clarification (B).**
- Performance drops 39% when requirements arrive across turns: models assume early and never recover [165].
- Clarifying the goal loses its value after ~10% of execution, and asking after the midpoint is worse than not asking at all [166].

*Apply:*
- At intake, check inputs, acceptance criteria and constraints. Ask batched questions only when the answer would change the plan; otherwise record assumptions.
- When a session drifts, consolidate the spec and restart.
- Researcher and reviewer prompts get a confidence target and an "insufficient evidence" option.

## Ranked changes: likely accuracy gain per unit cost

| # | Change | Extra cost | Tiers | Evidence |
|---|---|---|---|---|
| 1 | Gate all review on external evidence; remove same-model self-review loops | lower | all | [36, 37, 39, 42] |
| 2 | Spec-first, test-gated coding: blind reproduction tests, full regression, ≤3 debug rounds, then a fresh restart | test runtime | F/S coder, S tester | [90, 91, 94, 96, 97] |
| 3 | Claim-level grounding: URL/DOI checks, span entailment, "insufficient evidence" | ~1 cheap call per 10 claims | H/L | [108, 109, 111, 162] |
| 4 | Clarification gate; complete specs to subagents; restart on drift | +1 turn | F | [100, 165, 166] |
| 5 | Prompt cleanup: no CoT, few-shot or persona scaffolds; lean context files | negative | all | [10, 13, 14, 16, 87] |
| 6 | Orchestrator assigns model and effort by role and difficulty; escalate on verifier failure | negative | F/S/H | [22, 23, 30, 31] |
| 7 | Subagents only for read-heavy breadth; single writer; clean-context reviewer; central verification | ± (multi-agent ≈15× tokens) | F orchestrator, S/L workers | [72, 73, 75, 77] |
| 8 | Context hygiene: lean contexts, observation masking, notes files | negative | all | [131, 132, 133, 135] |
| 9 | Hybrid retrieval with contextual chunks and a local reranker (thinking off), small k; facet retrieval for novelty | low (local) | L | [122, 145, 146, 149] |
| 10 | Sample-and-select instead of debate or MoA, on hard or high-stakes items only | k× on those items | L code, F design | [64, 65, 71, 92] |
| 11 | Judge-bias controls: spec checklists, both orders, cross-family judge, pass/fail | +1 cheap call | H/L/S | [53, 57, 58, 59] |
| 12 | Verified-only memory with provenance; plain retrieval over memory frameworks; full-trace logging and an internal eval | low | — | [79, 101, 136, 138] |

**Deprioritize** (benefits faded with reasoning models, or evidence is weak):
- ToT/GoT controllers.
- Multi-agent debate.
- Mixture-of-agents with weaker models.
- PRMs.
- Persona prompts.
- Long self-reflection loops.
- Heavyweight memory frameworks.
- Treating LLM novelty or review scores as decisions.
- Repository-overview context files.
- Defaulting to maximum effort.

## References (all verified 2026-10-06)

1. Wei et al. (2022). *Chain-of-Thought Prompting Elicits Reasoning in Large Language Models*. arXiv:2201.11903
2. Kojima et al. (2022). *Large Language Models are Zero-Shot Reasoners*. arXiv:2205.11916
3. Wang et al. (2023). *Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models*. arXiv:2305.04091
4. Zhou et al. (2022). *Least-to-Most Prompting Enables Complex Reasoning in Large Language Models*. arXiv:2205.10625
5. Wang et al. (2022). *Self-Consistency Improves Chain of Thought Reasoning in Language Models*. arXiv:2203.11171
6. Yao et al. (2023). *Tree of Thoughts: Deliberate Problem Solving with Large Language Models*. arXiv:2305.10601
7. Besta et al. (2023). *Graph of Thoughts: Solving Elaborate Problems with Large Language Models*. arXiv:2308.09687
8. Sprague et al. (2024). *To CoT or not to CoT? Chain-of-thought helps mainly on math and symbolic reasoning*. arXiv:2409.12183
9. Liu et al. (2024). *Mind Your Step (by Step): Chain-of-Thought can Reduce Performance on Tasks where Thinking Makes Humans Worse*. arXiv:2410.21333
10. Meincke et al. (2025). *Prompting Science Report 2: The Decreasing Value of Chain of Thought in Prompting*. arXiv:2506.07142
11. Wang et al. (2024). *Do Advanced Language Models Eliminate the Need for Prompt Engineering in Software Engineering?*. arXiv:2411.02093
12. Nori et al. (2024). *From Medprompt to o1: Exploration of Run-Time Strategies for Medical Challenge Problems and Beyond*. arXiv:2411.03590
13. DeepSeek-AI (2025). *DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning*. arXiv:2501.12948
14. Wang et al. (2025). *From Harm to Help: Turning Reasoning In-Context Demos into Assets for Reasoning LMs*. arXiv:2509.23196
15. Zheng et al. (2023). *When "A Helpful Assistant" Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of Large Language Models*. arXiv:2311.10054
16. Basil et al. (2025). *Prompting Science Report 4: Playing Pretend: Expert Personas Don't Improve Factual Accuracy*. arXiv:2512.05858
17. Anthropic (2026). *Effort* (Claude API documentation). https://platform.claude.com/docs/en/build-with-claude/effort
18. Anthropic (2026). *Steering thinking* (Claude API documentation). https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost
19. Ge et al. (2025). *Innate Reasoning is Not Enough: In-Context Learning Enhances Reasoning Large Language Models with Less Overthinking*. arXiv:2503.19602
20. Yang et al. (2025). *Qwen3 Technical Report*. arXiv:2505.09388
21. Wang et al. (2025). *Demystifying Hybrid Thinking: Can LLMs Truly Switch Between Think and No-Think?*. arXiv:2510.12680
22. Snell et al. (2024). *Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters*. arXiv:2408.03314
23. Damani et al. (2024). *Learning How Hard to Think: Input-Adaptive Allocation of LM Computation*. arXiv:2410.04707
24. Chen et al. (2024). *Do NOT Think That Much for 2+3=? On the Overthinking of o1-Like LLMs*. arXiv:2412.21187
25. Gema et al. (2025). *Inverse Scaling in Test-Time Compute*. arXiv:2507.14417
26. Shojaee et al. (2025). *The Illusion of Thinking: Understanding the Strengths and Limitations of Reasoning Models via the Lens of Problem Complexity*. arXiv:2506.06941
27. Lawsen (2025). *Comment on The Illusion of Thinking: Understanding the Strengths and Limitations of Reasoning Models via the Lens of Problem Complexity*. arXiv:2506.09250
28. Aggarwal et al. (2025). *OptimalThinkingBench: Evaluating Over and Underthinking in LLMs*. arXiv:2508.13141
29. Zhao et al. (2025). *Test-Time Scaling in Reasoning Models Is Not Effective for Knowledge-Intensive Tasks Yet*. arXiv:2509.06861
30. Cuadron et al. (2025). *The Danger of Overthinking: Examining the Reasoning-Action Dilemma in Agentic Tasks*. arXiv:2502.08235
31. Fan et al. (2026). *Thinking Hard, Not Smart: Reasoning Models Fail to Ration Test-Time Compute Across Questions*. arXiv:2608.07968
32. Ghosal et al. (2025). *Does Thinking More always Help? Mirage of Test-Time Scaling in Reasoning Models*. arXiv:2506.04210
33. Sharma & Chopra (2025). *The Sequential Edge: Inverse-Entropy Voting Beats Parallel Self-Consistency at Matched Compute*. arXiv:2511.02309
34. Brown et al. (2024). *Large Language Monkeys: Scaling Inference Compute with Repeated Sampling*. arXiv:2407.21787
35. Chen et al. (2025). *Reasoning Models Don't Always Say What They Think*. arXiv:2505.05410
36. Huang et al. (2023). *Large Language Models Cannot Self-Correct Reasoning Yet*. arXiv:2310.01798
37. Stechly et al. (2024). *On the Self-Verification Limitations of Large Language Models on Reasoning and Planning Tasks*. arXiv:2402.08115
38. Tyen et al. (2023). *LLMs cannot find reasoning errors, but can correct them given the error location*. arXiv:2311.08516
39. Kamoi et al. (2024). *When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey of Self-Correction of LLMs*. arXiv:2406.01297
40. Olausson et al. (2023). *Is Self-Repair a Silver Bullet for Code Generation?*. arXiv:2306.09896
41. Madaan et al. (2023). *Self-Refine: Iterative Refinement with Self-Feedback*. arXiv:2303.17651
42. Rajasekaran, Anthropic (Mar 2026). *Harness design for long-running application development*. https://www.anthropic.com/engineering/harness-design-long-running-apps
43. Gou et al. (2023). *CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing*. arXiv:2305.11738
44. Chen et al. (2023). *Teaching Large Language Models to Self-Debug*. arXiv:2304.05128
45. Shinn et al. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning*. arXiv:2303.11366
46. Dhuliawala et al. (2023). *Chain-of-Verification Reduces Hallucination in Large Language Models*. arXiv:2309.11495
47. Lightman et al. (2023). *Let's Verify Step by Step*. arXiv:2305.20050
48. Uesato et al. (2022). *Solving math word problems with process- and outcome-based feedback*. arXiv:2211.14275
49. Zhang et al. (2025). *The Lessons of Developing Process Reward Models in Mathematical Reasoning*. arXiv:2501.07301
50. Singhi et al. (2025). *When To Solve, When To Verify: Compute-Optimal Problem Solving and Generative Verification for LLM Reasoning*. arXiv:2504.01005
51. Zhao et al. (2025). *Sample, Scrutinize and Scale: Effective Inference-Time Search by Scaling Verification*. arXiv:2502.01839
52. Chen et al. (2023). *Universal Self-Consistency for Large Language Model Generation*. arXiv:2311.17311
53. Wang et al. (2023). *Large Language Models are not Fair Evaluators*. arXiv:2305.17926
54. Shi et al. (2024). *Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge*. arXiv:2406.07791
55. Zheng et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. arXiv:2306.05685
56. Dubois et al. (2024). *Length-Controlled AlpacaEval: A Simple Way to Debias Automatic Evaluators*. arXiv:2404.04475
57. Panickssery et al. (2024). *LLM Evaluators Recognize and Favor Their Own Generations*. arXiv:2404.13076
58. Tan et al. (2024). *JudgeBench: A Benchmark for Evaluating LLM-based Judges*. arXiv:2410.12784
59. Cook et al. (2024). *TICKing All the Boxes: Generated Checklists Improve LLM Evaluation and Generation*. arXiv:2410.03608
60. Cihan et al. (2024). *Automated Code Review In Practice*. arXiv:2412.18531
61. Olewicki et al. (2024). *Impact of LLM-based Review Comment Generation in Practice: A Mixed Open-/Closed-source User Study*. arXiv:2411.07091
62. Smit et al. (2023). *Should we be going MAD? A Look at Multi-Agent Debate Strategies for LLMs*. arXiv:2311.17371
63. Wang et al. (2024). *Rethinking the Bounds of LLM Reasoning: Are Multi-Agent Discussions the Key?*. arXiv:2402.18272
64. Zhang et al. (2025). *Stop Overvaluing Multi-Agent Debate -- We Must Rethink Evaluation and Embrace Model Heterogeneity*. arXiv:2502.08788
65. Choi et al. (2025). *Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models?*. arXiv:2508.17536
66. Wynn et al. (2025). *Talk Isn't Always Cheap: Understanding Failure Modes in Multi-Agent Debate*. arXiv:2509.05396
67. Khan et al. (2024). *Debating with More Persuasive LLMs Leads to More Truthful Answers*. arXiv:2402.06782
68. Wunderlich et al. (2026). *Multi-Agent Reasoning Improves Compute Efficiency: Pareto-Optimal Test-Time Scaling*. arXiv:2605.01566
69. Li et al. (2024). *More Agents Is All You Need*. arXiv:2402.05120
70. Wang et al. (2024). *Mixture-of-Agents Enhances Large Language Model Capabilities*. arXiv:2406.04692
71. Li et al. (2025). *Rethinking Mixture-of-Agents: Is Mixing Different Large Language Models Beneficial?*. arXiv:2502.00674
72. Kim et al. (2025). *Towards a Science of Scaling Agent Systems*. arXiv:2512.08296
73. Tran & Kiela (2026). *Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets*. arXiv:2604.02460
74. Xu et al. (2026). *Rethinking the Value of Multi-Agent Workflow: A Strong Single Agent Baseline*. arXiv:2601.12307
75. Hadfield et al., Anthropic (Jun 2025). *How we built our multi-agent research system*. https://www.anthropic.com/engineering/multi-agent-research-system
76. Yan, Cognition (Jun 2025). *Don't Build Multi-Agents*. https://cognition.com/blog/dont-build-multi-agents
77. Yan, Cognition (Apr 2026). *Multi-Agents: What's Actually Working*. https://cognition.com/blog/multi-agents-working
78. Geng & Neubig (2026). *Effective Strategies for Asynchronous Software Engineering Agents*. arXiv:2603.21489
79. Cemri et al. (2025). *Why Do Multi-Agent LLM Systems Fail?*. arXiv:2503.13657
80. Schluntz & Zhang, Anthropic (Dec 2024). *Building effective agents*. https://www.anthropic.com/engineering/building-effective-agents
81. Anthropic (Sep 2025). *Effective context engineering for AI agents*. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
82. Yang et al. (2024). *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering*. arXiv:2405.15793
83. Xia et al. (2024). *Agentless: Demystifying LLM-based Software Engineering Agents*. arXiv:2407.01489
84. SWE-agent team (2025). *mini-swe-agent* (README). https://github.com/SWE-agent/mini-swe-agent
85. Dai et al. (2025). *Lita: Light Agent Uncovers the Agentic Coding Capabilities of LLMs*. arXiv:2509.25873
86. Chen et al. (2026). *Unlocking Model Potentials Through Adaptive Multi-Agent Scaffolding for Efficient Issue Resolution*. arXiv:2606.25514
87. Gloaguen et al. (2026). *Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?*. arXiv:2602.11988
88. Chen et al. (2022). *CodeT: Code Generation with Generated Tests*. arXiv:2207.10397
89. Ridnik et al. (2024). *Code Generation with AlphaCodium: From Prompt Engineering to Flow Engineering*. arXiv:2401.08500
90. Mündler et al. (2024). *SWT-Bench: Testing and Validating Real-World Bug-Fixes with Code Agents*. arXiv:2406.12952
91. Ahmed et al. (2025). *Otter: Generating Tests from Issues to Validate SWE Patches*. arXiv:2502.05368
92. Ehrlich et al. (2025). *CodeMonkeys: Scaling Test-Time Compute for Software Engineering*. arXiv:2501.14723
93. Huang et al. (2023). *AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation*. arXiv:2312.13010
94. Huang et al. (2024). *Measuring the Influence of Incorrect Code on Test Generation*. arXiv:2409.09464
95. Chen et al. (2026). *Rethinking the Value of Agent-Generated Tests for LLM-Based Software Engineering Agents*. arXiv:2602.07900
96. Adnan & Kuhn (2025). *The Debugging Decay Index: Rethinking Debugging Strategies for Code LLMs*. arXiv:2506.18403
97. Wang et al. (2026). *Fail-Fast, Restart-Smart: Early Failure Prediction and Restart for SWE Agentic Tasks*. arXiv:2608.03222
98. Wang et al. (2025). *Are "Solved Issues" in SWE-bench Really Solved Correctly? An Empirical Study*. arXiv:2503.15223
99. Whitfill et al., METR (Mar 2026). *Many SWE-bench-Passing PRs Would Not Be Merged into Main*. https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/
100. Vijayvargiya et al. (2025). *Ambig-SWE: Interactive Agents to Overcome Underspecificity in Software Engineering*. arXiv:2502.13069 (v1 title: Interactive Agents to Overcome Ambiguity in Software Engineering)
101. Grace et al., Anthropic (Jan 2026). *Demystifying evals for AI agents*. https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
102. Shao et al. (2024). *Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models*. arXiv:2402.14207
103. Asai et al. (2024). *OpenScholar: Synthesizing Scientific Literature with Retrieval-augmented LMs*. arXiv:2411.14199. Journal version: *Synthesizing scientific literature with retrieval-augmented language models*, Nature 650:857 (2026), doi:10.1038/s41586-025-10072-4.
104. Skarlinski et al. (2024). *Language agents achieve superhuman synthesis of scientific knowledge*. arXiv:2409.13740
105. Asai et al. (2023). *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*. arXiv:2310.11511
106. Yan et al. (2024). *Corrective Retrieval Augmented Generation*. arXiv:2401.15884
107. Liu et al. (2023). *Evaluating Verifiability in Generative Search Engines*. arXiv:2304.09848
108. Venkit et al. (2025). *DeepTRACE: Auditing Deep Research AI Systems for Tracking Reliability Across Citations and Evidence*. arXiv:2509.04499
109. Rao et al. (2026). *Detecting and Correcting Reference Hallucinations in Commercial LLMs and Deep Research Agents*. arXiv:2604.03173
110. Wallat et al. (2024). *Correctness is not Faithfulness in RAG Attributions*. arXiv:2412.18004
111. Min et al. (2023). *FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation*. arXiv:2305.14251
112. Wei et al. (2024). *Long-form factuality in large language models*. arXiv:2403.18802
113. Song et al. (2024). *VERISCORE: Evaluating the factuality of verifiable claims in long-form text generation*. arXiv:2406.19276
114. Rajendhran et al. (2025). *VeriFastScore: Speeding up long-form factuality evaluation*. arXiv:2505.16973
115. Si et al. (2024). *Can LLMs Generate Novel Research Ideas? A Large-Scale Human Study with 100+ NLP Researchers*. arXiv:2409.04109
116. Si et al. (2025). *The Ideation-Execution Gap: Execution Outcomes of LLM-Generated versus Human Research Ideas*. arXiv:2506.20803
117. Gupta & Pruthi (2025). *All That Glitters is Not Novel: Plagiarism in AI Generated Research*. arXiv:2502.16487
118. Lu et al. (2024). *The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery*. arXiv:2408.06292. Journal version: *Towards end-to-end automation of AI research*, Nature 651:914 (2026), doi:10.1038/s41586-026-10265-5.
119. Yamada et al. (2025). *The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search*. arXiv:2504.08066
120. Beel et al. (2025). *Evaluating Sakana's AI Scientist: Bold Claims, Mixed Results, and a Promising Future?*. arXiv:2502.14297
121. Schopf & Färber (2026). *Is this Idea Novel? An Automated Benchmark for Judgment of Research Ideas*. arXiv:2603.10303
122. Shahid et al. (2025). *Literature-Grounded Novelty Assessment of Scientific Ideas*. arXiv:2506.22026
123. Son et al. (2025). *When AI Co-Scientists Fail: SPOT-a Benchmark for Automated Verification of Scientific Research*. arXiv:2505.11855
124. Liang et al. (2023). *Can large language models provide useful feedback on research papers? A large-scale empirical analysis*. arXiv:2310.01783
125. Ye et al. (2024). *Are We There Yet? Revealing the Risks of Utilizing Large Language Models in Scholarly Peer Review*. arXiv:2412.01708
126. Baumann et al. (2026). *Stop Automating Peer Review Without Rigorous Evaluation*. arXiv:2605.03202
127. MiroMind Team (2025). *MiroThinker: Pushing the Performance Boundaries of Open-Source Research Agents via Model, Context, and Interactive Scaling*. arXiv:2511.11793
128. MiroMind Team (2026). *MiroThinker-1.7 & H1: Towards Heavy-Duty Research Agents via Verification*. arXiv:2603.15726
129. Liu et al. (2023). *Lost in the Middle: How Language Models Use Long Contexts*. arXiv:2307.03172
130. Modarressi et al. (2025). *NoLiMa: Long-Context Evaluation Beyond Literal Matching*. arXiv:2502.05167
131. Du et al. (2025). *Context Length Alone Hurts LLM Performance Despite Perfect Retrieval*. arXiv:2510.05381
132. Hong, Troynikov & Huber, Chroma (Jul 2025). *Context Rot: How Increasing Input Tokens Impacts LLM Performance*. https://www.trychroma.com/research/context-rot
133. Rodionov et al. (2026). *Reasoning Shift: How Context Silently Shortens LLM Reasoning*. arXiv:2604.01161
134. Jin et al. (2024). *Long-Context LLMs Meet RAG: Overcoming Challenges for Long Inputs in RAG*. arXiv:2410.05983
135. Lindenbauer et al. (2025). *The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management*. arXiv:2508.21433
136. Xiong et al. (2025). *How Memory Management Impacts LLM Agents: An Empirical Study of Experience-Following Behavior*. arXiv:2505.16067
137. Chen et al. (2025). *HaluMem: Evaluating Hallucinations in Memory Systems of Agents*. arXiv:2511.03506
138. Hu et al. (2025). *Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions*. arXiv:2507.05257
139. Zhang et al. (2025). *Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models*. arXiv:2510.04618
140. Packer et al. (2023). *MemGPT: Towards LLMs as Operating Systems*. arXiv:2310.08560
141. Park et al. (2023). *Generative Agents: Interactive Simulacra of Human Behavior*. arXiv:2304.03442
142. Xu et al. (2025). *A-MEM: Agentic Memory for LLM Agents*. arXiv:2502.12110
143. Chhikara et al. (2025). *Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory*. arXiv:2504.19413
144. Thakur et al. (2021). *BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval Models*. arXiv:2104.08663
145. Weller et al. (2025). *On the Theoretical Limitations of Embedding-Based Retrieval*. arXiv:2508.21038
146. Anthropic (Sep 2024). *Introducing Contextual Retrieval*. https://www.anthropic.com/news/contextual-retrieval
147. Zhang et al. (2025). *Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models*. arXiv:2506.05176
148. Jacob et al. (2024). *Drowning in Documents: Consequences of Scaling Reranker Inference*. arXiv:2411.11767
149. Jedidi et al. (2025). *Don't "Overthink" Passage Reranking: Is Reasoning Truly Necessary?*. arXiv:2505.16886
150. Young, Anthropic (Nov 2025). *Effective harnesses for long-running agents*. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
151. Chen et al. (2023). *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance*. arXiv:2305.05176
152. Ong et al. (2024). *RouteLLM: Learning to Route LLMs with Preference Data*. arXiv:2406.18665
153. Ding et al. (2024). *Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing*. arXiv:2404.14618
154. Aggarwal et al. (2023). *Let's Sample Step by Step: Adaptive-Consistency for Efficient Reasoning and Coding with LLMs*. arXiv:2305.11860
155. Taubenfeld et al. (2025). *Confidence Improves Self-Consistency in LLMs*. arXiv:2502.06233
156. Fu et al. (2025). *Deep Think with Confidence*. arXiv:2508.15260
157. Xiong et al. (2023). *Can LLMs Express Their Uncertainty? An Empirical Evaluation of Confidence Elicitation in LLMs*. arXiv:2306.13063
158. Kadavath et al. (2022). *Language Models (Mostly) Know What They Know*. arXiv:2207.05221
159. Yoon et al. (2025). *Reasoning Models Better Express Their Confidence*. arXiv:2505.14489
160. Kirichenko et al. (2025). *AbstentionBench: Reasoning LLMs Fail on Unanswerable Questions*. arXiv:2506.09038
161. Song et al. (2025). *The Hallucination Tax of Reinforcement Finetuning*. arXiv:2505.13988
162. Joren et al. (2024). *Sufficient Context: A New Lens on Retrieval Augmented Generation Systems*. arXiv:2411.06037
163. Kalai et al. (2025). *Why Language Models Hallucinate*. arXiv:2509.04664
164. Manakul et al. (2023). *SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for Generative Large Language Models*. arXiv:2303.08896
165. Laban et al. (2025). *LLMs Get Lost In Multi-Turn Conversation*. arXiv:2505.06120
166. Gulati et al. (2026). *Ask Early, Ask Late, Ask Right: When Does Clarification Timing Matter for Long-Horizon Agents?*. arXiv:2605.07937
