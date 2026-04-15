import { memo } from 'react'
import { getScoreConfig } from '../lib/utils'

export interface RecentAnalysisItem {
  id: string
  title: string
  subtitle: string
  url: string
  score: number
  source: 'session' | 'sample'
}

interface Props {
  items: RecentAnalysisItem[]
  loading: boolean
  onOpen: (url: string) => void
}

function RecentAnalysesComponent({ items, loading, onOpen }: Props) {
  return (
    <section className="surface-panel rounded-2xl p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="section-label">Recent Analyses</p>
          <p className="mt-1.5 text-xs leading-6 text-slate-500">
            Quick reopen for recent review runs.
          </p>
        </div>
        <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] text-slate-300">
          {items.length}
        </span>
      </div>

      <div className="mt-3 space-y-1.5">
        {items.map(item => {
          const tone = getScoreConfig(item.score)

          return (
            <button
              key={item.id}
              onClick={() => onOpen(item.url)}
              disabled={loading}
              className="group flex w-full items-center justify-between gap-3 rounded-xl px-2.5 py-2.5 text-left transition hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <span
                  className="h-2 w-2 shrink-0 rounded-full transition-transform duration-200 group-hover:scale-125"
                  style={{ backgroundColor: tone.color }}
                />
                <p className="truncate text-sm text-slate-200">{item.title}</p>
              </div>

              <span
                className="rounded-full border px-2.5 py-1 text-[11px] font-semibold"
                style={{
                  color: tone.color,
                  borderColor: `${tone.color}2E`,
                  backgroundColor: `${tone.color}12`,
                }}
              >
                {item.score.toFixed(1)}
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

export const RecentAnalyses = memo(RecentAnalysesComponent)
