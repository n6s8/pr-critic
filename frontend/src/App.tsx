import { startTransition, useMemo, useState } from 'react'
import { IssuesPanel } from './components/IssuesPanel'
import { MetricsBar } from './components/MetricsBar'
import { PipelineLoader } from './components/PipelineLoader'
import { PRContextHeader } from './components/PRContextHeader'
import { ReviewPanel } from './components/ReviewPanel'
import { ScoreCard } from './components/ScoreCard'
import { StrategyList } from './components/StrategyList'
import { TracePanel } from './components/TracePanel'
import { useReviewState } from './hooks/useReviewState'

type TabKey = 'review' | 'issues' | 'trace'

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'review', label: 'Review' },
  { key: 'issues', label: 'Issues' },
  { key: 'trace', label: 'Trace' },
]

function LoadingState() {
  return (
    <div className="surface-panel flex min-h-[420px] flex-col justify-center rounded-3xl p-8">
      <div className="mx-auto w-full max-w-5xl text-center">
        <p className="section-label">Pipeline</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">Analyzing PR...</h2>
        <p className="mt-3 text-sm text-slate-400">
          Running multi-agent pipeline...
        </p>
        <PipelineLoader />
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="surface-panel flex min-h-[420px] flex-col justify-center rounded-3xl p-8">
      <p className="section-label">Ready</p>
      <h2 className="mt-3 text-3xl font-semibold text-white">
        Analyze a pull request diff
      </h2>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
        Paste a GitHub diff URL to inspect score, strategies, structured issues,
        and the full multi-agent timeline in one place.
      </p>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="surface-panel flex min-h-[420px] flex-col justify-center rounded-3xl border border-red-500/30 p-8">
      <p className="section-label">Request Error</p>
      <h2 className="mt-3 text-2xl font-semibold text-white">
        Unable to render review results
      </h2>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300">
        {message}
      </p>
    </div>
  )
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('review')
  const {
    prUrl,
    lastAnalyzedUrl,
    data,
    loading,
    error,
    activeStrategyId,
    expandedAgents,
    setPrUrl,
    analyze,
    setActiveStrategy,
    toggleAgent,
    expandAll,
    collapseAll,
  } = useReviewState()

  const strategies = data?.strategies ?? []
  const issues = data?.issues ?? []
  const trace = data?.trace ?? []
  const review = data?.review ?? ''

  const activeStrategy = useMemo(
    () =>
      strategies.find(strategy => strategy.id === activeStrategyId) ??
      strategies[0] ??
      null,
    [activeStrategyId, strategies]
  )

  const handleAnalyze = () => {
    const nextUrl = prUrl.trim()
    if (!nextUrl) return

    startTransition(() => setActiveTab('review'))
    analyze(nextUrl)
  }

  const handleSelectStrategy = (id: string) => {
    setActiveStrategy(id)
    startTransition(() => setActiveTab('review'))
  }

  const handleTabChange = (tab: TabKey) => {
    startTransition(() => setActiveTab(tab))
  }

  return (
    <div className="h-screen overflow-hidden bg-app text-slate-100">
      <div className="mx-auto flex h-screen max-w-[1700px] flex-col px-4 py-4 lg:px-6">
        <header className="surface-panel shrink-0 rounded-3xl px-5 py-4">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <p className="section-label">PR Critic</p>
              <h1 className="mt-2 text-2xl font-semibold text-white">
                Premium PR review dashboard
              </h1>
              <p className="mt-2 text-sm text-slate-400">
                GitHub-style review workflow with DevTools-style analysis surfaces.
              </p>
            </div>

            <div className="flex w-full max-w-3xl gap-3">
              <input
                value={prUrl}
                onChange={event => setPrUrl(event.target.value)}
                onKeyDown={event => event.key === 'Enter' && handleAnalyze()}
                placeholder="https://github.com/org/repo/pull/123.diff"
                className="h-12 flex-1 rounded-2xl border border-white/10 bg-black/20 px-4 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-emerald-400/50 focus:ring-2 focus:ring-emerald-400/20"
              />
              <button
                onClick={handleAnalyze}
                disabled={loading}
                className="inline-flex h-12 items-center justify-center rounded-2xl bg-emerald-400 px-5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-emerald-400/40"
              >
                Analyze
              </button>
            </div>
          </div>
        </header>

        <div className="mt-4 grid min-h-0 flex-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="min-h-0 overflow-y-auto pr-1">
            <div className="flex flex-col gap-4 lg:sticky lg:top-0">
              <ScoreCard data={data} />
              <StrategyList
                strategies={strategies}
                activeId={activeStrategyId}
                onSelect={handleSelectStrategy}
              />
            </div>
          </aside>

          <main className="min-w-0 min-h-0 overflow-y-auto pr-1">
            {loading ? (
              <LoadingState />
            ) : error ? (
              <ErrorState message={error} />
            ) : !data ? (
              <EmptyState />
            ) : (
              <section className="surface-panel min-h-full overflow-hidden rounded-3xl">
                <PRContextHeader prUrl={lastAnalyzedUrl || prUrl} trace={trace} />
                <div className="flex flex-wrap items-center gap-3 border-b border-white/10 px-6 py-5">
                  {TABS.map(tab => {
                    const count =
                      tab.key === 'issues'
                        ? issues.length
                        : tab.key === 'trace'
                        ? trace.length
                        : undefined

                    return (
                      <button
                        key={tab.key}
                        onClick={() => handleTabChange(tab.key)}
                        className={`tab-button ${activeTab === tab.key ? 'tab-button-active' : ''}`}
                      >
                        <span>{tab.label}</span>
                        {typeof count === 'number' && (
                          <span className="rounded-full bg-black/20 px-2 py-0.5 text-[11px] text-slate-300">
                            {count}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>

                <MetricsBar issues={issues} />

                <div key={activeTab} className="tab-panel p-6">
                  {activeTab === 'review' && (
                    <ReviewPanel strategy={activeStrategy} review={review} />
                  )}

                  {activeTab === 'issues' && <IssuesPanel issues={issues} />}

                  {activeTab === 'trace' && (
                    <TracePanel
                      trace={trace}
                      expandedAgents={expandedAgents}
                      onToggleAgent={toggleAgent}
                      onExpandAll={expandAll}
                      onCollapseAll={collapseAll}
                    />
                  )}
                </div>
              </section>
            )}
          </main>
        </div>
      </div>
    </div>
  )
}
