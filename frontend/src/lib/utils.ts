import { clsx, type ClassValue } from 'clsx'
import type { LogLevel, Severity, Strategy, TraceEntry } from '../types'

export type IssueSeverityTone = 'critical' | 'major' | 'minor'
export type AgentStatus = 'success' | 'error' | 'running'

export interface PRContext {
  title: string
  repoLabel: string
  language: string
  filesChanged: number | null
  diffSize: number | null
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
  strategy?: Pick<Strategy, 'id' | 'name'> | null
) {
  if (!strategy) return 'Unknown Strategy'
  if (strategy.id === 'initial') return 'Balanced Review'
  return strategy.name || strategy.id
}

export function getIssueSeverityTone(severity: Severity | string): IssueSeverityTone {
  const normalized = String(severity ?? '').toLowerCase()

  if (['critical', 'error', 'high', 'blocker'].includes(normalized)) {
    return 'critical'
  }

  if (['major', 'warning', 'warn', 'medium'].includes(normalized)) {
    return 'major'
  }

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

export function formatDiffSize(size: number | null) {
  if (size === null || Number.isNaN(size)) return 'n/a'
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

export function getLevelTone(level: LogLevel) {
  switch (level) {
    case 'ERROR':
      return 'error'
    case 'WARN':
      return 'warn'
    case 'SUCCESS':
      return 'success'
    case 'DEBUG':
      return 'debug'
    default:
      return 'info'
  }
}

export function getAgentStatus(entries: TraceEntry[]): AgentStatus {
  if (entries.some(entry => entry.level === 'ERROR')) return 'error'

  const latestMessage = entries[entries.length - 1]?.message.toLowerCase() ?? ''
  if (
    latestMessage.includes('completed') ||
    latestMessage.includes('routing') ||
    entries.some(entry => entry.level === 'SUCCESS')
  ) {
    return 'success'
  }

  return 'running'
}

function parseDurationFromMessage(message: string) {
  const match = message.match(/\bin\s+([\d.]+)(ms|s)\b/i)
  if (!match) return null

  const value = Number(match[1])
  if (Number.isNaN(value)) return null

  return match[2].toLowerCase() === 's' ? value * 1000 : value
}

export function getAgentDurationMs(entries: TraceEntry[]) {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const parsed = parseDurationFromMessage(entries[index].message)
    if (parsed !== null) return parsed
  }

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
    const rawNumber = pullIndex >= 0 ? parts[pullIndex + 1] ?? '' : ''
    const prNumber = rawNumber.replace(/\.diff$/i, '')

    return { owner, repo, prNumber }
  } catch {
    return { owner: '', repo: '', prNumber: '' }
  }
}

export function derivePrContext(prUrl: string, trace: TraceEntry[]): PRContext {
  const { owner, repo, prNumber } = parsePrUrl(prUrl)
  const combinedMessages = trace.map(entry => entry.message).join(' | ')
  const languageMatch = combinedMessages.match(/language=([^,\s]+)/i)
  const diffMatch = combinedMessages.match(/diff_length=(\d+)/i)
  const filesMatch = combinedMessages.match(/files_changed=\[(.*?)\]/i)

  const filesChanged = filesMatch?.[1]
    ? (filesMatch[1].match(/'[^']+'|"[^"]+"/g) ?? []).length
    : null

  const repoLabel =
    owner && repo ? `${owner}/${repo}` : repo || 'Imported diff'

  return {
    title:
      repo && prNumber
        ? `${repo} - PR #${prNumber}`
        : repo
        ? `${repo} - Pull Request`
        : 'Pull Request Review',
    repoLabel,
    language: languageMatch?.[1] ?? 'Unknown',
    filesChanged,
    diffSize: diffMatch ? Number(diffMatch[1]) : null,
  }
}
