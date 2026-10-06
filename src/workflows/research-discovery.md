---
name: research-discovery
description: Broad academic discovery on a topic — query expansion, library-first search, arXiv/OpenReview/web, citation expansion, relevance ranking, intake of must-read papers — with every reported paper verified.
argument-hint: "<research topic>"
---

# Research discovery

1. **Plan:** turn the topic into 3–5 **facets** (sub-questions from different perspectives: problem, methods, evaluation, competing approaches, history). For a narrow topic one facet is fine.
2. **Search in parallel:** one {{agent:researcher}} per facet, each briefed with its facet, the overall topic, and the instruction to search the local library first. Each runs its own protocol: query expansion, deduplication, ranking, one hop of citation expansion, citation verification.
3. **Merge:** deduplicate across facets (DOI → arXiv ID → title+authors), re-rank MUST/SHOULD READ, and list papers found by only one facet.
4. **G5 Grounding:**
   - Run `verify_citations` on the merged list; drop or flag failures.
   - For M/L topics, have {{agent:claim-checker}} check the key claims made about the MUST READ papers.
5. **Intake:** MUST READ arXiv papers are downloaded. Mark important non-arXiv papers `MANUAL/LOCAL PDF INTAKE REQUIRED`. Suggest **paper-analyze** for the top ones.

Report:
- search formulations and sources searched;
- candidate counts before and after deduplication;
- MUST READ / SHOULD READ with IDs;
- citation-expansion discoveries and terminology discovered;
- clusters and apparent gaps (hypotheses only, not novelty claims);
- recommended reading order;
- coverage limitations.
