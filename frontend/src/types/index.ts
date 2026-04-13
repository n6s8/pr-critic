export type Severity = 'critical' | 'warning' | 'info'
export type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'DEBUG'

export interface Strategy {
  id: string
  name: string
  score: number
  description: string
}

export interface Issue {
  severity: Severity
  file: string
  line: number
  message: string
}

export interface TraceEntry {
  agent: string
  level: LogLevel
  message: string
  timestamp: string
}

export interface AnalyzeResponse {
  score: number
  strategies: Strategy[]
  selected_strategy: string
  review: string
  issues: Issue[]
  trace: TraceEntry[]
}