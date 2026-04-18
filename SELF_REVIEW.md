# Self-Review — PR Critic

**A critical assessment by the author**

| | |
|---|---|
| Project | PR Critic |
| Author | n6s8 |
| Purpose | Honest technical retrospective for submission review |

---

> This document is a candid assessment of what the system does well, where it cuts corners, and what I would do differently with more time. Engineering maturity means being the first to name your own blind spots — not waiting for someone else to find them.

---

## 1. What Works Well

### Multi-Agent Architecture

The decision to decompose the review pipeline into six specialised agents with a built-in quality loop is the strongest engineering choice in the project. It was also the hardest to commit to early — a single LLM call would have been faster to build and easier to test. The payoff showed up quickly: once the critic agent existed, review quality became measurable. Once it was measurable, it was improvable. That feedback loop would not have existed in a monolithic design.

The conditional branching logic — trigger the branch path only when the initial review scores below threshold — reflects a real design principle: only spend compute when the first attempt is not good enough. This keeps the happy path fast (single generation pass, ~6–8 seconds) while ensuring a safety net exists for weak initial outputs.

The compiled LangGraph singleton is a small but meaningful production detail. Compiling the graph once at startup rather than per request eliminates repeated DAG construction overhead. It signals awareness that the system needs to behave like a server, not a script.

### Separation of Model Profiles

Assigning distinct temperature settings per agent role — low temperature (0.1) for scoring and selection, higher temperature (0.2–0.5) for generation — is a deliberate and correct choice that is easy to overlook. A critic agent that introduces randomness into its scoring is unreliable; a review agent that generates the same text every time produces repetitive output. These are different jobs and they warrant different parameters.

### Evaluation Framework

The 20-scenario evaluation suite is the part of this project I am most satisfied with. It exists entirely because of one painful lesson: the first time I changed a system prompt and the review quality degraded, I had no systematic way to detect it. I had to manually read outputs and rely on intuition. The evaluation framework eliminated that problem. It now runs on every CI push and produces quantitative, reproducible results. That is infrastructure that pays back continuously.

The adversarial scenarios — prompt injection attempts, null bytes in URLs, jailbreak variable names — reflect real-world threat modelling rather than happy-path testing. The fact that the pipeline handles them gracefully is something I can verify, not just claim.

### Frontend Execution Trace

Exposing the agent execution trace in the dashboard UI was a late addition that turned out to be the most valuable UI decision in the project. It transforms PR Critic from a black box into a glass box. Users can see which agents ran, how long each took, what routing decisions were made, and why. For a system that asks users to trust AI output on their codebase, transparency is not a nice-to-have — it is a prerequisite for trust.

---

## 2. Technical Trade-offs

### TF-IDF Instead of a Vector Database

The RAG layer uses a TF-IDF keyword retriever over five local text files. This was a deliberate trade-off, not an oversight — but it is worth being honest about what was traded away.

**Why this choice was made:** The corpus is small (five documents), stable (it does not change between requests), and keyword-dense (OWASP entries, PEP 8 rules, and TypeScript guidelines all use precise, repeatable vocabulary). TF-IDF performs well in this regime. It is also deterministic, requires no external infrastructure, and adds zero latency to the pipeline. A vector database would have introduced a service dependency, an embedding step, and non-deterministic retrieval — all costs with minimal benefit at this corpus size.

**What was traded away:** Semantic understanding. TF-IDF retrieves documents that share vocabulary with the query. If a diff contains a subtle race condition that no corpus document describes using the exact same terms, the retriever will miss it. A semantic embedding model would surface conceptually related guidance even when the words differ. For the current corpus and use case this matters infrequently, but it is a real ceiling on retrieval quality.

**Honest assessment:** TF-IDF is the right choice for this scope. It becomes the wrong choice the moment the corpus grows beyond ~20 documents or starts containing long-form prose where keyword frequency is a poor proxy for relevance.

### Simplified Diff Handling

The system processes the raw unified diff as a string. It does not parse the diff into a structured representation — there is no explicit awareness of which lines were added versus removed, no file-level segmentation within the prompt, and no reconstruction of the surrounding code context (the lines before and after the change that did not change themselves).

This means that for a diff touching ten files across five packages, the review agent sees a single concatenated string truncated at a character limit. The agent infers file boundaries from the `diff --git` markers in the text, which works for well-structured diffs but degrades for large or unusual ones.

