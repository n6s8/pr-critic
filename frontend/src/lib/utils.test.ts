import { describe, expect, it } from 'vitest'
import { buildPipelineSteps, formatSourceLabel, getIssueCounts } from './utils'

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

  it('labels source types from the PR URL', () => {
    expect(formatSourceLabel('mock://pr/security-issue')).toBe('Mock PR')
    expect(formatSourceLabel('eval://sec/sql-injection')).toBe('Evaluation Scenario')
    expect(formatSourceLabel('https://github.com/org/repo/pull/1')).toBe('GitHub PR')
  })
})
