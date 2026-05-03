import { clsx, type ClassValue } from 'clsx'
import type {
  Candidate,
  PRMetadata,
  PipelineStep,
  Severity,
  TraceEntry,
  TraceStatus,
} from '../types'

export type IssueSeverityTone = 'critical' | 'major' | 'minor'
export type AgentStatus = 'started' | 'completed' | 'warning' | 'error' | 'routing'

export interface PRContext {
  title: string
  repoLabel: string
  language: string
  filesChanged: number
  diffSize: number
  source: string
}

const AGENT_ORDER = [
  'fetch_agent',
  'planner_agent',
  'rag_agent',
  'review_agent',
  'critic_initial',
  'router',
  'branch_agent',
  'critic_branch',
  'false_positive_guard_agent',
  'synthesis_agent',
  'selector_agent',
]

const AGENT_DESCRIPTIONS: Record<string, string> = {
  fetch_agent: 'Load PR metadata and the raw diff.',
  planner_agent: 'Choose review focus and expected risk areas.',
  rag_agent: 'Retrieve local guidance for the detected language.',
  review_agent: 'Generate the initial review candidate.',
  critic_initial: 'Score the initial review candidate and decide whether branching is needed.',
  router: 'Record the branch-or-select routing decision.',
  branch_agent: 'Generate alternative review candidates.',
  critic_branch: 'Score the branch candidates only.',
  false_positive_guard_agent: 'Remove findings without changed-line evidence.',
  synthesis_agent: 'Summarize grounded findings and limitations.',
  selector_agent: 'Choose the final candidate.',
}

const STRATEGY_LABELS: Record<string, string> = {
  initial: 'Balanced Review',
  large_pr_partial: 'Large PR Partial',
  fallback_rate_limited: 'Rate Limit Fallback',
  fallback_unavailable: 'Fallback Review',
  security_focus: 'Security Focus',
  correctness_focus: 'Correctness Focus',
  python_idioms: 'Python Idioms',
  typescript_idioms: 'TypeScript Idioms',
}

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function getScoreConfig(score: number) {
  if (score >= 8) {
    return {
      label: 'Ready to Merge',
      color: '#22c55e',
      barColor: 'linear-gradient(90deg, #16a34a 0%, #4ade80 100%)',
    }
  }

  if (score >= 5) {
    return {
      label: 'Needs Review',
      color: '#eab308',
      barColor: 'linear-gradient(90deg, #ca8a04 0%, #fde047 100%)',
    }
  }

  return {
    label: 'Critical Risk',
    color: '#ef4444',
    barColor: 'linear-gradient(90deg, #dc2626 0%, #fb7185 100%)',
  }
}

export function getStrategyDisplayName(
  candidate?: Pick<Candidate, 'strategy'> | null
) {
  if (!candidate) return 'Unknown Candidate'
  return STRATEGY_LABELS[candidate.strategy] ?? candidate.strategy.replace(/_/g, ' ')
}

export function getIssueSeverityTone(severity: Severity | string): IssueSeverityTone {
  const normalized = String(severity ?? '').toLowerCase()

  if (normalized === 'critical') return 'critical'
  if (normalized === 'warning' || normalized === 'major') return 'major'
  return 'minor'
}

export function getIssueCounts(
  issues: Array<Pick<{ severity: Severity | string }, 'severity'>>
) {
  return issues.reduce(
    (accumulator, issue) => {
      const tone = getIssueSeverityTone(issue.severity)
      accumulator[tone] += 1
      accumulator.total += 1
      return accumulator
    },
    { total: 0, critical: 0, major: 0, minor: 0 }
  )
}

export function formatAgentName(agent: string) {
  if (agent === 'router') return 'Router'
  if (agent === 'critic_initial') return 'Critic Initial'
  if (agent === 'critic_branch') return 'Critic Branch'

  return agent
    .replace(/_agent$/i, '')
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function formatTraceTimestamp(timestamp: string) {
  const parsed = new Date(timestamp)

  if (Number.isNaN(parsed.getTime())) {
    return timestamp || 'Unknown time'
  }

  return parsed.toLocaleString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    month: 'short',
    day: 'numeric',
  })
}

