import { useCallback, useRef, useState } from 'react'
import { analyzeRP, ReviewRequestError } from '../api/analyze'
import type { AnalyzeResponse, ReviewState } from '../types'

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
    activeCandidateIndex: null,
    expandedAgents: {},
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
      activeCandidateIndex: null,
      expandedAgents: {},
      activeIssueId: null,
    }))

    try {
      const data = await analyzeRP(url)

      if (requestIdRef.current !== requestId) return

      setState(current => ({
        ...current,
        data,
        loading: false,
        activeCandidateIndex: data.selected_index,
        expandedAgents: getInitialExpandedAgents(data),
      }))
    } catch (error) {
      if (requestIdRef.current !== requestId) return
      requestIdRef.current = requestId + 1

      let message = error instanceof Error ? error.message : 'Unable to analyze this PR.'
      if (
        error instanceof ReviewRequestError &&
        (
          error.code === 'llm_rate_limited' ||
          error.code === 'rate_limited' ||
          error.statusCode === 429
        )
      ) {
        message = error.retryAfterSeconds
          ? `LLM rate limit reached. Retry in about ${Math.ceil(error.retryAfterSeconds)} seconds.`
          : 'LLM rate limit reached. Please retry shortly.'
      }

      setState(current => ({
        ...current,
        loading: false,
        error: message,
      }))
    }
  }, [])

  const setActiveCandidate = useCallback((index: number) => {
    setState(current => ({ ...current, activeCandidateIndex: index }))
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
    setActiveCandidate,
    setActiveIssue,
    toggleAgent,
    expandAll,
    collapseAll,
  }
}
