import { memo } from 'react'
import type { Issue } from '../types'
import { getIssueCounts, getScoreConfig } from '../lib/utils'

interface Props {
  issues: Issue[]
  score: number
  candidateCount: number
  branchTaken: boolean
  branchImprovement: number | null
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string
  value: string | number
  tone: string
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/15 px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
        {label}
      </p>
      <p className={`mt-2 text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  )
}

function formatDelta(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

function MetricsBarComponent({
  issues,
  score,
  candidateCount,
  branchTaken,
  branchImprovement,
}: Props) {
  const counts = getIssueCounts(issues)
  const scoreTone = getScoreConfig(score)
  const primaryGridClass =
    branchImprovement !== null
      ? 'grid gap-3 sm:grid-cols-2 xl:grid-cols-5'
      : 'grid gap-3 sm:grid-cols-2 xl:grid-cols-4'

  return (
    <div className="border-b border-white/10 px-6 py-4">
      <div className={primaryGridClass}>
        <Metric label="Selected Score" value={score.toFixed(1)} tone="text-white" />
        <Metric label="Risk Label" value={scoreTone.label} tone="text-slate-200" />
        <Metric label="Candidates" value={candidateCount} tone="text-emerald-300" />
        <Metric label="Branch Path" value={branchTaken ? 'Taken' : 'Skipped'} tone={branchTaken ? 'text-orange-300' : 'text-sky-300'} />
        {branchImprovement !== null && (
          <Metric
            label="Branch Delta"
            value={formatDelta(branchImprovement)}
            tone={branchImprovement >= 0 ? 'text-emerald-300' : 'text-red-300'}
          />
        )}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total Issues" value={counts.total} tone="text-white" />
        <Metric label="Critical" value={counts.critical} tone="text-red-300" />
        <Metric label="Major" value={counts.major} tone="text-orange-300" />
        <Metric label="Minor" value={counts.minor} tone="text-yellow-200" />
      </div>
    </div>
  )
}

export const MetricsBar = memo(MetricsBarComponent)