export function formatRelativeTime(timestamp: string) {
  const parsed = new Date(timestamp)
  if (Number.isNaN(parsed.getTime())) return ''

  const diffMs = Date.now() - parsed.getTime()
  const diffSeconds = Math.max(1, Math.round(diffMs / 1000))

  if (diffSeconds < 60) return `${diffSeconds}s ago`

  const diffMinutes = Math.round(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`

  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`

  const diffDays = Math.round(diffHours / 24)
  return `${diffDays}d ago`
}

export function formatDuration(durationMs: number | null) {
  if (durationMs === null || Number.isNaN(durationMs)) return 'n/a'
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`
  if (durationMs < 10000) return `${(durationMs / 1000).toFixed(1)}s`
  return `${Math.round(durationMs / 1000)}s`
}

export function formatDiffSize(size: number) {
  return `${Intl.NumberFormat('en-US').format(size)} chars`
}

export function groupTraceByAgent(entries: TraceEntry[]) {
  const groups: Record<string, TraceEntry[]> = {}

  for (const entry of entries) {
    if (!groups[entry.agent]) groups[entry.agent] = []
    groups[entry.agent].push(entry)
  }

  return groups
}

export function getAgentStatus(entries: TraceEntry[]): AgentStatus {
  if (entries.some(entry => entry.status === 'error')) return 'error'
  if (entries.some(entry => entry.status === 'warning')) return 'warning'
  if (entries.some(entry => entry.status === 'routing')) return 'routing'
  if (
    entries.some(entry => entry.status === 'started') &&
    !entries.some(entry => entry.status === 'completed')
  ) {
    return 'started'
  }
  return 'completed'
}

export function getAgentDurationMs(entries: TraceEntry[]) {
  const timedEntry = [...entries]
    .reverse()
    .find(entry => typeof entry.duration_ms === 'number')
  if (timedEntry) return timedEntry.duration_ms

  const first = new Date(entries[0]?.timestamp ?? '').getTime()
  const last = new Date(entries[entries.length - 1]?.timestamp ?? '').getTime()

  if (Number.isNaN(first) || Number.isNaN(last)) return null
  return Math.max(0, last - first)
}

function parsePrUrl(prUrl: string) {
  try {
    const parsed = new URL(prUrl)
    const parts = parsed.pathname.split('/').filter(Boolean)

    const owner = parts[0] ?? ''
    const repo = parts[1] ?? ''
    const pullSegment = parts.find(part => /^pull$/i.test(part))
    const pullIndex = pullSegment ? parts.indexOf(pullSegment) : -1
    const prNumber = pullIndex >= 0 ? parts[pullIndex + 1] ?? '' : ''

    return { owner, repo, prNumber }
  } catch {
    return { owner: '', repo: '', prNumber: '' }
  }
}

export function formatSourceLabel(prUrl: string) {
  if (prUrl.startsWith('mock://')) return 'Mock PR'
  if (prUrl.startsWith('eval://')) return 'Evaluation Scenario'
  if (prUrl.includes('github.com')) return 'GitHub PR'
  return 'Raw Diff'
}

export function derivePrContext(prMetadata: PRMetadata, diffSize: number): PRContext {
  const { owner, repo, prNumber } = parsePrUrl(prMetadata.pr_url)
  const repoLabel = owner && repo ? `${owner}/${repo}` : repo || prMetadata.title || 'Imported diff'
  const title =
    prMetadata.title ||
    (repo && prNumber ? `${repo} - PR #${prNumber}` : 'Pull Request Review')

  return {
    title,
    repoLabel,
    language: prMetadata.language || 'Unknown',
    filesChanged: prMetadata.files_changed.length,
    diffSize,
    source: formatSourceLabel(prMetadata.pr_url),
  }
}

function summarizeDataValue(value: unknown) {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.join(', ')
  return JSON.stringify(value)
}

export function formatTraceSummary(entry: TraceEntry) {
  const pairs = Object.entries(entry.data ?? {})
  if (pairs.length === 0) {
    return entry.event.replace(/_/g, ' ')
  }

  const preview = pairs
    .slice(0, 3)
    .map(([key, value]) => `${key}=${summarizeDataValue(value)}`)
    .join(' | ')
  return `${entry.event.replace(/_/g, ' ')} | ${preview}`
}

export function buildPipelineSteps(trace: TraceEntry[]): PipelineStep[] {
  const grouped = groupTraceByAgent(trace)
  const presentAgents = Object.keys(grouped)
  const orderedAgents = [
    ...AGENT_ORDER.filter(agent => presentAgents.includes(agent)),
    ...presentAgents.filter(agent => !AGENT_ORDER.includes(agent)),
  ]

  return orderedAgents.map(agent => ({
    id: agent,
    label: formatAgentName(agent),
    description: AGENT_DESCRIPTIONS[agent] ?? 'Captured from backend trace.',
    status: getAgentStatus(grouped[agent]) as TraceStatus,
  }))
}
