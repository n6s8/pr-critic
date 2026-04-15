import type { DiffFile, DiffHunk, DiffLine, DiffFileStatus, Issue, TraceEntry } from '../types'

const DIFF_FENCE_RE = /```diff\s*([\s\S]*?)```/gi
const DIFF_START_RE = /^diff --git\s+a\/(.+?)\s+b\/(.+)$/i
const HUNK_HEADER_RE = /^@@\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s*@@(.*)$/
const FILES_CHANGED_RE = /files_changed=\[(.*?)\]/i

function normalizePath(value: string | null | undefined) {
  return String(value ?? '')
    .replace(/^(a|b)\//, '')
    .replace(/^["']|["']$/g, '')
    .trim()
}

function getPreferredPath(
  oldPath: string | null,
  newPath: string | null,
  status: DiffFileStatus
) {
  if (status === 'deleted') return oldPath || newPath || 'unknown'
  return newPath || oldPath || 'unknown'
}

function isFileMatch(diffPath: string, issuePath: string) {
  const normalizedDiff = normalizePath(diffPath)
  const normalizedIssue = normalizePath(issuePath)

  if (!normalizedDiff || !normalizedIssue) return false
  return (
    normalizedDiff === normalizedIssue ||
    normalizedDiff.endsWith(`/${normalizedIssue}`) ||
    normalizedIssue.endsWith(`/${normalizedDiff}`)
  )
}

function createLine(
  filePath: string,
  issueIdsByLine: Map<number, string[]>,
  index: number,
  type: DiffLine['type'],
  oldNumber: number | null,
  newNumber: number | null,
  content: string
): DiffLine {
  const lineKey = newNumber ?? oldNumber ?? -1

  return {
    id: `${filePath}:${index}:${oldNumber ?? 'x'}:${newNumber ?? 'x'}`,
    type,
    oldNumber,
    newNumber,
    content,
    issueIds: issueIdsByLine.get(lineKey) ?? [],
  }
}

function extractDiffFromReview(review: string) {
  if (!review.trim()) return ''

  const fencedBlocks = [...review.matchAll(DIFF_FENCE_RE)]
    .map(match => match[1].trim())
    .filter(Boolean)

  if (fencedBlocks.length > 0) {
    return fencedBlocks.join('\n')
  }

  if (review.includes('diff --git') && review.includes('@@')) {
    const start = review.indexOf('diff --git')
    return review.slice(start).trim()
  }

  return ''
}

function getCommentPrefix(filePath: string) {
  const extension = filePath.split('.').pop()?.toLowerCase()

  if (extension === 'py' || extension === 'rb' || extension === 'sh') {
    return '#'
  }

  if (extension === 'html' || extension === 'xml') {
    return '<!--'
  }

  return '//'
}

function createSyntheticFiles(
  issues: Issue[],
  filesFromTrace: string[]
): DiffFile[] {
  const groupedIssues = new Map<string, Issue[]>()

  for (const issue of issues) {
    const filePath = normalizePath(issue.file) || 'unknown'
    const existing = groupedIssues.get(filePath) ?? []
    existing.push(issue)
    groupedIssues.set(filePath, existing)
  }

  for (const traceFile of filesFromTrace) {
    const normalized = normalizePath(traceFile)
    if (!normalized || groupedIssues.has(normalized)) continue
    groupedIssues.set(normalized, [])
  }

  return [...groupedIssues.entries()].map(([filePath, fileIssues], fileIndex) => {
    const sortedIssues = [...fileIssues].sort((left, right) => left.line - right.line)
    const commentPrefix = getCommentPrefix(filePath)
    const hunks: DiffHunk[] =
      sortedIssues.length > 0
        ? sortedIssues.map((issue, issueIndex) => {
            const anchor = Math.max(1, issue.line || issueIndex + 1)

            return {
              id: `${filePath}:generated:${issueIndex}`,
              header: `@@ -${anchor},1 +${anchor},2 @@`,
              lines: [
                {
                  id: `${filePath}:generated:${issueIndex}:context`,
                  type: 'context',
                  oldNumber: Math.max(1, anchor - 1),
                  newNumber: Math.max(1, anchor - 1),
                  content: `${commentPrefix} Diff context unavailable in backend payload`,
                  issueIds: [],
                },
                {
                  id: `${filePath}:generated:${issueIndex}:removed`,
                  type: 'removed',
                  oldNumber: anchor,
                  newNumber: null,
                  content: `${commentPrefix} Original changed line not returned by API`,
                  issueIds: [getIssueId(issue)],
                },
                {
                  id: `${filePath}:generated:${issueIndex}:added`,
                  type: 'added',
                  oldNumber: null,
                  newNumber: anchor,
                  content:
                    commentPrefix === '<!--'
                      ? `<!-- Finding: ${issue.message} -->`
                      : `${commentPrefix} Finding: ${issue.message}`,
                  issueIds: [getIssueId(issue)],
                },
              ],
            }
          })
        : [
            {
              id: `${filePath}:generated:empty`,
              header: '@@ -1,1 +1,2 @@',
              lines: [
                {
                  id: `${filePath}:generated:empty:removed`,
                  type: 'removed',
                  oldNumber: 1,
                  newNumber: null,
                  content: `${commentPrefix} Exact diff lines unavailable`,
                  issueIds: [],
                },
                {
                  id: `${filePath}:generated:empty:added`,
                  type: 'added',
                  oldNumber: null,
                  newNumber: 1,
                  content:
                    commentPrefix === '<!--'
                      ? '<!-- File listed in execution trace -->'
                      : `${commentPrefix} File listed in execution trace`,
                  issueIds: [],
                },
              ],
            },
          ]

    return {
      id: `${filePath}:${fileIndex}`,
      path: filePath,
      oldPath: filePath,
      newPath: filePath,
      status: 'generated',
      source: 'generated',
      additions: hunks.reduce(
        (total, hunk) => total + hunk.lines.filter(line => line.type === 'added').length,
        0
      ),
      deletions: hunks.reduce(
        (total, hunk) => total + hunk.lines.filter(line => line.type === 'removed').length,
        0
      ),
      hunks,
      issues: sortedIssues,
    }
  })
}

function parseFilesChangedFromTrace(trace: TraceEntry[]) {
  const collected = new Set<string>()

  for (const entry of trace) {
    const match = entry.message.match(FILES_CHANGED_RE)
    if (!match?.[1]) continue

    for (const file of match[1].match(/'([^']+)'|"([^"]+)"/g) ?? []) {
      const normalized = normalizePath(file)
      if (normalized) collected.add(normalized)
    }
  }

  return [...collected]
}

export function getIssueId(issue: Pick<Issue, 'file' | 'line' | 'message'>) {
  return `${normalizePath(issue.file)}:${issue.line}:${issue.message}`
}

export function parseDiffFiles(review: string, issues: Issue[], trace: TraceEntry[]) {
  const diffSource = extractDiffFromReview(review)
  const filesFromTrace = parseFilesChangedFromTrace(trace)

  if (!diffSource) {
    return createSyntheticFiles(issues, filesFromTrace)
  }

  const files: DiffFile[] = []
  let currentFile: DiffFile | null = null
  let currentHunk: DiffHunk | null = null
  let currentIssueIdsByLine = new Map<number, string[]>()
  let oldLine = 0
  let newLine = 0
  let lineIndex = 0

  const attachIssues = (file: DiffFile) => {
    file.issues = issues.filter(issue => isFileMatch(file.path, issue.file))
    return file
  }

  const pushHunk = () => {
    if (!currentFile || !currentHunk) return
    currentFile.hunks.push(currentHunk)
    currentHunk = null
  }

  const pushFile = () => {
    if (!currentFile) return
    pushHunk()
    files.push(attachIssues(currentFile))
    currentFile = null
  }

  const ensureFile = (fallbackPath = 'unknown') => {
    if (currentFile) return currentFile

    currentFile = {
      id: `${fallbackPath}:${files.length}`,
      path: fallbackPath,
      oldPath: fallbackPath,
      newPath: fallbackPath,
      status: 'modified',
      source: 'review',
      additions: 0,
      deletions: 0,
      hunks: [],
      issues: [],
    }

    return currentFile
  }

  for (const rawLine of diffSource.replace(/\r\n/g, '\n').split('\n')) {
    const diffStartMatch = rawLine.match(DIFF_START_RE)

    if (diffStartMatch) {
      pushFile()
      const oldPath = normalizePath(diffStartMatch[1])
      const newPath = normalizePath(diffStartMatch[2])

      currentFile = {
        id: `${newPath || oldPath}:${files.length}`,
        path: newPath || oldPath || 'unknown',
        oldPath: oldPath || null,
        newPath: newPath || null,
        status: 'modified',
        source: 'review',
        additions: 0,
        deletions: 0,
        hunks: [],
        issues: [],
      }
      continue
    }

    if (rawLine.startsWith('new file mode')) {
      ensureFile().status = 'added'
      continue
    }

    if (rawLine.startsWith('deleted file mode')) {
      ensureFile().status = 'deleted'
      continue
    }

    if (rawLine.startsWith('rename from ')) {
      ensureFile().status = 'renamed'
      ensureFile().oldPath = normalizePath(rawLine.replace('rename from ', ''))
      ensureFile().path = getPreferredPath(
        ensureFile().oldPath,
        ensureFile().newPath,
        ensureFile().status
      )
      continue
    }

    if (rawLine.startsWith('rename to ')) {
      ensureFile().status = 'renamed'
      ensureFile().newPath = normalizePath(rawLine.replace('rename to ', ''))
      ensureFile().path = getPreferredPath(
        ensureFile().oldPath,
        ensureFile().newPath,
        ensureFile().status
      )
      continue
    }

    if (rawLine.startsWith('--- ')) {
      const file = ensureFile()
      const oldPath = normalizePath(rawLine.replace(/^---\s+/, '').replace('/dev/null', ''))
      file.oldPath = oldPath || null
      file.path = getPreferredPath(file.oldPath, file.newPath, file.status)
      continue
    }

    if (rawLine.startsWith('+++ ')) {
      const file = ensureFile()
      const newPath = normalizePath(rawLine.replace(/^\+\+\+\s+/, '').replace('/dev/null', ''))
      file.newPath = newPath || null
      file.path = getPreferredPath(file.oldPath, file.newPath, file.status)
      continue
    }

    const hunkMatch = rawLine.match(HUNK_HEADER_RE)
    if (hunkMatch) {
      const file = ensureFile(filesFromTrace[files.length] ?? issues[0]?.file ?? 'unknown')
      const issueIdsByLine = new Map<number, string[]>()

      for (const issue of issues.filter(item => isFileMatch(file.path, item.file))) {
        const anchor = issue.line || 0
        const existing = issueIdsByLine.get(anchor) ?? []
        existing.push(getIssueId(issue))
        issueIdsByLine.set(anchor, existing)
      }

      pushHunk()
      oldLine = Number(hunkMatch[1])
      newLine = Number(hunkMatch[3])
      currentHunk = {
        id: `${file.path}:${file.hunks.length}`,
        header: `${hunkMatch[0]}${hunkMatch[5] ?? ''}`.trim(),
        lines: [],
      }
      currentIssueIdsByLine = issueIdsByLine
      continue
    }

    if (!currentHunk) continue

    const file = ensureFile()

    if (rawLine.startsWith('+') && !rawLine.startsWith('+++')) {
      currentHunk.lines.push(
        createLine(file.path, currentIssueIdsByLine, lineIndex, 'added', null, newLine, rawLine.slice(1))
      )
      currentFile!.additions += 1
      newLine += 1
      lineIndex += 1
      continue
    }

    if (rawLine.startsWith('-') && !rawLine.startsWith('---')) {
      currentHunk.lines.push(
        createLine(file.path, currentIssueIdsByLine, lineIndex, 'removed', oldLine, null, rawLine.slice(1))
      )
      currentFile!.deletions += 1
      oldLine += 1
      lineIndex += 1
      continue
    }

    if (rawLine.startsWith(' ') || rawLine === '') {
      currentHunk.lines.push(
        createLine(
          file.path,
          currentIssueIdsByLine,
          lineIndex,
          'context',
          oldLine,
          newLine,
          rawLine.startsWith(' ') ? rawLine.slice(1) : rawLine
        )
      )
      oldLine += 1
      newLine += 1
      lineIndex += 1
      continue
    }

    currentHunk.lines.push(
      createLine(file.path, currentIssueIdsByLine, lineIndex, 'meta', null, null, rawLine)
    )
    lineIndex += 1
  }

  pushFile()

  return files.length > 0 ? files : createSyntheticFiles(issues, filesFromTrace)
}
