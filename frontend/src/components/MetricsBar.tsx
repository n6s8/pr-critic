import { memo, useMemo } from 'react'
import type { Issue } from '../types'
import { getIssueCounts } from '../lib/utils'

interface Props {
  issues: Issue[]
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string
  value: number
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

function MetricsBarComponent({ issues }: Props) {
  const counts = useMemo(() => getIssueCounts(issues), [issues])

  return (
    <div className="border-b border-white/10 px-6 py-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total Issues" value={counts.total} tone="text-white" />
        <Metric label="Critical" value={counts.critical} tone="text-red-300" />
        <Metric label="Major" value={counts.major} tone="text-orange-300" />
        <Metric label="Minor" value={counts.minor} tone="text-yellow-200" />
      </div>
    </div>
  )
}

export const MetricsBar = memo(MetricsBarComponent)
