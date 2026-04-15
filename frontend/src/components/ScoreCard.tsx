import { memo, useMemo } from 'react'
import type { AnalyzeResponse } from '../types'
import { getIssueCounts, getScoreConfig } from '../lib/utils'

interface Props {
  data: AnalyzeResponse | null
}

function ScoreCardComponent({ data }: Props) {
  const counts = useMemo(
    () => getIssueCounts(data?.issues ?? []),
    [data]
  )

  if (!data) {
    return (
      <section className="surface-panel rounded-2xl p-4">
        <p className="section-label">Score</p>
        <p className="mt-3 text-sm text-slate-400">
          Run an analysis to see score, severity mix, and strategy quality.
        </p>
      </section>
    )
  }

  const score = data.score ?? 0
  const progress = Math.max(0, Math.min((score / 10) * 100, 100))
  const { label, color, barColor } = getScoreConfig(score)

  return (
    <section className="surface-panel rounded-2xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="section-label">Quality Score</p>
          <p className="mt-1.5 text-xs leading-6 text-slate-500">
            Backend review confidence and risk signal.
          </p>
        </div>
        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] text-slate-300">
          {data.strategies.length} strategies
        </span>
      </div>

      <div className="mt-5 flex items-end gap-3">
        <span className="score-value text-5xl font-semibold leading-none" style={{ color }}>
          {score.toFixed(1)}
        </span>
        <div className="pb-0.5">
          <p className="text-xs text-slate-400">out of 10</p>
          <p className="text-sm font-medium" style={{ color }}>
            {label}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
          <span>0</span>
          <span>10</span>
        </div>
        <div className="h-2.5 rounded-full bg-slate-950/80 ring-1 ring-white/10">
          <div
            className="progress-fill h-full rounded-full"
            style={{ width: `${progress}%`, background: barColor }}
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2">
          <p className="text-[11px] text-red-300">Critical</p>
          <p className="mt-1 text-base font-semibold text-white">{counts.critical}</p>
        </div>
        <div className="rounded-xl border border-orange-500/20 bg-orange-500/10 px-3 py-2">
          <p className="text-[11px] text-orange-300">Major</p>
          <p className="mt-1 text-base font-semibold text-white">{counts.major}</p>
        </div>
        <div className="rounded-xl border border-yellow-400/20 bg-yellow-400/10 px-3 py-2">
          <p className="text-[11px] text-yellow-200">Minor</p>
          <p className="mt-1 text-base font-semibold text-white">{counts.minor}</p>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-white/10 bg-black/15 px-4 py-3">
        <p className="text-xs uppercase tracking-[0.12em] text-slate-500">
          Total Findings
        </p>
        <div className="mt-2 flex items-center justify-between">
          <p className="text-xs text-slate-400">All structured issues</p>
          <span className="text-base font-semibold text-white">{counts.total}</span>
        </div>
      </div>
    </section>
  )
}

export const ScoreCard = memo(ScoreCardComponent)