A proper implementation would parse the diff into a structured object — per-file, per-hunk, with added/removed lines explicitly tagged — and construct the prompt from that structure rather than from raw text. This would also enable line-level issue attribution (the issue extractor currently uses heuristics to map findings to line numbers, which is imprecise).

### Diff Truncation

Agent prompts cap diff input at 2,000–3,500 characters. For a small pull request this is sufficient. For a pull request that touches hundreds of lines across multiple files — a realistic scenario in any active codebase — the review agent sees a truncated view. The tail of the diff, which frequently contains the most recently added code, is silently dropped.

The truncation is announced in the prompt (`[diff truncated for branch review]`) so the agent is aware of it, but there is no guarantee the most important part of the diff is in the retained portion. A production system would implement sliding-window or file-priority strategies to ensure the highest-risk files are always included within the context limit.

### Sequential LLM Calls

The pipeline makes 3–6 serial LLM calls per request. Each call waits for the previous one to complete. The branch path is the worst case: generate two alternative reviews (sequentially), then score each (sequentially), then select. There is no architectural reason these calls need to be sequential — branch candidate generation is embarrassingly parallel — but the current implementation does not parallelise them.

This is a known gap, not an unknown one. The fix is a small number of lines using `asyncio.gather()`, and LangGraph supports async nodes natively. It was deferred in favour of correctness over performance during the initial build.

---

## 3. Limitations

### GitHub API Integration

The live mode fetches raw `.diff` content from public GitHub URLs. It does not authenticate with the GitHub API beyond an optional personal access token. This means:

- **Private repositories are not supported** without manual token configuration
- **Rate limits apply** at the unauthenticated rate (60 requests/hour per IP), which is trivially easy to exhaust during a demo or evaluation run
- **Rich PR metadata is unavailable** — linked issues, labels, previous review history, CI status, and reviewer assignments are all accessible via GitHub's GraphQL API but are not used

A production integration would use GitHub Apps authentication, which provides a per-installation rate limit of 5,000 requests/hour and access to the full PR context. This is a well-understood path but was out of scope for this project.

### Limited Code Comprehension

The review agents read diffs as text. They have no access to the broader codebase — the functions being called, the interfaces being implemented, the data structures being used. A diff that refactors a function signature looks correct in isolation but may break ten call sites in other files that are not in the diff.

This is a fundamental limitation of diff-based review and not unique to this system — human reviewers face the same constraint unless they check out the branch and read the full codebase. However, it means PR Critic cannot reliably detect cross-file consistency issues, dependency violations, or interface contract breaks. It reviews what it can see, not what the change affects.

### Issue Line Number Attribution

The issue extractor uses heuristics to map review findings to specific line numbers in the diff. It works reliably for findings that mention specific line references explicitly. For findings that describe general patterns across multiple lines, the attribution is approximate. A user following up on a "line 47" finding may find the actual issue is on line 44 or line 51.

This is noticeable enough to erode trust if a user checks a finding and cannot locate it at the reported line. Fixing it properly requires structured diff parsing (see above), which would allow exact line tracking throughout the pipeline.

---

## 4. What I Would Improve Next

### Real Semantic Retrieval

The most impactful single improvement to review quality would be replacing the TF-IDF retriever with a vector database and a text embedding model. ChromaDB with `text-embedding-3-small` (OpenAI) or a locally-hosted sentence transformer model would allow the system to retrieve conceptually relevant guidance even when vocabulary does not overlap.

This would also unlock corpus growth. The current five-document corpus is constrained partly by the diminishing returns of adding keyword-dense documents to a TF-IDF index. A semantic index degrades more gracefully as corpus size increases, making it practical to add language-specific frameworks (React, FastAPI, SQLAlchemy), domain-specific standards (HIPAA, PCI-DSS), or team-specific coding conventions.

### Structured Diff Parsing

Replacing raw string diff handling with a proper parser (`unidiff` in Python is mature and well-tested) would unlock several improvements simultaneously: accurate line number attribution, per-file review segmentation for large PRs, explicit added/removed line tagging in prompts, and the ability to prioritise high-risk files when truncation is necessary.

This is a moderate implementation effort with a high quality return. It is the change I would prioritise above parallelisation or additional agent strategies.

### Parallel Branch Generation

