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

function WarningIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4">
      <path
        d="M10 4.5L16 15.5H4L10 4.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M10 8V11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="10" cy="13.6" r="0.9" fill="currentColor" />
    </svg>
  )
}

function RouteIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4">
      <path
        d="M5 5H12.5C13.9 5 15 6.1 15 7.5V9"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M10.5 13H7.5C6.1 13 5 11.9 5 10.5V9"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path d="M12 11L15 8L18 11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
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
        const tone =
          step.status === 'error'
            ? 'border-red-400/30 bg-red-500/10 text-red-300'
            : step.status === 'warning'
            ? 'border-orange-400/30 bg-orange-500/10 text-orange-300'
            : step.status === 'routing'
            ? 'border-sky-400/30 bg-sky-500/10 text-sky-300'
            : step.status === 'started'
            ? 'border-slate-300/20 bg-white/[0.04] text-slate-300'
            : 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300'

        return (
          <article
            key={step.id}
            className={cn(
              'pipeline-step relative overflow-hidden rounded-2xl border px-4 py-4 transition-all duration-300',
              tone
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
                  tone
                )}
              >
                {step.status === 'warning' || step.status === 'error' ? (
                  <WarningIcon />
                ) : step.status === 'routing' ? (
                  <RouteIcon />
                ) : (
                  <CheckIcon />
                )}
              </span>
            </div>

            <p className="mt-3 text-xs uppercase tracking-[0.12em] text-slate-500">
              {step.status === 'routing'
                ? 'Decision'
                : step.status === 'started'
                ? 'Started'
                : step.status.charAt(0).toUpperCase() + step.status.slice(1)}
            </p>
          </article>
        )
      })}
    </div>
  )
}

export const PipelineLoader = memo(PipelineLoaderComponent)
