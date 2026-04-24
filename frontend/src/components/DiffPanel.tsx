import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { parseDiffFiles, getIssueId } from '../lib/diff'
import { cn, getIssueSeverityTone } from '../lib/utils'
import type { DiffFile, DiffLine, Issue } from '../types'

const FILE_STATUS_LABELS: Record<DiffFile['status'], string> = {
  modified: 'Modified',
  added: 'Added',
  deleted: 'Deleted',
  renamed: 'Renamed',
}

const FILE_STATUS_STYLES: Record<DiffFile['status'], string> = {
  modified: 'border-sky-400/20 bg-sky-400/10 text-sky-300',
  added: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
  deleted: 'border-red-400/20 bg-red-400/10 text-red-300',
  renamed: 'border-violet-400/20 bg-violet-400/10 text-violet-200',
}

const ISSUE_TONE_STYLES = {
  critical: 'border-red-400/20 bg-red-400/10 text-red-300',
  major: 'border-orange-400/20 bg-orange-400/10 text-orange-300',
  minor: 'border-yellow-300/20 bg-yellow-300/10 text-yellow-200',
} as const

const DIFF_LINE_STYLES: Record<DiffLine['type'], string> = {
  added: 'bg-emerald-500/[0.08]',
  removed: 'bg-red-500/[0.08]',
  context: 'bg-transparent',
  meta: 'bg-white/[0.02]',
}

const LANGUAGE_KEYWORDS: Record<string, Set<string>> = {
  ts: new Set(['const', 'let', 'return', 'function', 'if', 'else', 'import', 'from', 'export', 'type', 'interface', 'async', 'await']),
  tsx: new Set(['const', 'let', 'return', 'function', 'if', 'else', 'import', 'from', 'export', 'type', 'interface', 'async', 'await']),
  js: new Set(['const', 'let', 'var', 'return', 'function', 'if', 'else', 'import', 'from', 'export', 'async', 'await']),
  jsx: new Set(['const', 'let', 'var', 'return', 'function', 'if', 'else', 'import', 'from', 'export', 'async', 'await']),
  py: new Set(['def', 'return', 'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'class', 'import', 'from', 'with', 'as', 'pass', 'None', 'True', 'False', 'async', 'await']),
}

const TOKEN_RE =
  /(<!--.*?-->|\/\/.*$|#.*$|"(?:\\.|[^"])*"|'(?:\\.|[^'])*'|`(?:\\.|[^`])*`|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b)/g

function getExtension(filePath: string) {
  return filePath.split('.').pop()?.toLowerCase() ?? ''
}

function highlightCode(content: string, extension: string): ReactNode[] {
  const keywords = LANGUAGE_KEYWORDS[extension] ?? LANGUAGE_KEYWORDS.ts
  const parts: ReactNode[] = []
  let lastIndex = 0

  for (const match of content.matchAll(TOKEN_RE)) {
    const token = match[0]
    const start = match.index ?? 0

    if (start > lastIndex) {
      parts.push(content.slice(lastIndex, start))
    }

    let className = 'text-slate-200'
    if (token.startsWith('//') || token.startsWith('#') || token.startsWith('<!--')) {
      className = 'text-slate-500'
    } else if (token.startsWith('"') || token.startsWith("'") || token.startsWith('`')) {
      className = 'text-emerald-300'
    } else if (/^\d/.test(token)) {
      className = 'text-amber-300'
    } else if (keywords.has(token)) {
      className = 'text-sky-300'
    }

    parts.push(
      <span key={`${start}:${token}`} className={className}>
        {token}
      </span>
    )
    lastIndex = start + token.length
  }

  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex))
  }

  return parts.length > 0 ? parts : [content]
}

function DiffLineMarker({ type }: { type: DiffLine['type'] }) {
  const tone =
    type === 'added'
      ? 'text-emerald-300'
      : type === 'removed'
      ? 'text-red-300'
      : type === 'meta'
      ? 'text-slate-500'
      : 'text-slate-600'

  const marker = type === 'added' ? '+' : type === 'removed' ? '-' : ' '

  return (
    <span className={cn('inline-flex w-4 justify-center font-mono text-xs', tone)}>
      {marker}
    </span>
  )
}

interface DiffLineRowProps {
  line: DiffLine
  extension: string
  isFocused: boolean
  linkedIssues: Issue[]
  registerLine: (lineId: string, node: HTMLDivElement | null) => void
}

