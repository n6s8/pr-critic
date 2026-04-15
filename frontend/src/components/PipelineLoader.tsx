import { memo } from 'react'
import { cn } from '../lib/utils'
import type { PipelineStep } from '../types'

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4">
      <path
        d="M5 10.5L8.3 13.8L15 7.2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function LoaderDot() {
  return <span className="loading-pulse-dot h-2.5 w-2.5 rounded-full bg-emerald-300" />
}

interface Props {
  steps: PipelineStep[]
  compact?: boolean
}

function PipelineLoaderComponent({ steps, compact = false }: Props) {
  return (
    <div className={cn('grid gap-3 sm:grid-cols-2 xl:grid-cols-4', !compact && 'mt-8')}>
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1

        return (
          <article
            key={step.id}
            className={cn(
              'pipeline-step relative overflow-hidden rounded-2xl border px-4 py-4 transition-all duration-300',
              step.status === 'success'
                ? 'border-emerald-400/30 bg-emerald-500/10 shadow-[0_0_40px_rgba(16,185,129,0.1)]'
                : step.status === 'loading'
                ? 'border-sky-400/30 bg-sky-500/10 shadow-[0_0_40px_rgba(56,189,248,0.08)]'
                : 'border-white/10 bg-white/[0.03]'
            )}
          >
            {!isLast && (
              <span className="pointer-events-none absolute -right-2 top-1/2 hidden h-px w-4 -translate-y-1/2 bg-gradient-to-r from-white/20 to-transparent xl:block" />
            )}

            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white">{step.label}</p>
                {!compact && (
                  <p className="mt-2 text-xs leading-6 text-slate-400">
                    {step.description}
                  </p>
                )}
              </div>

              <span
                className={cn(
                  'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-all duration-300',
                  step.status === 'success'
                    ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300'
                    : step.status === 'loading'
                    ? 'border-sky-400/30 bg-sky-500/10 text-sky-300'
                    : 'border-white/10 bg-black/10 text-slate-500'
                )}
              >
                {step.status === 'success' ? (
                  <CheckIcon />
                ) : step.status === 'loading' ? (
                  <LoaderDot />
                ) : (
                  <span className="text-xs">•</span>
                )}
              </span>
            </div>

            <p className="mt-3 text-xs uppercase tracking-[0.12em] text-slate-500">
              {step.status === 'success'
                ? 'Completed'
                : step.status === 'loading'
                ? 'Running'
                : 'Queued'}
            </p>
          </article>
        )
      })}
    </div>
  )
}

export const PipelineLoader = memo(PipelineLoaderComponent)
