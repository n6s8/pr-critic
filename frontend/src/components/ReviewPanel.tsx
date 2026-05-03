import { memo, useMemo } from 'react'
import type { Candidate, RetrievalHit } from '../types'
import { getStrategyDisplayName } from '../lib/utils'

interface ReviewSection {
  title: string
  body: string
}

interface Props {
  candidate: Candidate | null
  isSelected: boolean
  selectorReason: string
  retrieval: RetrievalHit[]
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

function ReviewPanelComponent({
  candidate,
  isSelected,
  selectorReason,
  retrieval,
}: Props) {
  const isFallbackCandidate = candidate?.strategy.startsWith('fallback_') ?? false
  const isRateLimitFallback =
    candidate?.strategy === 'fallback_rate_limited' ||
    candidate?.review.trim() === 'LLM unavailable due to rate limit'
  const sections = useMemo(
    () => parseSections(candidate?.review ?? ''),
    [candidate?.review]
  )

  if (!candidate) {
    return (
      <section className="surface-panel rounded-3xl p-6">
        <p className="text-sm text-slate-400">
          Select a candidate to view the review.
        </p>
      </section>
    )
  }

  return (
    <section className="surface-panel rounded-3xl p-6">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 pb-5">
        <div className="max-w-3xl">
          <p className="section-label">Review</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            {getStrategyDisplayName(candidate)}
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            Exact review text returned for this candidate.
          </p>
          {isSelected && selectorReason && (
            <p className="mt-3 rounded-2xl border border-white/10 bg-black/15 px-4 py-3 text-sm leading-7 text-slate-300">
              {selectorReason}
            </p>
          )}
          {isFallbackCandidate && (
            <p className="mt-3 rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm leading-7 text-amber-100">
              {isRateLimitFallback
                ? 'The provider rate-limited this request. This candidate is a degraded fallback, not a model-generated review.'
                : 'The model review could not be generated cleanly. This candidate is a degraded fallback.'}
            </p>
          )}
        </div>

        <div className="flex flex-col items-end gap-2">
          <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-slate-300">
            Score {candidate.score.toFixed(1)}
          </span>
          {isSelected && (
            <span className="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">
              Selected Candidate
            </span>
          )}
        </div>
      </div>

      {candidate.critic_issues.length > 0 && (
        <div className="mt-6">
          <p className="section-label">Critic Evidence</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {candidate.critic_issues.map(issue => (
              <span
                key={issue}
                className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-slate-300"
              >
                {issue}
              </span>
            ))}
          </div>
        </div>
      )}

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

      <div className="mt-6">
        <div className="flex items-center justify-between">
          <p className="section-label">Based on Retrieved Context</p>
          <span className="text-xs text-slate-500">{retrieval.length} sources</span>
        </div>

        {retrieval.length === 0 ? (
          <p className="mt-3 text-sm text-slate-400">
            No retrieved context was returned for this review.
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            {retrieval.map(hit => (
              <article
                key={`${hit.source}:${hit.section}:${hit.snippet.slice(0, 24)}`}
                className="rounded-2xl border border-white/10 bg-black/15 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-slate-300">
                      {hit.source}
                    </span>
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-slate-400">
                      {hit.section}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500">
                    relevance {hit.relevance.toFixed(2)}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-7 text-slate-300">{hit.snippet}</p>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

export const ReviewPanel = memo(ReviewPanelComponent)
