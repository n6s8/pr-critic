import { startTransition, useCallback, useMemo, useState } from 'react'
import { Analytics } from '@vercel/analytics/react'
import { DeveloperFooter } from './components/DeveloperFooter'
import { DiffPanel } from './components/DiffPanel'
import { IssuesPanel } from './components/IssuesPanel'
import { MetricsBar } from './components/MetricsBar'
import { PipelineLoader } from './components/PipelineLoader'
import { PRContextHeader } from './components/PRContextHeader'
import { ReviewPanel } from './components/ReviewPanel'
import { StrategyList } from './components/StrategyList'
import { TracePanel } from './components/TracePanel'
import { useReviewState } from './hooks/useReviewState'
import { buildPipelineSteps } from './lib/utils'

type TabKey = 'review' | 'diff' | 'issues' | 'trace'

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'review', label: 'Review' },
  { key: 'diff', label: 'Diff' },
  { key: 'issues', label: 'Issues' },
  { key: 'trace', label: 'Trace' },
]

function LoadingState({ prUrl }: { prUrl: string }) {
  return (
    <div className="surface-panel flex min-h-[420px] flex-col justify-center rounded-3xl p-8">
      <div className="mx-auto w-full max-w-4xl text-center">
        <p className="section-label">Pipeline</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">Analyzing PR...</h2>
        <p className="mt-3 text-sm text-slate-400">
          Waiting for the backend to return the completed review for {prUrl || 'your pull request'}.
        </p>
      </div>
    </div>
  )
}

