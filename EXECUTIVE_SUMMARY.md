# Executive Summary — PR Critic

**AI-Powered Pull Request Review System**

| | |
|---|---|
| Author | n6s8 |
| Project | PR Critic |
| Audience | Review committee, management, investors |

---

## The Problem

Every time a developer finishes writing code, it goes through a process called a **pull request review** — a human colleague reads the new code, checks for mistakes, and approves it before it enters the product. In theory, this is a quality gate. In practice, it is one of the most frustrating bottlenecks in software development.

Three problems occur consistently across engineering teams of all sizes:

**It is slow.** The average pull request waits hours — sometimes days — for a reviewer to become available. During that time, the developer sits idle or context-switches to another task, losing momentum. Studies across the industry consistently show that review wait time is one of the top contributors to slow release cycles.

**It is inconsistent.** Whether a piece of code passes review depends heavily on who reviews it and when. A tired reviewer at the end of the day will miss issues that a fresh one would catch in the morning. A junior reviewer may not know the security implications of a pattern that a senior would flag immediately. The result is a lottery, not a process.

**It is expensive.** Senior engineers — the people best qualified to catch important issues — spend a significant portion of their week on reviews. This is time taken away from building product. For a team of ten engineers, even one hour of review time per day per person adds up to over 2,500 hours of senior engineering capacity lost per year.

The core issue is that a large proportion of review findings are **mechanical**: missing type declarations, insecure coding patterns, style violations, duplicated logic. These do not require human judgment. They require consistency and coverage — two things machines do better than people.

---

## The Solution

**PR Critic** is an AI system that performs an automated first-pass review of any pull request in seconds. A developer submits a link to their code changes, and within 10–15 seconds receives a structured report containing:

- An overall quality score from 0 to 10
- A list of specific issues found, each tagged by severity, file, and line number
- A written review explaining what was found and why it matters
- A transparent log of exactly how the system reached its conclusions

The system is designed to catch the mechanical class of issues — security vulnerabilities, style violations, logic errors, and poor coding patterns — so that human reviewers can focus their attention on the things that genuinely require human judgment: product decisions, architecture choices, and business logic.

