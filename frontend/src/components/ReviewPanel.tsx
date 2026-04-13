import type { Strategy } from '../types'

interface SingleProps {
  strategy: Strategy
  review: string
}

function SingleReview({ strategy, review }: SingleProps) {
  const name = strategy?.name ?? 'Unknown'

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border flex-shrink-0">
        <span className="section-label">Review</span>
        <span className="text-[10px] font-medium tracking-wider text-[#999] bg-card border border-border2 px-2 py-0.5 rounded uppercase">
          {name}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="text-[13px] leading-7 text-neutral-400 whitespace-pre-wrap">
          {review ?? ''}
        </div>
      </div>
    </div>
  )
}

interface CompareProps {
  strategies: Strategy[] | undefined
  reviews: Record<string, string>
  onClear: () => void
}

function CompareReview({ strategies, reviews, onClear }: CompareProps) {
  const safeStrategies = strategies ?? []

  if (safeStrategies.length === 0) return null

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-blue-950/20 flex-shrink-0">
        <span className="text-[12px] text-blue-400">
          Comparing {safeStrategies.length} strategies
        </span>

        <button
          onClick={onClear}
          className="ml-auto text-[11px] text-blue-500 border border-blue-800/50 px-2 py-0.5 rounded hover:bg-blue-950/40 transition-colors"
        >
          Exit compare
        </button>
      </div>

      <div
        className="flex-1 overflow-hidden grid"
        style={{ gridTemplateColumns: `repeat(${safeStrategies.length}, 1fr)` }}
      >
        {safeStrategies.map((s, i) => {
          const id = s?.id ?? `s-${i}`
          const name = s?.name ?? 'Unknown'
          const score = s?.score ?? 0
          const description = s?.description ?? ''

          return (
            <div
              key={id}
              className={`flex flex-col overflow-hidden${i < safeStrategies.length - 1 ? ' border-r border-border' : ''}`}
            >
              <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-elevated flex-shrink-0">
                <span className="text-[11px] text-neutral-400 font-medium">
                  {name}
                </span>
                <span className="text-[11px] font-mono text-[#666]">
                  {score.toFixed(2)}
                </span>
              </div>

              <div className="flex-1 overflow-y-auto px-3 py-3">
                <div className="text-[12px] leading-7 text-neutral-400 whitespace-pre-wrap">
                  {reviews[id] ?? '—'}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface Props {
  strategies: Strategy[] | undefined
  activeId: string
  compareIds: string[] | undefined
  review: string
  onClearCompare: () => void
}

export function ReviewPanel({
  strategies,
  activeId,
  compareIds,
  review,
  onClearCompare,
}: Props) {
  const safeStrategies = strategies ?? []
  const safeCompareIds = compareIds ?? []

  const activeStrategy =
    safeStrategies.find(s => s?.id === activeId) ?? null

  if (safeCompareIds.length > 0) {
    const compareStrategies = safeCompareIds
      .map(id => safeStrategies.find(s => s?.id === id))
      .filter(Boolean) as Strategy[]

    const reviews: Record<string, string> = {}

    compareStrategies.forEach((s, i) => {
      const id = s?.id ?? `s-${i}`
      const name = s?.name ?? 'Unknown'
      const score = s?.score ?? 0
      const description = s?.description ?? ''

      reviews[id] =
        id === activeId
          ? review ?? ''
          : `Review for "${name}" strategy.\n\nScore: ${score.toFixed(2)}\n\n${description}\n\n(Full review text available when this strategy is selected.)`
    })

    return (
      <CompareReview
        strategies={compareStrategies}
        reviews={reviews}
        onClear={onClearCompare}
      />
    )
  }

  if (!activeStrategy) {
    return (
      <div className="flex items-center justify-center h-full text-[#444] text-sm">
        Select a strategy
      </div>
    )
  }

  return (
    <SingleReview
      strategy={activeStrategy}
      review={review ?? ''}
    />
  )
}