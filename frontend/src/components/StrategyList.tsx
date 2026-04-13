import { cn } from '../lib/utils'
import type { Strategy } from '../types'

interface CardProps {
  strategy: Strategy
  rank: number
  isActive: boolean
  isInCompare: boolean
  onSelect: () => void
  onToggleCompare: () => void
}

function StrategyCard({ strategy, rank, isActive, isInCompare, onSelect, onToggleCompare }: CardProps) {
  const score = strategy?.score ?? 0
  const name = strategy?.name ?? 'Unknown'
  const description = strategy?.description ?? ''

  return (
    <div
      onClick={onSelect}
      className={cn(
        'group relative rounded-md mb-1.5 cursor-pointer transition-all',
        isActive
          ? 'bg-[#1c1c1c] border border-border3'
          : 'border border-transparent hover:bg-elevated',
        isInCompare && !isActive
          ? 'border border-blue-900/50 bg-blue-950/10'
          : ''
      )}
    >
      <div className="px-3 py-2.5">
        {/* Rank + name + score */}
        <div className="flex items-center gap-2 mb-1">
          <div className={cn(
            'w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-[11px] font-medium transition-colors',
            isActive ? 'bg-neutral-100 text-black' : 'bg-[#1e1e1e] text-[#777] border border-[#2a2a2a]'
          )}>
            {rank}
          </div>

          <span className={cn(
            'flex-1 text-[13px] font-medium transition-colors',
            isActive ? 'text-neutral-100' : 'text-neutral-400'
          )}>
            {name}
          </span>

          <span className={cn(
            'text-[13px] font-mono font-medium transition-colors',
            isActive ? 'text-neutral-100' : 'text-[#666]'
          )}>
            {score.toFixed(2)}
          </span>
        </div>

        {/* Score bar */}
        <div className="h-0.5 bg-[#1e1e1e] rounded-full mb-2">
          <div
            className={cn('h-full rounded-full transition-all', isActive ? 'bg-neutral-200' : 'bg-[#333]')}
            style={{ width: `${Math.min(score * 100, 100)}%` }}
          />
        </div>

        {/* Description */}
        <p className={cn(
          'text-[11px] leading-relaxed transition-colors',
          isActive ? 'text-[#888]' : 'text-[#555]'
        )}>
          {description}
        </p>
      </div>

      {/* Compare button */}
      <button
        onClick={e => { e.stopPropagation(); onToggleCompare() }}
        className={cn(
          'absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] font-medium transition-all border',
          'opacity-0 group-hover:opacity-100',
          isInCompare
            ? 'opacity-100 bg-blue-950/60 border-blue-800/50 text-blue-400'
            : 'bg-card border-border2 text-[#666] hover:text-[#aaa]'
        )}
        title={isInCompare ? 'Remove from compare' : 'Add to compare'}
      >
        {isInCompare ? 'comparing' : 'compare'}
      </button>
    </div>
  )
}

interface Props {
  strategies: Strategy[] | undefined
  activeId: string
  compareIds: string[] | undefined
  onSelect: (id: string) => void
  onToggleCompare: (id: string) => void
}

export function StrategyList({ strategies, activeId, compareIds, onSelect, onToggleCompare }: Props) {
  const safeStrategies = strategies ?? []
  const safeCompareIds = compareIds ?? []

  if (safeStrategies.length === 0) {
    return (
      <div className="px-4 py-3 text-sm text-gray-500">
        No strategies
      </div>
    )
  }

  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <p className="section-label">Strategies</p>
        {safeCompareIds.length > 0 && (
          <span className="text-[11px] text-blue-500">{safeCompareIds.length} selected</span>
        )}
      </div>

      {safeStrategies.map((s, i) => (
        <StrategyCard
          key={s?.id ?? i}
          strategy={s}
          rank={i + 1}
          isActive={activeId === s?.id}
          isInCompare={safeCompareIds.includes(s?.id)}
          onSelect={() => onSelect(s?.id)}
          onToggleCompare={() => onToggleCompare(s?.id)}
        />
      ))}
    </div>
  )
}