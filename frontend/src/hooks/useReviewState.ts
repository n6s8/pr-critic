import { useCallback, useState } from 'react'
import { analyzeRP } from '../api/analyze'
import type { AnalyzeResponse, LogLevel, ReviewState } from '../types'

function getInitialExpandedAgents(data: AnalyzeResponse) {
  const agents = [...new Set((data.trace ?? []).map(entry => entry.agent))]

  return Object.fromEntries(
    agents.map((agent, index) => [agent, index === agents.length - 1])
  )
}

export function useReviewState() {
  const [state, setState] = useState<ReviewState>({
    prUrl: '',
    lastAnalyzedUrl: '',
    data: null,
    loading: false,
    error: null,
    activeStrategyId: '',
    compareStrategyIds: [],
    selectedPipelineAgent: null,
    traceFilters: { INFO: true, WARN: true, ERROR: true, DEBUG: true, SUCCESS: true },
    expandedAgents: {},
  })

  const setPrUrl = useCallback((url: string) => {
    setState(current => ({ ...current, prUrl: url }))
  }, [])

  const analyze = useCallback(async (url: string) => {
    setState(current => ({
      ...current,
      lastAnalyzedUrl: url,
      loading: true,
      error: null,
      data: null,
      activeStrategyId: '',
      compareStrategyIds: [],
      selectedPipelineAgent: null,
      expandedAgents: {},
    }))

    try {
      const data = await analyzeRP(url)

      setState(current => ({
        ...current,
        data,
        loading: false,
        activeStrategyId:
          data.selected_strategy ||
          data.strategies[0]?.id ||
          '',
        expandedAgents: getInitialExpandedAgents(data),
      }))
    } catch (error) {
      setState(current => ({
        ...current,
        loading: false,
        error: error instanceof Error ? error.message : 'Unable to analyze this PR.',
      }))
    }
  }, [])

  const setActiveStrategy = useCallback((id: string) => {
    setState(current => ({ ...current, activeStrategyId: id }))
  }, [])

  const toggleCompare = useCallback((id: string) => {
    setState(current => {
      const previous = current.compareStrategyIds

      if (previous.includes(id)) {
        return {
          ...current,
          compareStrategyIds: previous.filter(value => value !== id),
        }
      }

      if (previous.length >= 2) {
        return {
          ...current,
          compareStrategyIds: [previous[1], id],
        }
      }

      return {
        ...current,
        compareStrategyIds: [...previous, id],
      }
    })
  }, [])

  const clearCompare = useCallback(() => {
    setState(current => ({ ...current, compareStrategyIds: [] }))
  }, [])

  const selectPipelineAgent = useCallback((agent: string) => {
    setState(current => ({
      ...current,
      selectedPipelineAgent:
        current.selectedPipelineAgent === agent ? null : agent,
    }))
  }, [])

  const toggleTraceFilter = useCallback((level: LogLevel) => {
    setState(current => ({
      ...current,
      traceFilters: {
        ...current.traceFilters,
        [level]: !current.traceFilters[level],
      },
    }))
  }, [])

  const toggleAgent = useCallback((agent: string) => {
    setState(current => ({
      ...current,
      expandedAgents: {
        ...current.expandedAgents,
        [agent]: !current.expandedAgents[agent],
      },
    }))
  }, [])

  const expandAll = useCallback(() => {
    setState(current => {
      if (!current.data) return current

      const agents = [...new Set(current.data.trace.map(entry => entry.agent))]

      return {
        ...current,
        expandedAgents: Object.fromEntries(agents.map(agent => [agent, true])),
      }
    })
  }, [])

  const collapseAll = useCallback(() => {
    setState(current => {
      if (!current.data) return current

      const agents = [...new Set(current.data.trace.map(entry => entry.agent))]

      return {
        ...current,
        expandedAgents: Object.fromEntries(agents.map(agent => [agent, false])),
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