PR Critic is live at [pr-critic.vercel.app](https://pr-critic.vercel.app) and can review any public GitHub pull request without any setup.

---

## How It Works — Without the Jargon

Rather than asking a single AI model to review code and hoping for a good answer, PR Critic uses a **pipeline of six specialised AI agents**, each responsible for one specific job.

Think of it as an assembly line with quality control built in:

1. A **research agent** fetches the code changes and identifies the programming language
2. A **knowledge agent** retrieves relevant coding standards for that language — security rules, style guides, best practices — from a curated internal library
3. A **review agent** reads the code and the standards together, then writes a structured review
4. A **critic agent** independently scores that review on four dimensions: usefulness, coverage, accuracy, and clarity
5. If the score is too low, a **strategy agent** generates alternative reviews using different specialist lenses — security focus, correctness focus, or language-specific best practices
6. A **selector agent** compares all versions and picks the best one to return

This pipeline runs automatically from end to end in one request. The user sees only the final result — but the system has performed what is effectively a multi-round internal review of its own output before presenting it.

---

## Results

The system was validated against a purpose-built evaluation suite of 20 pull request scenarios spanning five categories: security vulnerabilities, style violations, design problems, edge cases, and adversarial inputs designed to trick the AI.

Key measurable outputs:

- **End-to-end review time:** 10–15 seconds for a typical pull request diff
- **Quality scoring:** Every review is assigned a numeric score (0–10) using a four-dimension rubric, enabling objective comparison across reviews
- **Structured findings:** Issues are returned with severity level, file name, and line number — not as a wall of text, but as an actionable list
- **Self-correction:** When the initial review scores below the quality threshold, the system automatically generates and evaluates alternative approaches before responding
- **Test coverage:** 28 automated tests including adversarial cases (prompt injection, malformed inputs, empty diffs) with a passing CI pipeline on every code commit
- **Evaluation pass rate:** 100% of the 20 evaluation scenarios completed successfully in mock mode

---

## Business Value

**For individual developers,** PR Critic eliminates the anxiety of waiting. Instead of submitting code and hoping for feedback within the day, they receive a structured first-pass review instantly. Issues are caught earlier — when they are cheapest to fix — rather than discovered in review or, worse, in production.

**For engineering teams,** the system acts as a consistent baseline. Every pull request, regardless of size, complexity, or time of day, receives the same level of mechanical scrutiny. This raises the floor of code quality across the entire team without requiring senior engineers to spend their time on it.

**For engineering managers,** PR Critic is a scalability tool. As a team grows, the review bottleneck typically grows with it — more code, more reviewers needed, more coordination overhead. An automated first-pass review decouples review throughput from headcount. A team of five can review at the pace of a team of ten.

**For organisations with compliance or security requirements,** the system provides a documented, repeatable process. Every review is logged with the exact steps taken, the standards checked, and the score assigned. This creates an audit trail that manual reviews cannot provide.

The return on investment is straightforward: if PR Critic eliminates 30 minutes of senior engineering time per pull request, and a team merges 20 pull requests per week, that is 10 hours of senior engineering capacity recovered every week — time that goes back into building product.

---

## What Makes This Different

The most common reaction when people first hear about this project is: *"Can't you just paste the code into ChatGPT?"*

The answer is yes — and the result is a generic, uncritical, often sycophantic response that misses the issues that matter most.

PR Critic is different in four specific ways:

**It knows what to look for.** Before writing a review, the system retrieves the specific coding standards relevant to the language and context of the PR — OWASP security guidelines, Python style rules, TypeScript best practices. A general-purpose AI has no access to this context unless you provide it manually, every time.

**It checks its own work.** The critic agent evaluates the quality of every review on a defined rubric. If it scores too low, the system tries again with a different strategy. No general-purpose AI tool does this by default.

**Its output is structured.** A review from PR Critic is not a paragraph of prose. It is a machine-readable list of issues with severity, file, line number, and explanation — ready to be displayed in a dashboard, sent to a ticketing system, or integrated into a CI pipeline.

**It is transparent.** Every review comes with a full execution trace showing which agents ran, what decisions were made, and why. Users can inspect the reasoning, not just accept the conclusion.

---

## Lessons Learned

**What worked well:**

The multi-agent architecture with a built-in quality control loop proved to be the right design choice. Early prototypes used a single LLM call and produced inconsistent results — sometimes excellent, often shallow. Adding the critic and branching mechanism raised the floor of review quality significantly. The separation of concerns also made the system far easier to test and improve: changing the review prompt does not affect the scoring logic, and vice versa.

The evaluation framework was one of the most valuable investments. Having 20 named, repeatable scenarios made it possible to detect quality regressions immediately when prompts or models were changed — something that is impossible to do reliably with ad-hoc manual testing.

**What could be improved:**

The retrieval system currently uses a keyword-matching approach (TF-IDF) to find relevant coding standards. This works well for common patterns but can miss issues described with unusual vocabulary. Upgrading to a semantic search approach would improve coverage for subtle or novel code problems.

Review latency averages 10–15 seconds due to multiple sequential AI calls. For a developer tool, this is acceptable but noticeable. Parallelising the alternative review generation step — which is architecturally straightforward — would reduce worst-case latency by approximately half.

Finally, the current GitHub integration fetches diffs from public repositories. A production deployment would integrate with the GitHub Apps API to support private repositories, trigger reviews automatically on pull request creation, and post findings directly as review comments — completing the loop without any manual steps.

---

## Summary

PR Critic demonstrates that the right architecture matters as much as the underlying AI model. By treating code review as a pipeline problem — with separate agents for retrieval, generation, evaluation, and selection — the system produces consistently higher-quality output than any single-model approach, while remaining fast enough to fit naturally into a developer's workflow.

The core insight is simple: the bottleneck in software development is not writing code. It is the time and attention cost of reviewing it. A system that can reliably handle the mechanical half of that work does not replace engineers — it gives them their time back.

---

*Live demo: [pr-critic.vercel.app](https://pr-critic.vercel.app) · Repository: [github.com/n6s8/pr-critic](https://github.com/n6s8/pr-critic)*