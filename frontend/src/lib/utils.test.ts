import { describe, expect, it } from 'vitest'
import {
  buildPipelineSteps,
  formatSourceLabel,
  getIssueCounts,
  getStrategyDisplayName,
} from './utils'

describe('utils', () => {
  it('counts issues by severity tone', () => {
    const counts = getIssueCounts([
      { severity: 'critical' },
      { severity: 'warning' },
      { severity: 'info' },
    ])

    expect(counts).toEqual({
      total: 3,
      critical: 1,
      major: 1,
      minor: 1,
    })
  })

  it('builds pipeline steps directly from trace entries', () => {
    const steps = buildPipelineSteps([
      {
        agent: 'fetch_agent',
        event: 'end',
        status: 'completed',
        timestamp: '2026-01-01T00:00:00Z',
        duration_ms: 10,
        data: {},
      },
      {
        agent: 'router',
        event: 'routing_decision',
        status: 'routing',
        timestamp: '2026-01-01T00:00:01Z',
        duration_ms: null,
        data: { decision: 'branch' },
      },
    ])

    expect(steps.map(step => step.id)).toEqual(['fetch_agent', 'router'])
    expect(steps[1].status).toBe('routing')
  })

  it('keeps distinct critic stages in the pipeline', () => {
    const steps = buildPipelineSteps([
      {
        agent: 'critic_initial',
        event: 'end',
        status: 'completed',
        timestamp: '2026-01-01T00:00:00Z',
        duration_ms: 10,
        data: {},
      },
      {
        agent: 'critic_branch',
        event: 'end',
        status: 'completed',
        timestamp: '2026-01-01T00:00:01Z',
        duration_ms: 12,
        data: {},
      },
    ])

    expect(steps.map(step => step.id)).toEqual(['critic_initial', 'critic_branch'])
  })

  it('orders the upgraded multi-agent flow in graph order', () => {
    const trace = [
      'selector_agent',
      'false_positive_guard_agent',
      'review_agent',
      'planner_agent',
      'fetch_agent',
      'synthesis_agent',
      'rag_agent',
      'critic_initial',
      'router',
    ].map((agent, index) => ({
      agent,
      event: agent === 'router' ? 'routing_decision' : 'end',
      status: agent === 'router' ? 'routing' : 'completed',
      timestamp: `2026-01-01T00:00:0${index}Z`,
      duration_ms: 1,
      data: {},
    } as const))

    const steps = buildPipelineSteps(trace)

    expect(steps.map(step => step.id)).toEqual([
      'fetch_agent',
      'planner_agent',
      'rag_agent',
      'review_agent',
      'critic_initial',
      'router',
      'false_positive_guard_agent',
      'synthesis_agent',
      'selector_agent',
    ])
  })

  it('labels source types from the PR URL', () => {
    expect(formatSourceLabel('mock://pr/security-issue')).toBe('Mock PR')
    expect(formatSourceLabel('eval://sec/sql-injection')).toBe('Evaluation Scenario')
    expect(formatSourceLabel('https://github.com/org/repo/pull/1')).toBe('GitHub PR')
  })

  it('shows a clear label for the rate-limit fallback candidate', () => {
    expect(getStrategyDisplayName({ strategy: 'fallback_rate_limited' })).toBe('Rate Limit Fallback')
  })

  it('shows a clear label for large PR partial candidates', () => {
    expect(getStrategyDisplayName({ strategy: 'large_pr_partial' })).toBe('Large PR Partial')
  })
})
