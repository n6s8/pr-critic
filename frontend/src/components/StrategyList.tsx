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
      <section className="surface-panel rounded-3xl p-5">
        <p className="section-label">Strategies</p>
        <p className="mt-3 text-sm text-slate-400">
          Strategy options will appear here after the PR is analyzed.
        </p>
      </section>
    )
  }

  return (
    <section className="surface-panel rounded-3xl p-5">
      <div className="mb-4">
        <p className="section-label">Strategies</p>
        <p className="mt-2 text-sm text-slate-400">
          Select a backend strategy to inspect its review output.
        </p>
      </div>

      <div className="space-y-3">
        {strategies.map((strategy, index) => {
          const isActive = strategy.id === activeId
          const progress = Math.max(0, Math.min((strategy.score / 10) * 100, 100))

          return (
            <button
              key={strategy.id}
              onClick={() => onSelect(strategy.id)}
              title={strategy.description}
              className={cn(
                'card-lift w-full rounded-2xl border p-4 text-left transition-all',
                isActive
                  ? 'border-emerald-400/40 bg-emerald-500/10 shadow-[0_0_0_1px_rgba(52,211,153,0.15),0_18px_48px_rgba(16,185,129,0.15)]'
                  : 'border-white/10 bg-white/[0.03] hover:border-slate-500/40 hover:bg-white/[0.06]'
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-black/20 text-xs text-slate-300">
                      {index + 1}
                    </span>
                    <span className="truncate text-sm font-semibold text-white">
                      {getStrategyDisplayName(strategy)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-400">
                    {strategy.description}
                  </p>
                </div>

                <div className="shrink-0 text-right">
                  <p className="text-sm font-semibold text-white">
                    {strategy.score.toFixed(1)}
                  </p>
                  {isActive && (
                    <span className="mt-2 inline-flex rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-300">
                      Selected
                    </span>
                  )}
                </div>
              </div>

              <div className="mt-4 h-2 rounded-full bg-slate-950/80 ring-1 ring-white/5">
                <div
                  className={cn(
                    'progress-fill h-full rounded-full',
                    isActive ? 'bg-emerald-400' : 'bg-slate-400'
                  )}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}

export const StrategyList = memo(StrategyListComponent)
