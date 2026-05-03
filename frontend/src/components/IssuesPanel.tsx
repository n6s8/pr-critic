import {
  memo,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { getIssueId } from '../lib/diff'
import type { Issue } from '../types'
import { cn, getIssueCounts, getIssueSeverityTone } from '../lib/utils'

const SEVERITY_STYLES = {
  critical: {
    badge: 'border-red-500/30 bg-red-500/10 text-red-300',
    panel:
      'border-red-500/20 bg-red-500/[0.05] hover:border-red-400/30 hover:shadow-[0_18px_48px_rgba(239,68,68,0.08)]',
    title: 'text-red-300',
  },
  major: {
    badge: 'border-orange-500/30 bg-orange-500/10 text-orange-300',
    panel:
      'border-orange-500/20 bg-orange-500/[0.05] hover:border-orange-400/30 hover:shadow-[0_18px_48px_rgba(249,115,22,0.08)]',
    title: 'text-orange-300',
  },
  minor: {
    badge: 'border-yellow-400/30 bg-yellow-400/10 text-yellow-200',
    panel:
      'border-yellow-400/20 bg-yellow-400/[0.05] hover:border-yellow-300/30 hover:shadow-[0_18px_48px_rgba(250,204,21,0.08)]',
    title: 'text-yellow-200',
  },
} as const

const SEVERITY_ORDER = {
  critical: 0,
  major: 1,
  minor: 2,
} as const

type SeverityTone = keyof typeof SEVERITY_STYLES
type SortMode = 'severity' | 'file'

function SeverityIcon({ tone }: { tone: SeverityTone }) {
  const color =
    tone === 'critical'
      ? '#f87171'
      : tone === 'major'
      ? '#fb923c'
      : '#fde047'

  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden="true">
      <path
        d="M10 3L18 17H2L10 3Z"
        fill={color}
        fillOpacity="0.18"
        stroke={color}
        strokeWidth="1.3"
      />
      <path
        d="M10 7V11"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <circle cx="10" cy="14" r="1" fill={color} />
    </svg>
  )
}

interface IssueCardProps {
  issue: Issue
  isActive: boolean
  onSelect: () => void
  onCopy: () => void
  onOpenInDiff: () => void
  copied: boolean
}

