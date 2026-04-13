import type {
  AnalyzeResponse,
  Issue,
  LogLevel,
  Severity,
  Strategy,
  TraceEntry,
} from '../types'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

function normalizeSeverity(value: unknown): Severity {
  const normalized = String(value ?? '').toLowerCase()

  if (
    normalized === 'critical' ||
    normalized === 'major' ||
    normalized === 'minor' ||
    normalized === 'warning' ||
    normalized === 'info'
  ) {
    return normalized
  }

  if (['error', 'high', 'blocker'].includes(normalized)) {
    return 'critical'
  }

  if (['warn', 'medium'].includes(normalized)) {
    return 'major'
  }

  return 'minor'
}

function normalizeLogLevel(value: unknown): LogLevel {
  const normalized = String(value ?? '').toUpperCase()

  if (
    normalized === 'WARN' ||
    normalized === 'ERROR' ||
    normalized === 'DEBUG' ||
    normalized === 'SUCCESS'
  ) {
    return normalized
  }

  return 'INFO'
}

function mapIssues(raw: unknown): Issue[] {
  if (!Array.isArray(raw)) return []

  return raw.map((issue, index) => {
    const item = (issue ?? {}) as Partial<Issue>

    return {
      severity: normalizeSeverity(item.severity),
      file: item.file ?? 'unknown',
      line: typeof item.line === 'number' ? item.line : 0,
      message: item.message ?? `Issue ${index + 1}`,
    }
  })
}

function mapStrategies(raw: unknown): Strategy[] {
  if (!Array.isArray(raw)) return []

  return raw.map((strategy, index) => {
    const item = (strategy ?? {}) as Partial<Strategy>

    return {
      id: item.id ?? `strategy-${index + 1}`,
      name: item.name ?? item.id ?? `Strategy ${index + 1}`,
      score: typeof item.score === 'number' ? item.score : 0,
      description: item.description ?? '',
    }
  })
}

function mapTrace(raw: unknown): TraceEntry[] {
  if (!Array.isArray(raw)) return []

  return raw.map(entry => {
    const item = (entry ?? {}) as Partial<TraceEntry>

    return {
      agent: item.agent ?? 'unknown_agent',
      level: normalizeLogLevel(item.level),
      message: item.message ?? '',
      timestamp: item.timestamp ?? '',
    }
  })
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

    if (responseText.trim()) {
      try {
        const parsed = JSON.parse(responseText)

        if (typeof parsed.detail === 'string') {
          message = parsed.detail
        } else if (typeof parsed.message === 'string') {
          message = parsed.message
        } else {
          message = responseText.trim()
        }
      } catch {
        message = responseText.trim()
      }
    }

    throw new Error(message)
  }

  const data = responseText.trim() ? JSON.parse(responseText) : {}
  const strategies = mapStrategies(data.strategies)

  return {
    score: typeof data.score === 'number' ? data.score : 0,
    strategies,
    selected_strategy:
      typeof data.selected_strategy === 'string'
        ? data.selected_strategy
        : strategies[0]?.id ?? '',
    review: typeof data.review === 'string' ? data.review : '',
    issues: mapIssues(data.issues),
    trace: mapTrace(data.trace),
  }
}
