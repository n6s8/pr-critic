import { memo, useMemo } from 'react'
import type { Strategy } from '../types'
import { getStrategyDisplayName } from '../lib/utils'

interface ReviewSection {
  title: string
  body: string
}

interface Props {
  strategy: Strategy | null
  review: string
}

function parseSections(review: string): ReviewSection[] {
  const normalized = review.replace(/\r\n/g, '\n').trim()
  if (!normalized) return []

  const chunks = normalized.split(/\n(?=##\s+)/g)

  return chunks
    .map(chunk => {
      const trimmed = chunk.trim()
      if (!trimmed) return null

      if (!trimmed.startsWith('## ')) {
        return { title: 'Review', body: trimmed }
      }

      const [heading, ...rest] = trimmed.split('\n')

      return {
        title: heading.replace(/^##\s+/, '').trim(),
        body: rest.join('\n').trim(),
      }
    })
    .filter(Boolean) as ReviewSection[]
}

function renderBody(body: string) {
  const lines = body
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)

  return lines.map((line, index) => {
    if (line.startsWith('- ')) {
      return (
        <div
          key={`${line}-${index}`}
          className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3"
        >
          <div className="flex gap-3">
            <span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-300" />
            <p className="text-sm leading-7 text-slate-300">{line.slice(2)}</p>
          </div>
        </div>
      )
    }

    return (
      <p key={`${line}-${index}`} className="text-sm leading-7 text-slate-300">
        {line}
      </p>
    )
  })
}

function ReviewPanelComponent({ strategy, review }: Props) {
  const sections = useMemo(() => parseSections(review), [review])

  if (!strategy) {
    return (
      <section className="surface-panel rounded-3xl p-6">
        <p className="text-sm text-slate-400">
          Select a strategy to view the review.
        </p>
      </section>
    )
  }

  return (
    <section className="surface-panel rounded-3xl p-6">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 pb-5">
        <div>
          <p className="section-label">Review</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            {getStrategyDisplayName(strategy)}
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            Structured markdown-like review rendered from the backend response.
          </p>
        </div>

        <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-slate-300">
          Score {strategy.score.toFixed(1)}
        </span>
      </div>

      {sections.length === 0 ? (
        <p className="mt-6 text-sm text-slate-400">No review text returned.</p>
      ) : (
        <div className="mt-6 space-y-6">
          {sections.map((section, index) => (
            <article
              key={`${section.title}-${index}`}
              className="card-lift rounded-3xl border border-white/10 bg-black/12 p-5"
            >
              <h3 className="text-lg font-semibold text-white">{section.title}</h3>
              <div className="mt-4 space-y-3">{renderBody(section.body)}</div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export const ReviewPanel = memo(ReviewPanelComponent)
