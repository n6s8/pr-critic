import type {
  AnalyzeResponse,
  Candidate,
  Issue,
  PRMetadata,
  RetrievalHit,
  Severity,
  TraceEntry,
  TraceStatus,
} from '../types'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export class ReviewRequestError extends Error {
  statusCode: number
  code: string
  retryAfterSeconds: number | null

  constructor(
    message: string,
    {
      statusCode,
      code,
      retryAfterSeconds = null,
    }: {
      statusCode: number
      code: string
      retryAfterSeconds?: number | null
    }
  ) {
    super(message)
    this.name = 'ReviewRequestError'
    this.statusCode = statusCode
    this.code = code
    this.retryAfterSeconds = retryAfterSeconds
  }
}

function normalizeSeverity(value: unknown): Severity {
  const normalized = String(value ?? '').toLowerCase()

  if (normalized === 'critical' || normalized === 'warning' || normalized === 'info') {
    return normalized
  }

  if (normalized === 'major' || normalized === 'warn' || normalized === 'medium') {
    return 'warning'
  }

  return 'info'
}

function normalizeTraceStatus(value: unknown): TraceStatus {
  const normalized = String(value ?? '').toLowerCase()

  if (
    normalized === 'started' ||
    normalized === 'completed' ||
    normalized === 'warning' ||
    normalized === 'error' ||
    normalized === 'routing'
  ) {
    return normalized
  }

  return 'completed'
}

function mapIssues(raw: unknown): Issue[] {
  if (!Array.isArray(raw)) return []

  return raw.map((issue, index) => {
    const item = (issue ?? {}) as Partial<Issue>

    return {
      severity: normalizeSeverity(item.severity),
      issue_type: typeof item.issue_type === 'string' ? item.issue_type : 'unknown',
      file: item.file ?? 'unknown',
      line: typeof item.line === 'number' ? item.line : 0,
      message: item.message ?? `Issue ${index + 1}`,
      code_snippet: typeof item.code_snippet === 'string' ? item.code_snippet : '',
      source_id: typeof item.source_id === 'string' ? item.source_id : 'diff',
    }
  })
}

function mapRetrieval(raw: unknown): RetrievalHit[] {
  if (!Array.isArray(raw)) return []

  return raw.map((hit, index) => {
    const item = (hit ?? {}) as Partial<RetrievalHit>

    return {
      source: item.source ?? `source-${index + 1}`,
      section: item.section ?? 'general',
      snippet: item.snippet ?? '',
      relevance: typeof item.relevance === 'number' ? item.relevance : 0,
    }
  })
}

function mapCandidates(raw: unknown): Candidate[] {
  if (!Array.isArray(raw)) return []

  return raw.map((candidate, index) => {
    const item = (candidate ?? {}) as Partial<Candidate>

    return {
      index: typeof item.index === 'number' ? item.index : index,
      id: item.id ?? `candidate-${index + 1}`,
      strategy: item.strategy ?? 'unknown',
      review: item.review ?? '',
      score: typeof item.score === 'number' ? item.score : 0,
      score_rationale: item.score_rationale ?? '',
      critic_issues: Array.isArray(item.critic_issues)
        ? item.critic_issues.map(issue => String(issue))
        : [],
    }
  })
}

function mapTrace(raw: unknown): TraceEntry[] {
  if (!Array.isArray(raw)) return []

  return raw.map(entry => {
    const item = (entry ?? {}) as Partial<TraceEntry>

    return {
      agent: item.agent ?? 'unknown_agent',
      event: item.event ?? 'unknown',
      status: normalizeTraceStatus(item.status),
      timestamp: item.timestamp ?? '',
      duration_ms: typeof item.duration_ms === 'number' ? item.duration_ms : null,
      data:
        item.data && typeof item.data === 'object' && !Array.isArray(item.data)
          ? (item.data as Record<string, unknown>)
          : {},
    }
  })
}

function mapMetadata(raw: unknown, fallbackUrl: string): PRMetadata {
  const item = (raw ?? {}) as Partial<PRMetadata>

  return {
    title: item.title ?? 'Pull Request Review',
    author: item.author ?? 'unknown',
    base_branch: item.base_branch ?? 'main',
    head_branch: item.head_branch ?? '',
    language: item.language ?? 'Unknown',
    files_changed: Array.isArray(item.files_changed) ? item.files_changed : [],
    pr_url: item.pr_url ?? fallbackUrl,
  }
}

export async function analyzeRP(prUrl: string): Promise<AnalyzeResponse> {
  const response = await fetch(`${BASE_URL}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pr_url: prUrl }),
  })

  const responseText = await response.text()

  if (!response.ok) {
    let message = `Review request failed with status ${response.status}`
    let code = 'review_failed'
    let retryAfterSeconds: number | null = Number(response.headers.get('Retry-After'))
    if (Number.isNaN(retryAfterSeconds)) {
      retryAfterSeconds = null
    }

    if (responseText.trim()) {
      try {
        const parsed = JSON.parse(responseText)

        if (parsed.error && typeof parsed.error.code === 'string') {
          code = parsed.error.code
        }
        const parsedRetryAfter =
          parsed.error?.details?.retry_after_seconds ??
          parsed.details?.retry_after_seconds
        if (
          retryAfterSeconds === null &&
          typeof parsedRetryAfter === 'number' &&
          Number.isFinite(parsedRetryAfter)
        ) {
          retryAfterSeconds = parsedRetryAfter
        }

        if (typeof parsed.detail === 'string') {
          message = parsed.detail
        } else if (parsed.error && typeof parsed.error.message === 'string') {
          message = parsed.error.message
        } else if (typeof parsed.message === 'string') {
          message = parsed.message
        } else {
          message = responseText.trim()
        }
      } catch {
        message = responseText.trim()
      }
    }

    throw new ReviewRequestError(message, {
      statusCode: response.status,
      code,
      retryAfterSeconds,
    })
  }

  const data = responseText.trim() ? JSON.parse(responseText) : {}
  const candidates = mapCandidates(data.candidates)
  const selectedIndex =
    typeof data.selected_index === 'number' ? data.selected_index : candidates[0]?.index ?? 0
  const selectedReview =
    mapCandidates([data.selected_review])[0] ??
    candidates.find(candidate => candidate.index === selectedIndex) ??
    candidates[0] ?? {
      index: 0,
      id: 'candidate-0',
      strategy: 'unknown',
      review: '',
      score: 0,
      score_rationale: '',
      critic_issues: [],
    }

  return {
    language: typeof data.language === 'string' ? data.language : 'Unknown',
    files_changed: Array.isArray(data.files_changed) ? data.files_changed : [],
    diff_size: typeof data.diff_size === 'number' ? data.diff_size : 0,
    pr_metadata: mapMetadata(data.pr_metadata, prUrl),
    diff: typeof data.diff === 'string' ? data.diff : '',
    retrieval: mapRetrieval(data.retrieval),
    candidates,
    selected_index: selectedIndex,
    selected_review: selectedReview,
    selector_reason:
      typeof data.selector_reason === 'string' ? data.selector_reason : '',
    branch_taken: Boolean(data.branch_taken),
    branch_improvement:
      typeof data.branch_improvement === 'number' ? data.branch_improvement : null,
    score: typeof data.score === 'number' ? data.score : selectedReview.score,
    issues: mapIssues(data.issues),
    trace: mapTrace(data.trace),
  }
}
