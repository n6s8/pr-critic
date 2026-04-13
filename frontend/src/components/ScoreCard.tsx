import type { AnalyzeResponse } from '../types'
import { getScoreConfig } from '../lib/utils'

interface Props {
  data: AnalyzeResponse | null
}

export function ScoreCard({ data }: Props) {
  if (!data) return null

  const score = data.score ?? 0
  const issues = data.issues ?? []

  const { label, color, barColor } = getScoreConfig(score)
  const pct = (score / 10) * 100

  const critical = issues.filter(i => i?.severity === 'critical').length
  const warning  = issues.filter(i => i?.severity === 'warning').length
  const info     = issues.filter(i => i?.severity === 'info').length

  return (
    <div className="px-4 py-3 border-b border-border">
      <p className="section-label mb-2">Score</p>

      <div className="flex items-baseline gap-1.5 mb-0.5">
        <span className="text-5xl font-light leading-none" style={{ color }}>
          {score}
        </span>
        <span className="text-base text-[#555] leading-none">/ 10</span>
        <span className="text-sm font-medium ml-1.5" style={{ color }}>
          {label}
        </span>
      </div>

      <div className="h-1 bg-[#1e1e1e] rounded-full my-2.5">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {critical > 0 && (
          <span className="text-[11px] px-2 py-0.5 rounded bg-red-950/50 text-red-400 border border-red-900/40">
            {critical} critical
          </span>
        )}
        {warning > 0 && (
          <span className="text-[11px] px-2 py-0.5 rounded bg-orange-950/50 text-orange-400 border border-orange-900/40">
            {warning} warning
          </span>
        )}
        {info > 0 && (
          <span className="text-[11px] px-2 py-0.5 rounded bg-card text-[#777] border border-border2">
            {info} info
          </span>
        )}
      </div>
    </div>
  )
}