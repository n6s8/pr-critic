export type Severity = 'critical' | 'major' | 'minor' | 'warning' | 'info'
export type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'DEBUG' | 'SUCCESS'
export type PipelineStepId = 'fetch' | 'rag' | 'review' | 'critic'
export type PipelineStepStatus = 'pending' | 'loading' | 'success'
export type DiffLineType = 'context' | 'added' | 'removed' | 'meta'
export type DiffFileStatus = 'modified' | 'added' | 'deleted' | 'renamed' | 'generated'
export type DiffSource = 'review' | 'generated'

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

export interface PipelineStep {
  id: PipelineStepId
  label: string
  description: string
  status: PipelineStepStatus
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

export interface DiffLine {
  id: string
  type: DiffLineType
  oldNumber: number | null
  newNumber: number | null
  content: string
  issueIds: string[]
}

export interface DiffHunk {
  id: string
  header: string
  lines: DiffLine[]
}

export interface DiffFile {
  id: string
  path: string
  oldPath: string | null
  newPath: string | null
  status: DiffFileStatus
  source: DiffSource
  additions: number
  deletions: number
  hunks: DiffHunk[]
  issues: Issue[]
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
  pipelineSteps: PipelineStep[]
  activeIssueId: string | null
}