As noted above, parallelising branch candidate generation with `asyncio.gather()` is architecturally straightforward and would reduce worst-case latency from ~15 seconds to ~8–9 seconds. For a developer tool, that difference is meaningful — it is the difference between a tool that feels fast and one that feels like it is thinking.

### GitHub App Integration and Webhook Trigger

The current UX requires a developer to open the PR Critic dashboard, paste a URL, and wait. A production integration would post review findings as GitHub PR comments automatically, triggered by a webhook on pull request creation. This removes all friction from the workflow — the developer would simply open their pull request and find the automated review already waiting.

### Confidence and Uncertainty Signalling

The current output presents findings with the same confidence regardless of whether the model is certain or speculating. A senior reviewer reading code will say "this is definitely a SQL injection" for one finding and "this might be a race condition, worth investigating" for another. The system does not currently distinguish these cases.

Adding explicit confidence levels to findings — derived from the critic agent's scoring and the model's own uncertainty signals — would help users prioritise which findings to investigate first and which to take with more caution.

---

## 5. Key Learning Outcomes

### Multi-Agent Orchestration Is an Architecture Decision, Not a Feature

The most important thing I learned building this project is that adding agents is not the same as improving a system. Early in the build, the instinct was to add agents whenever something was not working well. The discipline required was the opposite: define what each agent is responsible for, what it is *not* responsible for, and what the contract between them is. Agents that have overlapping responsibilities produce redundant or contradictory output. Agents with ambiguous contracts produce unpredictable behaviour at the boundaries.

LangGraph's explicit state schema enforces this discipline mechanically — if an agent writes to a state key that another agent depends on, that dependency is visible. This makes the architecture legible in a way that raw function chains are not.

### LLMs Are Reliable Generators but Unreliable Judges

The review agent produces surprisingly good output most of the time. The critic agent is harder to trust. Scoring a review requires the model to hold two representations in mind simultaneously — the review and the diff — and apply a rubric consistently across both. This is exactly the kind of multi-step reasoning where current language models are weakest. The regex fallback in the critic's JSON parser exists because the model occasionally returns a score embedded in prose rather than valid JSON, even when the prompt explicitly instructs otherwise.

The lesson is that LLMs should be used to generate content and transform it, not to evaluate it with precision. Where precision matters — scoring, comparison, selection — the prompt engineering needs to be defensive, the output parsing needs a fallback, and the results should be treated as approximate, not authoritative.

### Observability Is Not Optional

The execution trace was added late. Before it existed, debugging a bad review required adding print statements, running the pipeline manually, and reading raw LLM output. After it existed, every agent run was inspectable end-to-end without any additional tooling. This experience confirmed something I had read but not fully internalised: for agentic systems, where the failure mode is often a subtly wrong output rather than a crash, observability is more valuable than it is in traditional software. A crash has a stack trace. A bad AI output has nothing unless you build the instrumentation yourself.

### System Design Thinking Over Model Selection

The most common question about AI projects is "which model did you use?" The least interesting question about this project is which model was used. The Groq / Llama 3.1 choice was made primarily for latency and cost — a different model would produce different outputs but would not change the fundamental quality characteristics of the system. What determines quality here is the architecture: the retrieval grounding, the self-evaluation loop, the strategy branching, and the structured output contract. A better model inside a bad architecture produces marginally better bad results. A good architecture scales with model improvements for free.

---

## Summary Assessment

| Area | Assessment |
|---|---|
| Architecture | Strong. The multi-agent pipeline with self-evaluation is the right design for this problem. |
| Test coverage | Strong. Adversarial cases, evaluation framework, and CI pipeline are production-quality. |
| RAG implementation | Adequate for current scope. TF-IDF is a conscious trade-off, not a gap in understanding. |
| Diff handling | Weak. Raw string processing is the largest source of imprecision in the current system. |
| GitHub integration | Partial. Live mode works for public repos; production readiness requires GitHub Apps. |
| Latency | Acceptable but improvable. Parallelisation is a known next step, not a discovery. |
| Observability | Strong. Execution trace gives the system transparency that most AI tools lack. |

The project demonstrates that a well-designed multi-agent system can produce consistently useful output on a real engineering problem. It also demonstrates where first versions of AI systems reliably cut corners: retrieval depth, structured data handling, and integration completeness. Knowing where the corners are is the first step to addressing them.

---

*Repository: [github.com/n6s8/pr-critic](https://github.com/n6s8/pr-critic)*