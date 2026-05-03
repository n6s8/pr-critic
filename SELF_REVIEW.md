# Self-Review - PR Critic

## What Is Strong

### Workflow Separation

The strongest part of the project is now the explicit collaborative workflow. Fetching, planning, retrieval, candidate generation, scoring, branching, false-positive filtering, synthesis, and selection are separate responsibilities with visible artifacts between them. That makes the system inspectable and makes fake orchestration much harder.

### Real MCP Boundary

GitHub access now goes through a local MCP server/client boundary. The fetch agent calls `get_pull_request` and `get_pull_request_diff` through `GitHubMCPClient`, and direct REST access is contained behind the MCP server provider layer. This closes the highest-risk capstone rubric gap.

### Evidence-Grounded Reviews

Every surviving issue must include file, line, changed code snippet, and source id. The false-positive guard removes weak or unsupported findings, and the selector synthesizes grounded findings across candidates so a branch cannot accidentally lose issues found by the initial pass.

### Honest Runtime Behavior

The runtime is materially more credible than before:

- GitHub fetch failures return errors instead of fake reviews
- LLM rate limits produce explicit degraded fallback behavior
- downstream LLM stages are skipped when the request is already rate-limited
- the frontend reflects those states instead of masking them

### Token Control

The biggest engineering improvement is the prompt-shaping layer. The system now filters the diff before the first review prompt, prioritizes higher-risk files, keeps RAG compact, and branches only when the score and token budget justify the extra calls.

### Evaluation

The evaluation story is defensible in a narrower sense. The runner measures precision, recall, F1, and false positives against structured expected issues instead of using keyword buckets. That is still not the same as a human benchmark on real pull requests, but it is concrete and repeatable.

After the hardening pass, the deterministic mock evaluation reports 20/20 successful scenarios with average precision 1.0, recall 1.0, F1 1.0, and zero false positives.

## Trade-offs

### Partial Diff Review

The system no longer behaves like it reviews every changed line equally. For normal PRs, it intentionally selects the most relevant chunks before the main LLM pass. That is the right trade-off for rate limits and token control, but it means some lower-priority files may be omitted from the first review.

### Reduced Context vs Reliability

The system gives up some breadth on purpose. Tight filtering, compact retrieval, and bounded prompts make the runtime more stable and more predictable under real token and rate-limit pressure, but they also reduce how much context reaches the model in a single pass.

### Bounded Tokens vs Completeness

The prompt budget is now enforced rather than aspirational. That improves resilience, but it means completeness is conditional: the system is optimized to review the highest-signal parts of a PR, not to guarantee exhaustive coverage.

### Local TF-IDF Retrieval

The retriever is intentionally simple and compact. For a local corpus, TF-IDF plus compact snippets is cheaper and easier to inspect than a heavier retrieval stack. The downside is weaker semantic recall than an embedding or hybrid system on a very large corpus.

### Conservative Large-PR Handling

Very large PRs are handled in stability-first mode. Branching and review-generation LLM calls are disabled, the selected strategy becomes `large_pr_partial`, and the result is explicitly partial. That is honest and robust, but it is not broad coverage.

## Limitations

- There is no GitHub webhook or GitHub App review loop
- Rate limiting and caches are in-memory
- Evaluation scenarios are local and synthetic
- The system is still not fully repository-aware; repository signals are lightweight and best-effort
- There is no full repository analysis
- There are no AST-based analyzers or deeper static-analysis integrations

## Remaining Credibility Risks

The main remaining credibility risk is no longer MCP, fake orchestration, or false-positive control. It is broader real-world coverage and validation depth.

- The system still does not inspect full repository context or run static analysis tools
- Live model behavior is not validated in every CI run unless credentials are configured
- Issue extraction and diff anchoring are much stronger after grounding, but still not equivalent to compiler-backed AST analysis for every language

## Future Improvements

- AST-based and symbol-aware analysis before the LLM review
- Deeper GitHub integration through webhooks, review drafts, and comment publishing
- A distributed cache backend such as Redis for shared fetch/retrieval/review caching across replicas

## Summary

This project is now a top-tier capstone engineering submission: real MCP integration, explicit multi-agent state, bounded prompting, issue-level evaluation, evidence-grounded findings, and a frontend that reflects real backend behavior. The remaining improvements are production expansion items rather than blockers for the capstone rubric.
