# Self-Review - PR Critic

## What Is Strong

### Multi-Agent Structure

The strongest part of the project is the explicit workflow. Candidate generation, scoring, branching, and selection are separate responsibilities with visible state between them. That makes the system easier to debug and harder to fake.

### Evaluation

The evaluation story is now defensible. The runner measures precision, recall, F1, and false positives against named scenarios instead of reporting synthetic quality numbers. That is not the same as human review benchmarking, but it is at least honest and repeatable.

### Contract Discipline

The frontend now depends on a clean backend contract instead of reverse-engineering state from trace text. That change matters more than UI polish because it removes an entire class of fake intelligence.

## Trade-offs

### Local TF-IDF Retrieval

The retriever is intentionally simple. For a small local corpus, TF-IDF is cheaper and more deterministic than a vector database. The downside is obvious: it will miss semantically related guidance when vocabulary does not overlap well.

### Diff-Scoped Review

The system reviews what is visible in the diff. That keeps the scope realistic, but it means the model cannot reason about the full repository or downstream call sites it cannot see.

### Conservative Large-Diff Handling

The backend now chunks diffs more cleanly than before, but very large PRs are still handled conservatively. This keeps the implementation understandable, but it is not optimized for the biggest review workloads.

## Limitations

- The corpus is still small
- There is no GitHub webhook or GitHub App integration
- Rate limiting and caches are in-memory
- Review quality is measured against scenarios, not human-labeled reviewer judgments

## Remaining Credibility Risks

The main remaining risk is not fake logic anymore. It is scope. A reviewer can still fairly say the system is credible for a capstone and not yet complete enough for a broad production rollout. That is acceptable as long as the project states that clearly.

## Summary

This project is now strongest as a credible engineering submission: explicit state, visible evidence, real evaluation, and a frontend that reflects the backend instead of pretending to be more dynamic than it is.
