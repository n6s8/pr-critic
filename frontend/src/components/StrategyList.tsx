import { memo } from 'react'
import type { Candidate } from '../types'
import { cn, getStrategyDisplayName } from '../lib/utils'

interface Props {
  candidates: Candidate[]
  activeIndex: number | null
  selectedIndex: number
  selectorReason: string
  onSelect: (index: number) => void
}

function StrategyListComponent({
  candidates,
  activeIndex,
  selectedIndex,
  selectorReason,
  onSelect,
}: Props) {
  if (candidates.length === 0) {
    return (
      <section className="border-b border-white/10 px-6 py-5">
        <p className="section-label">Candidates</p>
        <p className="mt-3 text-sm text-slate-400">
          Review candidates will appear here after the PR is analyzed.
        </p>
      </section>
    )
  }

  return (
    <section className="border-b border-white/10 px-6 py-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-2xl">
          <p className="section-label">Candidates</p>
          <p className="mt-2 text-sm text-slate-400">
            These are the actual backend-generated review candidates. The selector
            chose candidate {selectedIndex + 1}.
          </p>
          {selectorReason && (
            <p className="mt-3 rounded-2xl border border-white/10 bg-black/15 px-4 py-3 text-sm leading-7 text-slate-300">
              {selectorReason}
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2 xl:max-w-[72%] xl:justify-end">
          {candidates.map(candidate => {
            const isActive = candidate.index === activeIndex
            const isSelected = candidate.index === selectedIndex

            return (
              <button
                key={candidate.id}
                onClick={() => onSelect(candidate.index)}
                className={cn(
                  'rounded-2xl border px-4 py-3 text-left transition-all',
                  isActive
                    ? 'border-emerald-400/35 bg-emerald-500/10 shadow-[0_12px_30px_rgba(16,185,129,0.12)]'
                    : 'border-white/10 bg-white/[0.03] hover:border-slate-500/40 hover:bg-white/[0.06]'
                )}
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-black/20 text-xs text-slate-300">
                    {candidate.index + 1}
                  </span>
                  <div className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-white">
                      {getStrategyDisplayName(candidate)}
                    </span>
                    <p className="mt-1 text-xs text-slate-500">
                      {isSelected ? 'Selector choice' : 'Alternative candidate'}
                    </p>
                    {candidate.score_rationale && (
                      <p className="mt-2 max-w-[260px] text-xs leading-5 text-slate-400">
                        {candidate.score_rationale}
                      </p>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-semibold text-white">
                      {candidate.score.toFixed(1)}
                    </p>
                    {isSelected && (
                      <span className="mt-1 inline-flex rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                        Selected
                      </span>
                    )}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </section>
  )
}

export const StrategyList = memo(StrategyListComponent)
