import type { DiffFile, DiffHunk, DiffLine, DiffFileStatus, Issue } from '../types'

const DIFF_START_RE = /^diff --git\s+a\/(.+?)\s+b\/(.+)$/i
const HUNK_HEADER_RE = /^@@\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s*@@(.*)$/

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

export function getIssueId(issue: Pick<Issue, 'file' | 'line' | 'message'>) {
  return `${normalizePath(issue.file)}:${issue.line}:${issue.message}`
}

export function parseDiffFiles(diff: string, issues: Issue[]) {
  if (!diff.trim()) {
    return [] as DiffFile[]
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
      additions: 0,
      deletions: 0,
      hunks: [],
      issues: [],
    }

    return currentFile
  }

  for (const rawLine of diff.replace(/\r\n/g, '\n').split('\n')) {
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
      const file = ensureFile(issues[0]?.file ?? 'unknown')
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
  return files
}