const IssueCard = memo(function IssueCard({
  issue,
  isActive,
  onSelect,
  onCopy,
  onOpenInDiff,
  copied,
}: IssueCardProps) {
  const tone = getIssueSeverityTone(issue.severity)
  const styles = SEVERITY_STYLES[tone]

  return (
    <article
      onClick={onSelect}
      className={cn(
        'card-lift h-[116px] cursor-pointer rounded-2xl border p-4 transition duration-200',
        styles.panel,
        isActive && 'ring-2 ring-emerald-400/30'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityIcon tone={tone} />
            <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${styles.badge}`}>
              {tone}
            </span>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] font-mono text-slate-400">
              {issue.issue_type}
            </span>
            <span className="truncate font-mono text-sm text-slate-300">
              {issue.file}:{issue.line}
            </span>
          </div>
          <p className="mt-3 max-h-[44px] overflow-hidden text-sm leading-6 text-slate-300">
            {issue.message}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={event => {
              event.stopPropagation()
              onCopy()
            }}
            title="Copy issue details"
            className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-slate-300 transition hover:bg-white/[0.09]"
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            onClick={event => {
              event.stopPropagation()
              onOpenInDiff()
            }}
            title="Open in diff viewer"
            className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-slate-300 transition hover:bg-white/[0.09]"
          >
            Open diff
          </button>
        </div>
      </div>
    </article>
  )
})

function Section({
  title,
  count,
  tone,
  children,
}: {
  title: string
  count: number
  tone: SeverityTone
  children: ReactNode
}) {
  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${SEVERITY_STYLES[tone].badge}`}>
          {title}
        </span>
        <span className={`text-sm ${SEVERITY_STYLES[tone].title}`}>{count} findings</span>
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function sortIssues(issues: Issue[], mode: SortMode) {
  return [...issues].sort((left, right) => {
    if (mode === 'file') {
      return `${left.file}:${left.line}`.localeCompare(`${right.file}:${right.line}`)
    }

    const leftTone = getIssueSeverityTone(left.severity)
    const rightTone = getIssueSeverityTone(right.severity)

    if (SEVERITY_ORDER[leftTone] !== SEVERITY_ORDER[rightTone]) {
      return SEVERITY_ORDER[leftTone] - SEVERITY_ORDER[rightTone]
    }

    return `${left.file}:${left.line}`.localeCompare(`${right.file}:${right.line}`)
  })
}

interface Props {
  issues: Issue[]
  activeIssueId: string | null
  onSelectIssue: (issueId: string | null) => void
  onOpenInDiff: (issueId: string) => void
}

function IssuesPanelComponent({
  issues,
  activeIssueId,
  onSelectIssue,
  onOpenInDiff,
}: Props) {
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  const [sortMode, setSortMode] = useState<SortMode>('severity')
  const [severityFilters, setSeverityFilters] = useState<Record<SeverityTone, boolean>>({
    critical: true,
    major: true,
    minor: true,
  })
  const [copiedIssueId, setCopiedIssueId] = useState<string | null>(null)
  const [lastOpenedIssueId, setLastOpenedIssueId] = useState<string | null>(null)

  const counts = useMemo(() => getIssueCounts(issues), [issues])

  const filteredIssues = useMemo(() => {
    const normalizedQuery = deferredQuery.trim().toLowerCase()

    return sortIssues(
      issues.filter(issue => {
        const tone = getIssueSeverityTone(issue.severity)
        if (!severityFilters[tone]) return false

        if (!normalizedQuery) return true

        return `${issue.file} ${issue.issue_type} ${issue.message} ${issue.line} ${issue.source_id ?? ''} ${issue.code_snippet ?? ''}`
          .toLowerCase()
          .includes(normalizedQuery)
      }),
      sortMode
    )
  }, [deferredQuery, issues, severityFilters, sortMode])

  useEffect(() => {
    if (filteredIssues.length === 0) {
      onSelectIssue(null)
      return
    }

    if (activeIssueId && filteredIssues.some(issue => getIssueId(issue) === activeIssueId)) {
      return
    }

    onSelectIssue(getIssueId(filteredIssues[0]))
  }, [activeIssueId, filteredIssues, onSelectIssue])

  const selectedIssue = useMemo(
    () => filteredIssues.find(issue => getIssueId(issue) === activeIssueId) ?? null,
    [activeIssueId, filteredIssues]
  )

  const groupedIssues = useMemo(() => {
    return {
      critical: filteredIssues.filter(issue => getIssueSeverityTone(issue.severity) === 'critical'),
      major: filteredIssues.filter(issue => getIssueSeverityTone(issue.severity) === 'major'),
      minor: filteredIssues.filter(issue => getIssueSeverityTone(issue.severity) === 'minor'),
    }
  }, [filteredIssues])

  const handleCopy = async (issue: Issue) => {
    const issueId = getIssueId(issue)
    const evidence = issue.code_snippet ? `\nEvidence: ${issue.code_snippet}` : ''
    const source = issue.source_id ? `\nSource: ${issue.source_id}` : ''
    const payload = `[${getIssueSeverityTone(issue.severity).toUpperCase()}] ${issue.file}:${issue.line}\n${issue.message}${evidence}${source}`

    try {
      await navigator.clipboard.writeText(payload)
    } catch {
      // Keep the UX responsive even if clipboard permissions are unavailable.
    }

    setCopiedIssueId(issueId)
    window.setTimeout(() => {
      setCopiedIssueId(current => (current === issueId ? null : current))
    }, 1800)
  }

  const handleOpenInDiff = (issue: Issue) => {
    const issueId = getIssueId(issue)
    setLastOpenedIssueId(issueId)
    onOpenInDiff(issueId)
  }

  const renderIssueCard = (issue: Issue) => {
    const issueId = getIssueId(issue)

    return (
      <IssueCard
        key={issueId}
        issue={issue}
        isActive={activeIssueId === issueId}
        onSelect={() => onSelectIssue(issueId)}
        onCopy={() => void handleCopy(issue)}
        onOpenInDiff={() => handleOpenInDiff(issue)}
        copied={copiedIssueId === issueId}
      />
    )
  }

  return (
    <section className="surface-panel rounded-3xl p-6">
      <div className="border-b border-white/10 pb-5">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <p className="section-label">Issues</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">Developer Findings</h2>
            <p className="mt-2 text-sm text-slate-400">
              Filter, search, sort, and triage backend issue findings like a daily driver tool.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl border border-white/10 bg-black/15 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.12em] text-slate-500">Total</p>
              <p className="mt-2 text-2xl font-semibold text-white">{counts.total}</p>
            </div>
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.12em] text-red-300">Critical</p>
              <p className="mt-2 text-2xl font-semibold text-white">{counts.critical}</p>
            </div>
            <div className="rounded-2xl border border-orange-500/20 bg-orange-500/10 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.12em] text-orange-300">Major</p>
              <p className="mt-2 text-2xl font-semibold text-white">{counts.major}</p>
            </div>
            <div className="rounded-2xl border border-yellow-400/20 bg-yellow-400/10 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.12em] text-yellow-200">Minor</p>
              <p className="mt-2 text-2xl font-semibold text-white">{counts.minor}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap gap-2">
          {(['critical', 'major', 'minor'] as const).map(tone => (
            <button
              key={tone}
              onClick={() =>
                setSeverityFilters(current => ({
                  ...current,
                  [tone]: !current[tone],
                }))
              }
              className={cn(
                'rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] transition',
                severityFilters[tone]
                  ? SEVERITY_STYLES[tone].badge
                  : 'border-white/10 bg-white/[0.03] text-slate-500'
              )}
            >
              {tone}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search file or message"
            className="h-11 rounded-2xl border border-white/10 bg-black/20 px-4 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-emerald-400/50 focus:ring-2 focus:ring-emerald-400/20"
          />
          <select
            value={sortMode}
            onChange={event => setSortMode(event.target.value as SortMode)}
            className="h-11 rounded-2xl border border-white/10 bg-black/20 px-4 text-sm text-white outline-none transition focus:border-emerald-400/50 focus:ring-2 focus:ring-emerald-400/20"
          >
            <option value="severity">Sort by severity</option>
            <option value="file">Sort by file</option>
          </select>
        </div>
      </div>

      {selectedIssue && (
        <div className="mt-6 rounded-3xl border border-white/10 bg-black/15 p-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${SEVERITY_STYLES[getIssueSeverityTone(selectedIssue.severity)].badge}`}>
                  {getIssueSeverityTone(selectedIssue.severity)}
                </span>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] font-mono text-slate-400">
                  {selectedIssue.issue_type}
                </span>
                <span className="font-mono text-sm text-slate-300">
                  {selectedIssue.file}:{selectedIssue.line}
                </span>
              </div>

              <p className="mt-4 text-sm leading-7 text-slate-200">
                {selectedIssue.message}
              </p>

              {(selectedIssue.code_snippet || selectedIssue.source_id) && (
                <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
                  {selectedIssue.code_snippet && (
                    <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-black/25 p-3 text-xs leading-5 text-slate-300">
                      <code>{selectedIssue.code_snippet}</code>
                    </pre>
                  )}
                  {selectedIssue.source_id && (
                    <span className="h-fit rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 font-mono text-[11px] text-emerald-200">
                      {selectedIssue.source_id}
                    </span>
                  )}
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => void handleCopy(selectedIssue)}
                className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 transition hover:bg-white/[0.09]"
              >
                Copy issue
              </button>
              <button
                onClick={() => handleOpenInDiff(selectedIssue)}
                className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-200 transition hover:bg-white/[0.09]"
              >
                Open in diff
              </button>
            </div>
          </div>

          {lastOpenedIssueId === getIssueId(selectedIssue) && (
            <p className="mt-3 text-xs text-emerald-300">
              Diff viewer synced to this issue anchor.
            </p>
          )}
        </div>
      )}

      {filteredIssues.length === 0 ? (
        <div className="mt-6 rounded-3xl border border-white/10 bg-black/12 p-6">
          <p className="section-label">Issues</p>
          <p className="mt-3 text-sm text-slate-300">No issues found.</p>
        </div>
      ) : (
        <div className="mt-6 space-y-6">
          {(['critical', 'major', 'minor'] as const).map(tone => {
            const sectionIssues = groupedIssues[tone]
            if (sectionIssues.length === 0) return null

            return (
              <Section
                key={tone}
                title={tone}
                count={sectionIssues.length}
                tone={tone}
              >
                {sectionIssues.map(renderIssueCard)}
              </Section>
            )
          })}
        </div>
      )}
    </section>
  )
}

export const IssuesPanel = memo(IssuesPanelComponent)
