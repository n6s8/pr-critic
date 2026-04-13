import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function getScoreConfig(score: number) {
  if (score >= 9) return { label: 'Excellent',    color: '#22c55e', barColor: '#22c55e' }
  if (score >= 7) return { label: 'Good Quality', color: '#3b82f6', barColor: '#3b82f6' }
  if (score >= 5) return { label: 'Needs Work',   color: '#f97316', barColor: '#f97316' }
  if (score >= 3) return { label: 'High Risk',    color: '#f97316', barColor: '#ef4444' }
  return           { label: 'Critical Risk', color: '#ef4444', barColor: '#ef4444' }
}

export function groupTraceByAgent(entries: import('../types').TraceEntry[]) {
  const groups: Record<string, import('../types').TraceEntry[]> = {}
  for (const entry of entries) {
    if (!groups[entry.agent]) groups[entry.agent] = []
    groups[entry.agent].push(entry)
  }
  return groups
}