const DiffLineRow = memo(function DiffLineRow({
  line,
  extension,
  isFocused,
  linkedIssues,
  registerLine,
}: DiffLineRowProps) {
  return (
    <div
      ref={node => registerLine(line.id, node)}
      className={cn(
        'diff-line group grid min-w-[760px] grid-cols-[72px_72px_minmax(0,1fr)] border-l-2 transition-all duration-200',
        DIFF_LINE_STYLES[line.type],
        isFocused
          ? 'diff-line-focus border-l-emerald-300 shadow-[0_0_0_1px_rgba(52,211,153,0.18)]'
          : line.type === 'added'
          ? 'border-l-emerald-400/20'
          : line.type === 'removed'
          ? 'border-l-red-400/20'
          : 'border-l-transparent'
      )}
    >
      <div className="border-r border-white/5 px-3 py-1.5 text-right font-mono text-xs text-slate-500">
        {line.oldNumber ?? ''}
      </div>
      <div className="border-r border-white/5 px-3 py-1.5 text-right font-mono text-xs text-slate-500">
        {line.newNumber ?? ''}
      </div>
      <div className="min-w-0 px-3 py-1.5">
        <div className="flex items-start gap-3">
          <DiffLineMarker type={line.type} />
          <code className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-[13px] leading-6 text-slate-200">
            {line.type === 'meta' ? (
              <span className="text-slate-500">{line.content}</span>
            ) : (
              highlightCode(line.content, extension)
            )}
          </code>
          {linkedIssues.length > 0 && (
            <div className="hidden shrink-0 flex-wrap justify-end gap-1 lg:flex">
              {linkedIssues.map(issue => {
                const tone = getIssueSeverityTone(issue.severity)
                return (
                  <span
                    key={getIssueId(issue)}
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]',
                      ISSUE_TONE_STYLES[tone]
                    )}
                  >
                    {tone}
                  </span>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
})

interface Props {
  diff: string
  issues: Issue[]
  activeIssueId: string | null
  onActiveIssueChange: (issueId: string | null) => void
}

function DiffPanelComponent({
  diff,
  issues,
  activeIssueId,
  onActiveIssueChange,
}: Props) {
  const lineRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const diffFiles = useMemo(() => parseDiffFiles(diff, issues), [diff, issues])
  const issueMap = useMemo(
    () => new Map(issues.map(issue => [getIssueId(issue), issue])),
    [issues]
  )

  const issueTargets = useMemo(() => {
    const targets = new Map<string, { fileId: string; lineId: string }>()

    for (const file of diffFiles) {
      let firstLineId = ''

      for (const hunk of file.hunks) {
        for (const line of hunk.lines) {
          if (!firstLineId) firstLineId = line.id

          for (const issueId of line.issueIds) {
            if (!targets.has(issueId)) {
              targets.set(issueId, { fileId: file.id, lineId: line.id })
            }
          }
        }
      }

      for (const issue of file.issues) {
        const issueId = getIssueId(issue)
        if (!targets.has(issueId) && firstLineId) {
          targets.set(issueId, { fileId: file.id, lineId: firstLineId })
        }
      }
    }

    return targets
  }, [diffFiles])

  const [selectedFileId, setSelectedFileId] = useState<string | null>(diffFiles[0]?.id ?? null)

  useEffect(() => {
    if (diffFiles.length === 0) {
      setSelectedFileId(null)
      return
    }

    setSelectedFileId(current => {
      if (activeIssueId) {
        const activeTarget = issueTargets.get(activeIssueId)
        if (activeTarget) return activeTarget.fileId
      }

      return diffFiles.some(file => file.id === current) ? current : diffFiles[0].id
    })
  }, [activeIssueId, diffFiles, issueTargets])

  const selectedFile = useMemo(
    () => diffFiles.find(file => file.id === selectedFileId) ?? diffFiles[0] ?? null,
    [diffFiles, selectedFileId]
  )

  const totals = useMemo(
    () =>
      diffFiles.reduce(
        (summary, file) => ({
          additions: summary.additions + file.additions,
          deletions: summary.deletions + file.deletions,
        }),
        { additions: 0, deletions: 0 }
      ),
    [diffFiles]
  )

  useEffect(() => {
    if (!activeIssueId || !selectedFile) return

    const target = issueTargets.get(activeIssueId)
    if (!target || target.fileId !== selectedFile.id) return

    const frame = window.requestAnimationFrame(() => {
      lineRefs.current[target.lineId]?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [activeIssueId, issueTargets, selectedFile])

  const sortedIssues = useMemo(
    () =>
      [...issues].sort((left, right) =>
        `${left.file}:${left.line}`.localeCompare(`${right.file}:${right.line}`)
      ),
    [issues]
  )

  const handleSelectIssue = useCallback(
    (issueId: string) => {
      onActiveIssueChange(issueId)
    },
    [onActiveIssueChange]
  )

  const registerLine = useCallback((lineId: string, node: HTMLDivElement | null) => {
    lineRefs.current[lineId] = node
  }, [])

  if (diffFiles.length === 0) {
    return (
      <section className="surface-panel rounded-3xl p-6">
        <p className="section-label">Diff</p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Code Explorer</h2>
        <p className="mt-3 text-sm leading-7 text-slate-400">
          The backend did not return a diff for this analysis.
        </p>
      </section>
    )
  }

  return (
    <section className="surface-panel rounded-3xl p-6">
      <div className="flex flex-col gap-5 border-b border-white/10 pb-5 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="section-label">Diff</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Code Explorer</h2>
          <p className="mt-2 text-sm text-slate-400">
            Raw diff content returned by the backend, with issue anchors mapped where possible.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl border border-white/10 bg-black/15 px-4 py-3">
            <p className="text-[11px] uppercase tracking-[0.12em] text-slate-500">Files</p>
            <p className="mt-2 text-2xl font-semibold text-white">{diffFiles.length}</p>
          </div>
          <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3">
            <p className="text-[11px] uppercase tracking-[0.12em] text-emerald-200">Added</p>
            <p className="mt-2 text-2xl font-semibold text-white">{totals.additions}</p>
          </div>
          <div className="rounded-2xl border border-red-400/20 bg-red-400/10 px-4 py-3">
            <p className="text-[11px] uppercase tracking-[0.12em] text-red-200">Removed</p>
            <p className="mt-2 text-2xl font-semibold text-white">{totals.deletions}</p>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <div className="rounded-3xl border border-white/10 bg-black/15 p-4">
            <div className="flex items-center justify-between">
              <p className="section-label">Changed Files</p>
              <span className="text-xs text-slate-500">{diffFiles.length} total</span>
            </div>

            <div className="mt-4 space-y-2">
              {diffFiles.map(file => {
                const isSelected = file.id === selectedFile?.id

                return (
                  <button
                    key={file.id}
                    onClick={() => setSelectedFileId(file.id)}
                    className={cn(
                      'card-lift w-full rounded-2xl border p-3 text-left transition-all',
                      isSelected
                        ? 'border-emerald-400/35 bg-emerald-500/10 shadow-[0_18px_48px_rgba(16,185,129,0.14)]'
                        : 'border-white/10 bg-white/[0.03] hover:border-white/20'
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-mono text-sm text-white">{file.path}</p>
                        <p className="mt-2 text-xs text-slate-500">
                          {file.issues.length} issue{file.issues.length === 1 ? '' : 's'}
                        </p>
                      </div>
                      <span
                        className={cn(
                          'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]',
                          FILE_STATUS_STYLES[file.status]
                        )}
                      >
                        {FILE_STATUS_LABELS[file.status]}
                      </span>
                    </div>

                    <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
                      <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-emerald-200">
                        +{file.additions}
                      </span>
                      <span className="rounded-full border border-red-400/20 bg-red-400/10 px-2 py-0.5 text-red-200">
                        -{file.deletions}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="rounded-3xl border border-white/10 bg-black/15 p-4">
            <div className="flex items-center justify-between">
              <p className="section-label">Issue Anchors</p>
              <span className="text-xs text-slate-500">{sortedIssues.length} linked</span>
            </div>

            {sortedIssues.length === 0 ? (
              <p className="mt-4 text-sm leading-7 text-slate-400">
                No structured issues were extracted from the selected review.
              </p>
            ) : (
              <div className="mt-4 space-y-2">
                {sortedIssues.map(issue => {
                  const issueId = getIssueId(issue)
                  const tone = getIssueSeverityTone(issue.severity)
                  const isActive = issueId === activeIssueId

                  return (
                    <button
                      key={issueId}
                      onClick={() => handleSelectIssue(issueId)}
                      className={cn(
                        'w-full rounded-2xl border px-3 py-3 text-left transition-all',
                        isActive
                          ? 'border-emerald-400/30 bg-emerald-500/10 shadow-[0_18px_48px_rgba(16,185,129,0.12)]'
                          : 'border-white/10 bg-white/[0.03] hover:border-white/20'
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em]',
                            ISSUE_TONE_STYLES[tone]
                          )}
                        >
                          {tone}
                        </span>
                        <span className="font-mono text-xs text-slate-300">
                          {issue.file}:{issue.line || '?'}
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-300">{issue.message}</p>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </aside>

        <div className="min-w-0">
          {selectedFile && (
            <div className="overflow-hidden rounded-3xl border border-white/10 bg-black/15">
              <div className="border-b border-white/10 px-5 py-4">
                <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm text-slate-300">
                      {selectedFile.path}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          'rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]',
                          FILE_STATUS_STYLES[selectedFile.status]
                        )}
                      >
                        {FILE_STATUS_LABELS[selectedFile.status]}
                      </span>
                      <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-slate-300">
                        {selectedFile.hunks.length} hunk{selectedFile.hunks.length === 1 ? '' : 's'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="diff-scroll overflow-x-auto">
                {selectedFile.hunks.map(hunk => (
                  <div key={hunk.id} className="border-b border-white/5 last:border-b-0">
                    <div className="sticky top-0 z-10 border-y border-white/5 bg-slate-950/95 px-4 py-2 font-mono text-xs text-sky-300 backdrop-blur">
                      {hunk.header}
                    </div>

                    <div>
                      {hunk.lines.map(line => {
                        const linkedIssues = line.issueIds
                          .map(issueId => issueMap.get(issueId))
                          .filter(Boolean) as Issue[]

                        return (
                          <DiffLineRow
                            key={line.id}
                            line={line}
                            extension={getExtension(selectedFile.path)}
                            isFocused={
                              activeIssueId !== null && line.issueIds.includes(activeIssueId)
                            }
                            linkedIssues={linkedIssues}
                            registerLine={registerLine}
                          />
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

export const DiffPanel = memo(DiffPanelComponent)
