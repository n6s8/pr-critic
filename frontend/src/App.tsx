import { useState, useCallback } from 'react'
import type { AnalyzeResponse, LogLevel, TraceFilters } from './types'
import { analyzeRP } from './api/analyze'
import { ScoreCard } from './components/ScoreCard'
import { Pipeline } from './components/Pipeline'
import { StrategyList } from './components/StrategyList'
import { ReviewPanel } from './components/ReviewPanel'
import { IssuesList } from './components/IssuesList'
import { TracePanel } from './components/TracePanel'

interface AppState {
  prUrl: string
  data: AnalyzeResponse | null
  loading: boolean
  error: string | null
  activeStrategyId: string
  compareStrategyIds: string[]
  selectedPipelineAgent: string | null
  traceFilters: TraceFilters
  expandedAgents: Record<string, boolean>
}

export default function App() {
  const [state, setState] = useState<AppState>({
    prUrl: 'mock://pr/security-issue',
    data: null,
    loading: false,
    error: null,
    activeStrategyId: '',
    compareStrategyIds: [],
    selectedPipelineAgent: null,
    traceFilters: { INFO: true, WARN: true, ERROR: true, DEBUG: true },
    expandedAgents: {},
  })

  const handleAnalyze = useCallback(async () => {
    const url = state.prUrl.trim()
    if (!url) return

    setState(s => ({
      ...s,
      loading: true,
      error: null,
      data: null,
      activeStrategyId: '',
      compareStrategyIds: [],
      selectedPipelineAgent: null,
      expandedAgents: {},
    }))

    try {
      const res = await analyzeRP(url)

      // ✅ FIX: normalize backend response
      const normalized: AnalyzeResponse = {
        score: res.score ?? 0,
        issues: res.issues ?? [],
        trace: res.trace ?? [],
        review: res.review ?? '',
        strategies: [
          {
            id: res.selected_strategy ?? 'default',
            name: res.selected_strategy ?? 'Default',
            score: res.score ?? 0,
            description: 'Auto-selected strategy',
          },
        ],
        selected_strategy: res.selected_strategy ?? 'default',
      }

      const agents = [...new Set(normalized.trace.map(t => t.agent))]

      setState(s => ({
        ...s,
        data: normalized,
        loading: false,
        activeStrategyId:
          normalized.selected_strategy ||
          normalized.strategies[0]?.id ||
          '',
        expandedAgents: Object.fromEntries(
          agents.map(a => [a, false])
        ),
      }))
    } catch (err) {
      setState(s => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : 'Request failed',
      }))
    }
  }, [state.prUrl])

  const setActiveStrategy = (id: string) =>
    setState(s => ({ ...s, activeStrategyId: id }))

  const toggleCompare = (id: string) =>
    setState(s => {
      const prev = s.compareStrategyIds
      if (prev.includes(id))
        return { ...s, compareStrategyIds: prev.filter(x => x !== id) }
      if (prev.length >= 2)
        return { ...s, compareStrategyIds: [prev[1], id] }
      return { ...s, compareStrategyIds: [...prev, id] }
    })

  const clearCompare = () =>
    setState(s => ({ ...s, compareStrategyIds: [] }))

  const selectPipelineAgent = (agent: string) =>
    setState(s => {
      const next = s.selectedPipelineAgent === agent ? null : agent

      if (next !== null && s.data) {
        const trace = s.data.trace ?? []
        const agents = [...new Set(trace.map(t => t.agent))]
        const expanded = Object.fromEntries(
          agents.map(a => [a, a === next])
        )
        return { ...s, selectedPipelineAgent: next, expandedAgents: expanded }
      }

      return { ...s, selectedPipelineAgent: next }
    })

  const toggleFilter = (level: LogLevel) =>
    setState(s => ({
      ...s,
      traceFilters: {
        ...s.traceFilters,
        [level]: !s.traceFilters[level],
      },
    }))

  const toggleAgent = (agent: string) =>
    setState(s => ({
      ...s,
      expandedAgents: {
        ...s.expandedAgents,
        [agent]: !s.expandedAgents[agent],
      },
    }))

  const expandAll = () =>
    setState(s => {
      if (!s.data) return s
      const agents = [...new Set(s.data.trace.map(t => t.agent))]
      return {
        ...s,
        expandedAgents: Object.fromEntries(
          agents.map(a => [a, true])
        ),
      }
    })

  const collapseAll = () =>
    setState(s => {
      if (!s.data) return s
      const agents = [...new Set(s.data.trace.map(t => t.agent))]
      return {
        ...s,
        expandedAgents: Object.fromEntries(
          agents.map(a => [a, false])
        ),
      }
    })

  const clearPipelineFilter = () =>
    setState(s => ({ ...s, selectedPipelineAgent: null }))

  const { data, loading, error } = state

  const trace = data?.trace ?? []
  const strategies = data?.strategies ?? []
  const issues = data?.issues ?? []
  const review = data?.review ?? ''

  const triggeredBranch =
    trace.some(t => t.agent === 'branch_agent') ?? false

  return (
    <div className="flex flex-col h-screen bg-[#0a0a0a] overflow-hidden">

      <header className="flex items-center px-4 py-2 border-b border-gray-800">
        <span className="text-sm text-white">PR Review</span>
      </header>

      <div className="p-4 border-b border-gray-800 flex gap-2">
        <input
          value={state.prUrl}
          onChange={e =>
            setState(s => ({ ...s, prUrl: e.target.value }))
          }
          onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
          className="flex-1 bg-black border px-3 py-2 text-white"
        />
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="bg-white text-black px-4"
        >
          {loading ? '...' : 'Analyze'}
        </button>
      </div>

      {loading && <div className="p-4 text-white">Loading...</div>}
      {error && <div className="p-4 text-red-500">{error}</div>}

      {!loading && !error && data && (
        <div className="flex flex-1">

          <aside className="w-[350px] border-r border-gray-800 overflow-auto">
            <ScoreCard data={data} />
            <Pipeline
              trace={trace}
              selectedAgent={state.selectedPipelineAgent}
              onSelect={selectPipelineAgent}
              triggeredBranch={triggeredBranch}
            />
            <StrategyList
              strategies={strategies}
              activeId={state.activeStrategyId}
              compareIds={state.compareStrategyIds}
              onSelect={setActiveStrategy}
              onToggleCompare={toggleCompare}
            />
          </aside>

          <main className="flex-1 overflow-auto">
            <ReviewPanel
              strategies={strategies}
              activeId={state.activeStrategyId}
              compareIds={state.compareStrategyIds}
              review={review}
              onClearCompare={clearCompare}
            />
            <IssuesList issues={issues} />
            <TracePanel
              trace={trace}
              selectedAgent={state.selectedPipelineAgent}
              filters={state.traceFilters}
              expandedAgents={state.expandedAgents}
              onToggleAgent={toggleAgent}
              onToggleFilter={toggleFilter}
              onExpandAll={expandAll}
              onCollapseAll={collapseAll}
              onClearFilter={clearPipelineFilter}
            />
          </main>
        </div>
      )}
    </div>
  )
}