function EmptyState({
  prUrl,
  loading,
  onPrUrlChange,
  onAnalyze,
}: {
  prUrl: string
  loading: boolean
  onPrUrlChange: (value: string) => void
  onAnalyze: () => void
}) {
  return (
    <section className="surface-panel w-full max-w-4xl rounded-[32px] px-8 py-10 text-center lg:px-12 lg:py-14">
      <p className="section-label">Ready</p>
      <h1 className="mt-4 text-4xl font-semibold tracking-tight text-white lg:text-5xl">
        Analyze a pull request diff
      </h1>
      <p className="mx-auto mt-4 max-w-2xl text-base leading-8 text-slate-400">
        Paste a GitHub PR URL, mock PR URL, or raw diff input to inspect the
        real backend review output, candidate set, trace, and diff content.
      </p>

      <div className="mx-auto mt-8 max-w-3xl rounded-[28px] border border-white/10 bg-black/20 p-4 shadow-[0_24px_64px_rgba(2,6,23,0.28)]">
        <label className="section-label" htmlFor="empty-pr-url-input">
          PR URL or Diff Source
        </label>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row">
          <input
            id="empty-pr-url-input"
            value={prUrl}
            onChange={event => onPrUrlChange(event.target.value)}
            onKeyDown={event => event.key === 'Enter' && onAnalyze()}
            placeholder="https://github.com/org/repo/pull/123"
            className="h-14 flex-1 rounded-2xl border border-white/10 bg-black/25 px-5 text-[15px] text-white outline-none transition placeholder:text-slate-500 focus:border-emerald-400/50 focus:ring-2 focus:ring-emerald-400/20"
          />
          <button
            onClick={onAnalyze}
            disabled={loading}
            className="inline-flex h-14 items-center justify-center rounded-2xl bg-emerald-400 px-6 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-emerald-400/40"
          >
            Analyze
          </button>
        </div>
      </div>
    </section>
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

function ResultTopBar({
  prUrl,
  loading,
  onPrUrlChange,
  onAnalyze,
}: {
  prUrl: string
  loading: boolean
  onPrUrlChange: (value: string) => void
  onAnalyze: () => void
}) {
  return (
    <header className="surface-panel shrink-0 rounded-2xl px-4 py-3 lg:px-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="min-w-0 lg:w-[170px]">
          <p className="section-label">PR Critic</p>
          <p className="mt-1 truncate text-xs text-slate-500">
            Pull request workspace
          </p>
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row">
          <input
            value={prUrl}
            onChange={event => onPrUrlChange(event.target.value)}
            onKeyDown={event => event.key === 'Enter' && onAnalyze()}
            placeholder="https://github.com/org/repo/pull/123"
            className="h-11 flex-1 rounded-2xl border border-white/10 bg-black/20 px-4 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-emerald-400/50 focus:ring-2 focus:ring-emerald-400/20"
          />
          <button
            onClick={onAnalyze}
            disabled={loading}
            className="inline-flex h-11 items-center justify-center rounded-2xl bg-emerald-400 px-5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-emerald-400/40"
          >
            Analyze
          </button>
        </div>
      </div>
    </header>
  )
}

function ExecutionStrip({ steps }: { steps: ReturnType<typeof buildPipelineSteps> }) {
  return (
    <div className="border-b border-white/10 px-6 py-5">
      <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="section-label">Execution</p>
          <p className="mt-2 text-sm text-slate-400">
            This pipeline view is derived directly from the backend trace.
          </p>
        </div>
        <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-200">
          {steps.length} traced stages
        </span>
      </div>
      <div className="mt-4">
        <PipelineLoader steps={steps} compact />
      </div>
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
    activeCandidateIndex,
    expandedAgents,
    activeIssueId,
    setPrUrl,
    analyze,
    setActiveCandidate,
    setActiveIssue,
    toggleAgent,
    expandAll,
    collapseAll,
  } = useReviewState()

  const candidates = useMemo(() => data?.candidates ?? [], [data?.candidates])
  const issues = useMemo(() => data?.issues ?? [], [data?.issues])
  const trace = useMemo(() => data?.trace ?? [], [data?.trace])
  const selectedReview = data?.selected_review ?? null
  const pipelineSteps = useMemo(() => buildPipelineSteps(trace), [trace])

  const activeCandidate = useMemo(
    () =>
      candidates.find(candidate => candidate.index === activeCandidateIndex) ??
      selectedReview ??
      null,
    [activeCandidateIndex, candidates, selectedReview]
  )

  const handleAnalyze = useCallback(() => {
    const nextUrl = prUrl.trim()
    if (!nextUrl) return

    startTransition(() => setActiveTab('review'))
    analyze(nextUrl)
  }, [analyze, prUrl])

  const handleSelectCandidate = useCallback((index: number) => {
    setActiveCandidate(index)
    startTransition(() => setActiveTab('review'))
  }, [setActiveCandidate])

  const handleTabChange = useCallback((tab: TabKey) => {
    startTransition(() => setActiveTab(tab))
  }, [])

  const handleSelectIssue = useCallback((issueId: string | null) => {
    setActiveIssue(issueId)
  }, [setActiveIssue])

  const handleOpenIssueInDiff = useCallback((issueId: string) => {
    setActiveIssue(issueId)
    startTransition(() => setActiveTab('diff'))
  }, [setActiveIssue])

  const showEmptyState = !lastAnalyzedUrl && !loading && !error && !data

  if (showEmptyState) {
    return (
      <div className="bg-app text-slate-100">
        <div className="mx-auto flex min-h-screen max-w-[1700px] flex-col px-4 py-4 lg:px-6 lg:py-5">
          <main className="flex flex-1 items-center justify-center">
            <EmptyState
              prUrl={prUrl}
              loading={loading}
              onPrUrlChange={setPrUrl}
              onAnalyze={handleAnalyze}
            />
          </main>

          <div className="mt-4 shrink-0">
            <DeveloperFooter />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-screen overflow-hidden bg-app text-slate-100">
      <div className="mx-auto grid h-full max-w-[1700px] grid-rows-[auto_minmax(0,1fr)] px-4 py-4 lg:px-6 lg:py-5">
        <ResultTopBar
          prUrl={prUrl}
          loading={loading}
          onPrUrlChange={setPrUrl}
          onAnalyze={handleAnalyze}
        />

        <main className="mt-3 min-h-0 min-w-0 overflow-y-auto pr-1">
          {loading ? (
            <LoadingState prUrl={lastAnalyzedUrl || prUrl} />
          ) : error ? (
            <ErrorState message={error} />
          ) : data ? (
            <section className="surface-panel overflow-hidden rounded-[28px]">
              <PRContextHeader
                prMetadata={data.pr_metadata}
                diffSize={data.diff_size}
              />
              <ExecutionStrip steps={pipelineSteps} />

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

              <MetricsBar
                issues={issues}
                score={data.score}
                candidateCount={candidates.length}
                branchTaken={data.branch_taken}
                branchImprovement={data.branch_improvement}
              />
              <StrategyList
                candidates={candidates}
                activeIndex={activeCandidateIndex}
                selectedIndex={data.selected_index}
                selectorReason={data.selector_reason}
                onSelect={handleSelectCandidate}
              />

              <div key={activeTab} className="tab-panel p-6">
                {activeTab === 'review' && (
                  <ReviewPanel
                    candidate={activeCandidate}
                    isSelected={activeCandidate?.index === data.selected_index}
                    selectorReason={data.selector_reason}
                    retrieval={data.retrieval}
                  />
                )}

                {activeTab === 'diff' && (
                  <DiffPanel
                    diff={data.diff}
                    issues={issues}
                    activeIssueId={activeIssueId}
                    onActiveIssueChange={handleSelectIssue}
                  />
                )}

                {activeTab === 'issues' && (
                  <IssuesPanel
                    issues={issues}
                    activeIssueId={activeIssueId}
                    onSelectIssue={handleSelectIssue}
                    onOpenInDiff={handleOpenIssueInDiff}
                  />
                )}

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
          ) : null}
        </main>
      </div>
      <Analytics />
    </div>
  )
}
