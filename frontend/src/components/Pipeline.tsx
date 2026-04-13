import { cn } from '../lib/utils'
import type { TraceEntry } from '../types'

const AGENT_ORDER = ['fetch_agent', 'rag_agent', 'review_agent', 'critic_agent', 'branch_agent', 'selector_agent']
const AGENT_LABELS: Record<string, string> = {
  fetch_agent:    'Fetch',
  rag_agent:      'RAG',
  review_agent:   'Review',
  critic_agent:   'Critic',
  branch_agent:   'Branch',
  selector_agent: 'Select',
}

function CheckIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
      <path d="M1.5 5L4 7.5L8.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

interface Props {
  trace: TraceEntry[]
  selectedAgent: string | null
  onSelect: (agent: string) => void
  triggeredBranch: boolean
}

export function Pipeline({ trace, selectedAgent, onSelect, triggeredBranch }: Props) {
  // Derive which agents appear in the trace
  const presentAgents = [...new Set(trace.map(t => t.agent))]

  // Build pipeline: use known order, but include any unknown agents at the end
  const orderedAgents = [
    ...AGENT_ORDER.filter(a => presentAgents.includes(a)),
    ...presentAgents.filter(a => !AGENT_ORDER.includes(a)),
  ]

  // Per-agent: does it have warnings/errors?
  const agentStatus = (agent: string): 'warn' | 'error' | 'ok' => {
    const entries = trace.filter(t => t.agent === agent)
    if (entries.some(e => e.level === 'ERROR')) return 'error'
    if (entries.some(e => e.level === 'WARN'))  return 'warn'
    return 'ok'
  }

  // Rough timing from timestamps
  const agentTime = (agent: string): string => {
    const entries = trace.filter(t => t.agent === agent)
    if (entries.length < 2) return ''
    try {
      const first = new Date(entries[0].timestamp).getTime()
      const last  = new Date(entries[entries.length - 1].timestamp).getTime()
      const ms = last - first
      if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
      return `${ms}ms`
    } catch {
      return ''
    }
  }

  const totalTime = (() => {
    if (trace.length < 2) return ''
    try {
      const first = new Date(trace[0].timestamp).getTime()
      const last  = new Date(trace[trace.length - 1].timestamp).getTime()
      return `${((last - first) / 1000).toFixed(1)}s`
    } catch { return '' }
  })()

  return (
    <div className="px-4 py-3 border-b border-border">
      <div className="flex items-center justify-between mb-2">
        <p className="section-label">Agent Pipeline</p>
        {totalTime && <span className="text-[11px] text-[#555] font-mono">{totalTime} total</span>}
      </div>

      <div className="space-y-0.5">
        {orderedAgents.map(agent => {
          const isActive = selectedAgent === agent
          const status   = agentStatus(agent)
          const time     = agentTime(agent)
          const label    = AGENT_LABELS[agent] ?? agent.replace('_agent', '')
          const isBranch = agent === 'branch_agent' && triggeredBranch

          return (
            <button
              key={agent}
              onClick={() => onSelect(agent)}
              title={`Filter trace to ${label}`}
              className={cn(
                'w-full flex items-center gap-2.5 px-2 py-1.5 rounded-md text-left transition-all',
                'hover:bg-elevated',
                isActive
                  ? 'bg-active border border-border3'
                  : 'border border-transparent'
              )}
            >
              {/* Status circle */}
              <div className={cn(
                'w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0',
                isActive
                  ? 'bg-neutral-200 text-black'
                  : status === 'error'
                    ? 'bg-red-950/60 text-red-400 border border-red-900/40'
                    : status === 'warn'
                      ? 'bg-[#1e1a10] text-orange-400 border border-orange-900/40'
                      : 'bg-[#1a1a1a] text-neutral-400 border border-[#2a2a2a]'
              )}>
                <CheckIcon />
              </div>

              <span className={cn(
                'flex-1 text-[13px] transition-colors',
                isActive ? 'text-neutral-100' : 'text-neutral-400'
              )}>
                {label}
              </span>

              {isBranch && (
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-orange-950/60 text-orange-400 border border-orange-900/40 uppercase tracking-wide">
                  Branched
                </span>
              )}

              {time && (
                <span className={cn(
                  'text-[11px] font-mono flex-shrink-0',
                  isActive ? 'text-[#888]' : 'text-[#444]'
                )}>
                  {time}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {selectedAgent && (
        <p className="mt-2 text-[11px] text-[#444] italic">Click again to clear filter</p>
      )}
    </div>
  )
}