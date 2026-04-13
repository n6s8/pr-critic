import { memo, useEffect, useState } from 'react'
import { cn } from '../lib/utils'

const PIPELINE_STEPS = ['Fetch', 'Rag', 'Review', 'Critic'] as const

type StepState = 'idle' | 'loading' | 'success'

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

function PipelineLoaderComponent() {
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    const interval = window.setInterval(() => {
      setActiveIndex(current =>
        current >= PIPELINE_STEPS.length - 1 ? current : current + 1
      )
    }, 650)

    return () => window.clearInterval(interval)
  }, [])

  return (
    <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {PIPELINE_STEPS.map((step, index) => {
        const state: StepState =
          index < activeIndex ? 'success' : index === activeIndex ? 'loading' : 'idle'

        return (
          <div
            key={step}
            className={cn(
              'rounded-2xl border px-4 py-4 transition-all duration-300',
              state === 'success'
                ? 'border-emerald-400/30 bg-emerald-500/10 shadow-[0_0_40px_rgba(16,185,129,0.1)]'
                : state === 'loading'
                ? 'border-sky-400/30 bg-sky-500/10 shadow-[0_0_40px_rgba(56,189,248,0.08)]'
                : 'border-white/10 bg-white/[0.03]'
            )}
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-white">{step}</p>
              <span
                className={cn(
                  'inline-flex h-7 w-7 items-center justify-center rounded-full border',
                  state === 'success'
                    ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300'
                    : state === 'loading'
                    ? 'border-sky-400/30 bg-sky-500/10 text-sky-300'
                    : 'border-white/10 bg-black/10 text-slate-500'
                )}
              >
                {state === 'success' ? <CheckIcon /> : state === 'loading' ? <LoaderDot /> : <span className="text-xs">•</span>}
              </span>
            </div>

            <p className="mt-3 text-xs uppercase tracking-[0.12em] text-slate-500">
              {state === 'success'
                ? 'Completed'
                : state === 'loading'
                ? 'Running'
                : 'Queued'}
            </p>
          </div>
        )
      })}
    </div>
  )
}

export const PipelineLoader = memo(PipelineLoaderComponent)
