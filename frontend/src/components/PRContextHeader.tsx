import { memo, useMemo } from 'react'
import type { TraceEntry } from '../types'
import { derivePrContext, formatDiffSize } from '../lib/utils'

interface Props {
  prUrl: string
  trace: TraceEntry[]
}

function StatPill({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-sm font-medium text-slate-100">{value}</p>
    </div>
  )
}

function PRContextHeaderComponent({ prUrl, trace }: Props) {
  const context = useMemo(() => derivePrContext(prUrl, trace), [prUrl, trace])

  return (
    <div className="border-b border-white/10 px-6 py-6">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="section-label">Pull Request</p>
          <h2 className="mt-2 text-3xl font-semibold text-white">{context.title}</h2>
          <p className="mt-2 text-sm text-slate-400">
            {context.repoLabel} - imported diff analysis
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatPill label="Language" value={context.language} />
          <StatPill
            label="Files Changed"
            value={
              context.filesChanged === null
                ? 'n/a'
                : String(context.filesChanged)
            }
          />
          <StatPill label="Diff Size" value={formatDiffSize(context.diffSize)} />
          <StatPill label="Source" value="Backend trace" />
        </div>
      </div>
    </div>
  )
}

export const PRContextHeader = memo(PRContextHeaderComponent)
