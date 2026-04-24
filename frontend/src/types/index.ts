export type Severity = 'critical' | 'warning' | 'info'
export type TraceStatus = 'started' | 'completed' | 'warning' | 'error' | 'routing'
export type DiffLineType = 'context' | 'added' | 'removed' | 'meta'
export type DiffFileStatus = 'modified' | 'added' | 'deleted' | 'renamed'

export interface Issue {
  severity: Severity
  file: string
  line: number
  message: string
}

export interface RetrievalHit {
  source: string
  section: string
  snippet: string
  relevance: number
}

export interface Candidate {
  index: number
  id: string
  strategy: string
  review: string
  score: number
  score_rationale: string
  critic_issues: string[]
}

export interface PRMetadata {
  title: string
  author: string
  base_branch: string
  head_branch: string
  language: string
  files_changed: string[]
  pr_url: string
}

export interface TraceEntry {
  agent: string
  event: string
  status: TraceStatus
  timestamp: string
  duration_ms: number | null
  data: Record<string, unknown>
}

export interface AnalyzeResponse {
  language: string
  files_changed: string[]
  diff_size: number
  pr_metadata: PRMetadata
  diff: string
  retrieval: RetrievalHit[]
  candidates: Candidate[]
  selected_index: number
  selected_review: Candidate
  selector_reason: string
  branch_taken: boolean
  branch_improvement: number | null
  score: number
  issues: Issue[]
  trace: TraceEntry[]
}

export interface PipelineStep {
  id: string
  label: string
  description: string
  status: TraceStatus
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
  activeCandidateIndex: number | null
  expandedAgents: Record<string, boolean>
  activeIssueId: string | null
}
