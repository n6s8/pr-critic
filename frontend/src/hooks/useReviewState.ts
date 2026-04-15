import { useCallback, useRef, useState } from 'react'
import { analyzeRP } from '../api/analyze'
import type {
  AnalyzeResponse,
  LogLevel,
  PipelineStep,
  PipelineStepStatus,
  ReviewState,
} from '../types'

const PIPELINE_BLUEPRINT: Array<Omit<PipelineStep, 'status'>> = [
  {
    id: 'fetch',
    label: 'Fetch',
    description: 'Retrieving pull request metadata and diff context.',
  },
  {
    id: 'rag',
    label: 'Rag',
    description: 'Loading retrieval context and coding guidance.',
  },
  {
    id: 'review',
    label: 'Review',
    description: 'Generating the structured reviewer narrative.',
  },
  {
    id: 'critic',
    label: 'Critic',
    description: 'Scoring quality and finalizing the response.',
  },
]

function createInitialPipelineSteps(): PipelineStep[] {
  return PIPELINE_BLUEPRINT.map(step => ({ ...step, status: 'pending' }))
}

function updatePipelineStepStatus(
  steps: PipelineStep[],
  targetId: PipelineStep['id'],
  status: PipelineStepStatus
) {
  return steps.map(step => (step.id === targetId ? { ...step, status } : step))
}

function wait(ms: number) {
  return new Promise<void>(resolve => {
    window.setTimeout(resolve, ms)
  })
}

function getInitialExpandedAgents(data: AnalyzeResponse) {
  const agents = [...new Set((data.trace ?? []).map(entry => entry.agent))]

  return Object.fromEntries(
    agents.map((agent, index) => [agent, index === agents.length - 1])
  )
}

export function useReviewState() {
  const requestIdRef = useRef(0)
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
    pipelineSteps: createInitialPipelineSteps(),
    activeIssueId: null,
  })

  const setPrUrl = useCallback((url: string) => {
    setState(current => ({ ...current, prUrl: url }))
  }, [])

  const analyze = useCallback(async (url: string) => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId

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
      pipelineSteps: createInitialPipelineSteps(),
      activeIssueId: null,
    }))

    try {
      const pipelinePromise = (async () => {
        for (const step of PIPELINE_BLUEPRINT) {
          if (requestIdRef.current !== requestId) return

          setState(current => ({
            ...current,
            pipelineSteps: updatePipelineStepStatus(current.pipelineSteps, step.id, 'loading'),
          }))

          await wait(300 + Math.floor(Math.random() * 501))

          if (requestIdRef.current !== requestId) return

          setState(current => ({
            ...current,
            pipelineSteps: updatePipelineStepStatus(current.pipelineSteps, step.id, 'success'),
          }))
        }
      })()

      const [data] = await Promise.all([analyzeRP(url), pipelinePromise])

      if (requestIdRef.current !== requestId) return

      setState(current => ({
        ...current,
        data,
        loading: false,
        activeStrategyId:
          data.selected_strategy ||
          data.strategies[0]?.id ||
          '',
        expandedAgents: getInitialExpandedAgents(data),
        pipelineSteps:
          current.pipelineSteps.every(step => step.status === 'success')
            ? current.pipelineSteps
            : createInitialPipelineSteps().map(step => ({ ...step, status: 'success' })),
      }))
    } catch (error) {
      if (requestIdRef.current !== requestId) return
      requestIdRef.current = requestId + 1

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

  const setActiveIssue = useCallback((issueId: string | null) => {
    setState(current => ({ ...current, activeIssueId: issueId }))
  }, [])

  return {
    ...state,
    setPrUrl,
    analyze,
    setActiveStrategy,
    setActiveIssue,
    toggleCompare,
    clearCompare,
    selectPipelineAgent,
    toggleTraceFilter,
    toggleAgent,
    expandAll,
    collapseAll,
  }
}
