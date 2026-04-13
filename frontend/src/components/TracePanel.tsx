import { memo, useEffect, useMemo, useState } from 'react'
import type { TraceEntry } from '../types'
import {
  cn,
  formatAgentName,
  formatDuration,
  formatRelativeTime,
  formatTraceTimestamp,
  getAgentDurationMs,
  getAgentStatus,
  groupTraceByAgent,
} from '../lib/utils'

const LEVEL_STYLES = {
  INFO: 'border-sky-400/20 bg-sky-400/10 text-sky-300',
  WARN: 'border-orange-400/20 bg-orange-400/10 text-orange-300',
  ERROR: 'border-red-400/20 bg-red-400/10 text-red-300',
  DEBUG: 'border-slate-400/20 bg-slate-400/10 text-slate-300',
  SUCCESS: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
} as const

const STATUS_STYLES = {
  success: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-300',
  error: 'border-red-400/20 bg-red-500/10 text-red-300',
  running: 'border-sky-400/20 bg-sky-500/10 text-sky-300',
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
  const [expandedEntries, setExpandedEntries] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!latestAgent) return

    const latestEntries = grouped[latestAgent] ?? []
    if (latestEntries.length === 0) return

    const latestEntryKey = `${latestAgent}-${latestEntries.length - 1}`
    setExpandedEntries({ [latestEntryKey]: true })
  }, [grouped, latestAgent])

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
          <h2 className="mt-2 text-2xl font-semibold text-white">DevTools Timeline</h2>
          <p className="mt-2 text-sm text-slate-400">
            Multi-agent execution rendered as a clickable investigation timeline.
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

          return (
            <article
              key={agent}
              className="card-lift rounded-3xl border border-white/10 bg-black/12"
            >
              <button
                onClick={() => onToggleAgent(agent)}
                className="flex w-full items-center gap-3 px-5 py-4 text-left transition hover:bg-white/[0.03]"
              >
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-300">
                  <Chevron expanded={isExpanded} />
                </span>

                <div className="relative min-w-0 flex-1 pl-5">
                  <span className="absolute left-0 top-0 h-full w-px bg-white/10" />
                  <p className="text-sm font-semibold text-white">
                    {formatAgentName(agent)}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-500">
                    {entries[entries.length - 1]?.message ?? 'No log entries'}
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

                      return (
                        <div key={entryKey} className="relative pl-6">
                          {index < entries.length - 1 && (
                            <span className="absolute left-[7px] top-4 h-[calc(100%+1rem)] w-px bg-white/10" />
                          )}

                          <span className="absolute left-0 top-2.5 h-3.5 w-3.5 rounded-full border border-white/10 bg-slate-800" />

                          <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.02]">
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
                                  <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${LEVEL_STYLES[entry.level]}`}>
                                    [{entry.level}]
                                  </span>
                                  <span className="text-xs text-slate-500" title={formatTraceTimestamp(entry.timestamp)}>
                                    {formatRelativeTime(entry.timestamp) || formatTraceTimestamp(entry.timestamp)}
                                  </span>
                                </div>

                                <span className="shrink-0 text-slate-500">
                                  <Chevron expanded={entryExpanded} />
                                </span>
                              </div>

                              <p className="mt-3 text-sm leading-7 text-slate-200">
                                {entry.message}
                              </p>
                            </button>

                            <div
                              className={cn(
                                'collapsible border-t border-white/10 bg-black/15',
                                entryExpanded && 'collapsible-open'
                              )}
                            >
                              <div className="overflow-hidden px-4 py-4">
                                <div className="grid gap-4 md:grid-cols-2">
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
                                      Relative
                                    </p>
                                    <p className="mt-2 text-sm text-slate-200">
                                      {formatRelativeTime(entry.timestamp) || 'n/a'}
                                    </p>
                                  </div>
                                </div>
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
