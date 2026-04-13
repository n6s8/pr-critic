import { useState, useCallback } from 'react'
import type { AnalyzeResponse, LogLevel, ReviewState } from '../types'
import { analyzeRP } from '../api/analyze'

export function useReviewState() {
  const [state, setState] = useState<ReviewState>({
    prUrl: 'https://github.com/acme/platform/pull/1847',
    data: null,
    loading: false,
    error: null,
    activeStrategyId: '',
    compareStrategyIds: [],
    selectedPipelineAgent: null,
    traceFilters: { INFO: true, WARN: true, ERROR: true, DEBUG: true },
    expandedAgents: {},
  })

  const setPrUrl = useCallback((url: string) => {
    setState(s => ({ ...s, prUrl: url }))
  }, [])

  const analyze = useCallback(async (url: string) => {
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
      const data: AnalyzeResponse = await analyzeRP(url)

      const agents = [...new Set((data.trace ?? []).map(t => t.agent))]
      const initialExpanded = Object.fromEntries(
        agents.map(a => [a, false])
      )

      setState(s => ({
        ...s,
        data,
        loading: false,

        // ✅ FIX: используем новый контракт
        activeStrategyId:
          data.activeStrategyId ||
          data.strategies?.[0]?.id ||
          '',

        expandedAgents: initialExpanded,
      }))
    } catch (err) {
      setState(s => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : 'Unknown error',
      }))
    }
  }, [])

  const setActiveStrategy = useCallback((id: string) => {
    setState(s => ({ ...s, activeStrategyId: id }))
  }, [])

  const toggleCompare = useCallback((id: string) => {
    setState(s => {
      const prev = s.compareStrategyIds
      if (prev.includes(id))
        return { ...s, compareStrategyIds: prev.filter(x => x !== id) }
      if (prev.length >= 2)
        return { ...s, compareStrategyIds: [prev[1], id] }
      return { ...s, compareStrategyIds: [...prev, id] }
    })
  }, [])

  const clearCompare = useCallback(() => {
    setState(s => ({ ...s, compareStrategyIds: [] }))
  }, [])

  const selectPipelineAgent = useCallback((agent: string) => {
    setState(s => {
      const next = s.selectedPipelineAgent === agent ? null : agent

      if (next !== null && s.data) {
        const agents = [...new Set((s.data.trace ?? []).map(t => t.agent))]
        const expanded = Object.fromEntries(
          agents.map(a => [a, a === next])
        )
        return {
          ...s,
          selectedPipelineAgent: next,
          expandedAgents: expanded,
        }
      }

      return { ...s, selectedPipelineAgent: next }
    })
  }, [])

  const toggleTraceFilter = useCallback((level: LogLevel) => {
    setState(s => ({
      ...s,
      traceFilters: {
        ...s.traceFilters,
        [level]: !s.traceFilters[level],
      },
    }))
  }, [])

  const toggleAgent = useCallback((agent: string) => {
    setState(s => ({
      ...s,
      expandedAgents: {
        ...s.expandedAgents,
        [agent]: !s.expandedAgents[agent],
      },
    }))
  }, [])

  const expandAll = useCallback(() => {
    setState(s => {
      if (!s.data) return s
      const agents = [...new Set((s.data.trace ?? []).map(t => t.agent))]
      return {
        ...s,
        expandedAgents: Object.fromEntries(
          agents.map(a => [a, true])
        ),
      }
    })
  }, [])

  const collapseAll = useCallback(() => {
    setState(s => {
      if (!s.data) return s
      const agents = [...new Set((s.data.trace ?? []).map(t => t.agent))]
      return {
        ...s,
        expandedAgents: Object.fromEntries(
          agents.map(a => [a, false])
        ),
      }
    })
  }, [])

  return {
    ...state,
    setPrUrl,
    analyze,
    setActiveStrategy,
    toggleCompare,
    clearCompare,
    selectPipelineAgent,
    toggleTraceFilter,
    toggleAgent,
    expandAll,
    collapseAll,
  }
}