import { cn } from '../lib/utils'
import type { TraceEntry, TraceFilters, LogLevel } from '../types'

const FILTER_LEVELS: LogLevel[] = ['INFO', 'WARN', 'ERROR', 'DEBUG']

const LEVEL_STYLES: Record<LogLevel, { badge: string; row: string; text: string }> = {
  INFO:  { badge: 'text-[#666]',     row: '',                                              text: 'text-[#888]' },
  DEBUG: { badge: 'text-[#3a6a9a]',  row: '',                                              text: 'text-[#666]' },
  WARN:  { badge: 'text-orange-500', row: 'bg-orange-950/20 border-l-2 border-l-orange-900/60', text: 'text-orange-300/80' },
  ERROR: { badge: 'text-red-500',    row: 'bg-red-950/20 border-l-2 border-l-red-900/60',  text: 'text-red-300/80' },
}

const FILTER_ACTIVE_STYLES: Record<LogLevel, string> = {
  INFO:  'text-[#aaa] border-[#444] bg-active',
  WARN:  'text-orange-400 border-orange-900/50 bg-orange-950/20',
  ERROR: 'text-red-400 border-red-900/50 bg-red-950/20',
  DEBUG: 'text-blue-400 border-blue-900/50 bg-blue-950/20',
}

interface AgentGroupProps {
  agent: string
  entries: TraceEntry[]
  isExpanded: boolean
  isHighlighted: boolean
  isDimmed: boolean
  filters: TraceFilters
  onToggle: () => void
}

function AgentGroup({ agent, entries, isExpanded, isHighlighted, isDimmed, filters, onToggle }: AgentGroupProps) {
  const visible = entries.filter(e => filters[e.level])
  const hasWarn  = entries.some(e => e.level === 'WARN')
  const hasError = entries.some(e => e.level === 'ERROR')
  const label = agent.replace('_agent', '').toUpperCase()

  return (
    <div className={cn('border-b border-border transition-opacity', isDimmed && 'opacity-25')}>
      <button
        onClick={onToggle}
        className={cn(
          'w-full flex items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-elevated',
          isHighlighted && 'bg-elevated'
        )}
      >
        <svg
          width="8" height="8" viewBox="0 0 8 8" fill="none"
          className={cn('text-[#444] flex-shrink-0 transition-transform', isExpanded && 'rotate-90')}
        >
          <path d="M2 1L6 4L2 7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>

        <span className={cn(
          'text-[11px] font-medium tracking-widest uppercase transition-colors',
          isHighlighted ? 'text-[#aaa]' : 'text-[#555]'
        )}>
          {label}
        </span>

        <span className="text-[11px] text-[#3a3a3a] font-mono ml-0.5">{entries.length}</span>

        {hasError && <span className="w-1.5 h-1.5 rounded-full bg-red-500 ml-0.5" />}
        {!hasError && hasWarn && <span className="w-1.5 h-1.5 rounded-full bg-orange-400 ml-0.5" />}

        {visible.length !== entries.length && (
          <span className="ml-auto text-[11px] text-[#444] font-mono">{visible.length}/{entries.length}</span>
        )}
      </button>

      {isExpanded && (
        <div>
          {visible.map((entry, i) => {
            const styles = LEVEL_STYLES[entry.level]
            return (
              <div
                key={i}
                className={cn('flex gap-3 py-1 pl-8 pr-4 font-mono text-[12px] leading-5', styles.row)}
              >
                <span className="text-[#3a3a3a] flex-shrink-0 w-[86px] truncate" title={entry.timestamp}>
                  {entry.timestamp.length > 12
                    ? entry.timestamp.slice(11, 23)
                    : entry.timestamp}
                </span>
                <span className={cn('flex-shrink-0 w-[44px] font-semibold text-[11px] pt-[1px]', styles.badge)}>
                  {entry.level}
                </span>
                <span className={cn('flex-1 break-words', styles.text)}>{entry.message}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

interface Props {
  trace: TraceEntry[]
  selectedAgent: string | null
  filters: TraceFilters
  expandedAgents: Record<string, boolean>
  onToggleAgent: (agent: string) => void
  onToggleFilter: (level: LogLevel) => void
  onExpandAll: () => void
  onCollapseAll: () => void
  onClearFilter: () => void
}

export function TracePanel({
  trace, selectedAgent, filters, expandedAgents,
  onToggleAgent, onToggleFilter, onExpandAll, onCollapseAll, onClearFilter,
}: Props) {
  const agents = [...new Set(trace.map(t => t.agent))]
  const grouped: Record<string, TraceEntry[]> = {}
  agents.forEach(a => { grouped[a] = trace.filter(t => t.agent === a) })

  return (
    <div className="flex flex-col flex-shrink-0 border-t border-border">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border flex-wrap">
        <span className="section-label">Agent Trace</span>
        <span className="text-[11px] text-[#444] font-mono">{trace.length} entries</span>

        <div className="flex items-center gap-1 ml-auto flex-wrap">
          {FILTER_LEVELS.map(level => (
            <button
              key={level}
              onClick={() => onToggleFilter(level)}
              className={cn(
                'text-[11px] font-mono font-medium px-2 py-0.5 rounded border transition-all',
                filters[level]
                  ? FILTER_ACTIVE_STYLES[level]
                  : 'text-[#444] border-[#1e1e1e] bg-transparent'
              )}
            >
              {level}
            </button>
          ))}

          <div className="w-px h-3 bg-border2 mx-0.5" />

          <button onClick={onExpandAll}  className="text-[11px] text-[#555] hover:text-[#888] px-1.5 py-0.5 transition-colors">expand all</button>
          <button onClick={onCollapseAll} className="text-[11px] text-[#555] hover:text-[#888] px-1.5 py-0.5 transition-colors">collapse all</button>
        </div>
      </div>

      {/* Active pipeline filter banner */}
      {selectedAgent && (
        <div className="flex items-center gap-2 px-4 py-1.5 bg-emerald-950/20 border-b border-emerald-900/30">
          <span className="text-[11px] text-emerald-500">
            Showing: <span className="font-mono font-medium">{selectedAgent}</span>
          </span>
          <button
            onClick={onClearFilter}
            className="ml-auto text-[11px] text-emerald-600 border border-emerald-900/40 px-2 py-0.5 rounded hover:bg-emerald-950/40 transition-colors"
          >
            clear
          </button>
        </div>
      )}

      {/* Groups */}
      <div>
        {agents.map(agent => (
          <AgentGroup
            key={agent}
            agent={agent}
            entries={grouped[agent]}
            isExpanded={expandedAgents[agent] ?? false}
            isHighlighted={selectedAgent === agent}
            isDimmed={selectedAgent !== null && selectedAgent !== agent}
            filters={filters}
            onToggle={() => onToggleAgent(agent)}
          />
        ))}
      </div>
    </div>
  )
}