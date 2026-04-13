export type Severity = 'critical' | 'major' | 'minor' | 'warning' | 'info'
export type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'DEBUG' | 'SUCCESS'

export interface TraceFilters {
  INFO: boolean
  WARN: boolean
  ERROR: boolean
  DEBUG: boolean
  SUCCESS: boolean
}

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

export interface ReviewState {
  prUrl: string
  lastAnalyzedUrl: string
  data: AnalyzeResponse | null
  loading: boolean
  error: string | null
  activeStrategyId: string
  compareStrategyIds: string[]
  selectedPipelineAgent: string | null
  traceFilters: TraceFilters
  expandedAgents: Record<string, boolean>
}
