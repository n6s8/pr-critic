import { memo } from 'react'
import type { Strategy } from '../types'
import { cn, getStrategyDisplayName } from '../lib/utils'

interface Props {
  strategies: Strategy[]
  activeId: string
  onSelect: (id: string) => void
}

function StrategyListComponent({ strategies, activeId, onSelect }: Props) {
  if (strategies.length === 0) {
    return (
      <section className="border-b border-white/10 px-6 py-5">
        <p className="section-label">Strategies</p>
        <p className="mt-3 text-sm text-slate-400">
          Strategy options will appear here after the PR is analyzed.
        </p>
      </section>
    )
  }

  return (
    <section className="border-b border-white/10 px-6 py-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="section-label">Strategies</p>
          <p className="mt-2 text-sm text-slate-400">
            Switch the active backend strategy without leaving the main workspace.
          </p>
        </div>

        <div className="flex flex-wrap gap-2 xl:max-w-[72%] xl:justify-end">
          {strategies.map((strategy, index) => {
            const isActive = strategy.id === activeId

            return (
              <button
                key={strategy.id}
                onClick={() => onSelect(strategy.id)}
                title={strategy.description}
                className={cn(
                  'rounded-2xl border px-4 py-3 text-left transition-all',
                  isActive
                    ? 'border-emerald-400/35 bg-emerald-500/10 shadow-[0_12px_30px_rgba(16,185,129,0.12)]'
                    : 'border-white/10 bg-white/[0.03] hover:border-slate-500/40 hover:bg-white/[0.06]'
                )}
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-black/20 text-xs text-slate-300">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-white">
                      {getStrategyDisplayName(strategy)}
                    </span>
                    <p className="mt-1 text-xs text-slate-500">
                      {isActive ? 'Selected strategy' : 'Available option'}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-semibold text-white">
                      {strategy.score.toFixed(1)}
                    </p>
                    {isActive && (
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
