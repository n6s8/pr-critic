import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { TraceEntry } from '../types'
import {
  cn,
  formatAgentName,
  formatDuration,
  formatRelativeTime,
  formatTraceSummary,
  formatTraceTimestamp,
  getAgentDurationMs,
  getAgentStatus,
  groupTraceByAgent,
} from '../lib/utils'

const STATUS_STYLES = {
  completed: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-300',
  warning: 'border-orange-400/20 bg-orange-500/10 text-orange-300',
  error: 'border-red-400/20 bg-red-500/10 text-red-300',
  started: 'border-slate-400/20 bg-slate-500/10 text-slate-300',
  routing: 'border-sky-400/20 bg-sky-500/10 text-sky-300',
} as const

function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      className={cn('h-4 w-4 transition-transform duration-300', expanded && 'rotate-90')}
    >
      <path
        d="M7 5L12 10L7 15"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

interface Props {
  trace: TraceEntry[]
  expandedAgents: Record<string, boolean>
  onToggleAgent: (agent: string) => void
  onExpandAll: () => void
  onCollapseAll: () => void
}

function TracePanelComponent({
  trace,
  expandedAgents,
  onToggleAgent,
  onExpandAll,
  onCollapseAll,
}: Props) {
  const grouped = useMemo(() => groupTraceByAgent(trace), [trace])
  const agents = useMemo(() => Object.keys(grouped), [grouped])
  const latestAgent = agents[agents.length - 1] ?? ''
  const latestAgentRef = useRef<HTMLElement | null>(null)
  const [expandedEntries, setExpandedEntries] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!latestAgent) return

    const latestEntries = grouped[latestAgent] ?? []
    if (latestEntries.length === 0) return

    const latestEntryKey = `${latestAgent}-${latestEntries.length - 1}`
    setExpandedEntries({ [latestEntryKey]: true })
  }, [grouped, latestAgent])

  useEffect(() => {
    if (!latestAgentRef.current) return

    const frame = window.requestAnimationFrame(() => {
      latestAgentRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [latestAgent, trace.length])

  if (trace.length === 0) {
    return (
      <section className="surface-panel rounded-3xl p-6">
        <p className="section-label">Trace</p>
        <p className="mt-4 text-sm text-slate-400">
          No execution trace was returned for this analysis.
        </p>
      </section>
    )
  }

  return (
    <section className="surface-panel rounded-3xl p-6">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 pb-5">
        <div>
          <p className="section-label">Trace</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Execution Timeline</h2>
          <p className="mt-2 text-sm text-slate-400">
            Structured backend trace events grouped by agent.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={onExpandAll}
            className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300 transition hover:bg-white/[0.08]"
          >
            Expand all
          </button>
          <button
            onClick={onCollapseAll}
            className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300 transition hover:bg-white/[0.08]"
          >
            Collapse all
          </button>
        </div>
      </div>

      <div className="mt-6 space-y-4">
        {agents.map(agent => {
          const entries = grouped[agent]
          const isExpanded = expandedAgents[agent] ?? false
          const status = getAgentStatus(entries)
          const duration = formatDuration(getAgentDurationMs(entries))
          const isLatest = agent === latestAgent

          return (
            <article
              key={agent}
              ref={isLatest ? latestAgentRef : undefined}
              className={cn(
                'card-lift relative overflow-hidden rounded-3xl border bg-black/12 transition-all duration-300',
                isLatest
                  ? 'border-emerald-400/20 shadow-[0_18px_56px_rgba(16,185,129,0.12)]'
                  : 'border-white/10'
              )}
            >
              <span className="absolute left-6 top-0 h-full w-px bg-gradient-to-b from-white/0 via-white/10 to-white/0" />

              <button
                onClick={() => onToggleAgent(agent)}
                className="flex w-full items-center gap-4 px-5 py-4 text-left transition hover:bg-white/[0.03]"
              >
                <span
                  className={cn(
                    'relative z-[1] inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-slate-300 transition-all duration-300',
                    isLatest
                      ? 'border-emerald-400/25 bg-emerald-500/10 shadow-[0_0_0_8px_rgba(16,185,129,0.06)]'
                      : 'border-white/10 bg-white/[0.04]'
                  )}
                >
                  {isLatest && <span className="trace-node-pulse absolute inset-0 rounded-full" />}
                  <Chevron expanded={isExpanded} />
                </span>

                <div className="relative min-w-0 flex-1 pl-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-white">
                      {formatAgentName(agent)}
                    </p>
                    {isLatest && (
                      <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-200">
                        Latest
                      </span>
                    )}
                  </div>
                  <p className="mt-1 truncate text-xs text-slate-500">
                    {formatTraceSummary(entries[entries.length - 1])}
                  </p>
                </div>

                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase ${STATUS_STYLES[status]}`}>
                  {status}
                </span>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300">
                  {duration}
                </span>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300">
                  {entries.length} entries
                </span>
              </button>

              <div className={cn('collapsible', isExpanded && 'collapsible-open')}>
                <div className="overflow-hidden">
                  <div className="space-y-4 border-t border-white/10 px-5 py-5">
                    {entries.map((entry, index) => {
                      const entryKey = `${agent}-${index}`
                      const entryExpanded = expandedEntries[entryKey] ?? false
                      const isLatestEntry = isLatest && index === entries.length - 1

                      return (
                        <div key={entryKey} className="trace-entry relative pl-7">
                          <span className="absolute left-[9px] top-0 h-full w-px bg-white/10" />
                          <span
                            className={cn(
                              'absolute left-0 top-3 h-[18px] w-[18px] rounded-full border transition-all duration-300',
                              isLatestEntry
                                ? 'border-emerald-400/30 bg-emerald-500/20 shadow-[0_0_0_8px_rgba(16,185,129,0.08)]'
                                : 'border-white/10 bg-slate-800'
                            )}
                          />

                          <div
                            className={cn(
                              'overflow-hidden rounded-2xl border border-white/10 bg-white/[0.02] transition-all duration-300',
                              isLatestEntry && 'border-emerald-400/20 bg-emerald-500/[0.04]'
                            )}
                          >
                            <button
                              onClick={() =>
                                setExpandedEntries(current => ({
                                  ...current,
                                  [entryKey]: !current[entryKey],
                                }))
                              }
                              className="w-full px-4 py-4 text-left transition hover:bg-white/[0.03]"
                            >
                              <div className="flex flex-wrap items-start gap-3">
                                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                                  <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] font-medium text-slate-200">
                                    [{formatAgentName(entry.agent)}]
                                  </span>
                                  <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${STATUS_STYLES[entry.status]}`}>
                                    [{entry.status}]
                                  </span>
                                  <span
                                    className="text-xs text-slate-500"
                                    title={formatTraceTimestamp(entry.timestamp)}
                                  >
                                    {formatRelativeTime(entry.timestamp) || formatTraceTimestamp(entry.timestamp)}
                                  </span>
                                </div>

                                <span className="shrink-0 text-slate-500">
                                  <Chevron expanded={entryExpanded} />
                                </span>
                              </div>

                              <p className="mt-3 text-sm leading-7 text-slate-200">
                                {formatTraceSummary(entry)}
                              </p>
                            </button>

                            <div
                              className={cn(
                                'collapsible border-t border-white/10 bg-black/15',
                                entryExpanded && 'collapsible-open'
                              )}
                            >
                              <div className="overflow-hidden px-4 py-4">
                                <div className="grid gap-4 md:grid-cols-3">
                                  <div>
                                    <p className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
                                      Event
                                    </p>
                                    <p className="mt-2 text-sm text-slate-200">
                                      {entry.event}
                                    </p>
                                  </div>
                                  <div>
                                    <p className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
                                      Timestamp
                                    </p>
                                    <p className="mt-2 text-sm text-slate-200">
                                      {formatTraceTimestamp(entry.timestamp)}
                                    </p>
                                  </div>
                                  <div>
                                    <p className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
                                      Duration
                                    </p>
                                    <p className="mt-2 text-sm text-slate-200">
                                      {formatDuration(entry.duration_ms)}
                                    </p>
                                  </div>
                                </div>

                                {Object.keys(entry.data).length > 0 && (
                                  <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
                                    <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs leading-6 text-slate-300">
                                      {JSON.stringify(entry.data, null, 2)}
                                    </pre>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}

export const TracePanel = memo(TracePanelComponent)
