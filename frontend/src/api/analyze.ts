import type { AnalyzeResponse, Strategy, Issue } from '../types'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

function mapIssues(raw: string[]): Issue[] {
  return (raw ?? []).map((msg, i) => ({
    id: String(i),
    severity: msg.toLowerCase().includes('critical')
      ? 'critical'
      : msg.toLowerCase().includes('major')
      ? 'warning'
      : 'info',
    file: 'unknown',
    line: 0,
    message: msg,
  }))
}

export async function analyzeRP(prUrl: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pr_url: prUrl }),
  })

  const data = await res.json()

  // 🔥 transform backend → frontend format
  const strategies: Strategy[] = (data.candidates ?? []).map((c: any) => ({
    id: c.strategy,
    name: c.strategy,
    score: c.score / 10, // normalize if needed
    description: c.score_rationale ?? '',
  }))

  const active = strategies[0]

  return {
    score: data.best_score ?? 0,
    review: data.best_review ?? '',
    issues: mapIssues(data.candidates?.[0]?.issues ?? []),
    strategies,
    trace: data.trace ?? [],
    activeStrategyId: active?.id ?? '',
  }
}