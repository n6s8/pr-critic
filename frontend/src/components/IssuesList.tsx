import type { Issue } from '../types'
import { cn } from '../lib/utils'

const SEV_STYLES: Record<string, { badge: string; row: string; dot: string }> = {
  critical: {
    badge: 'bg-red-950/60 text-red-400 border-red-900/40',
    row:   'border-l-2 border-l-red-800/50',
    dot:   'bg-red-500',
  },
  warning: {
    badge: 'bg-orange-950/60 text-orange-400 border-orange-900/40',
    row:   'border-l-2 border-l-orange-800/50',
    dot:   'bg-orange-400',
  },
  info: {
    badge: 'bg-card text-[#777] border-border2',
    row:   '',
    dot:   'bg-[#555]',
  },
}

interface Props {
  issues: Issue[] | undefined
}

export function IssuesList({ issues }: Props) {
  const safeIssues = issues ?? []

  if (safeIssues.length === 0) return null

  return (
    <div className="border-t border-border px-4 py-3">
      <p className="section-label mb-2">Issues ({safeIssues.length})</p>

      <div className="space-y-1.5">
        {safeIssues.map((issue, i) => {
          const severity = issue?.severity ?? 'info'
          const file = issue?.file ?? 'unknown'
          const line = issue?.line ?? 0
          const message = issue?.message ?? ''

          const styles = SEV_STYLES[severity] ?? SEV_STYLES.info

          return (
            <div
              key={i}
              className={cn(
                'flex gap-2.5 p-2.5 rounded-md bg-elevated',
                styles.row
              )}
            >
              <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5', styles.dot)} />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className={cn(
                    'text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border',
                    styles.badge
                  )}>
                    {severity}
                  </span>

                  <span className="text-[11px] font-mono text-[#666] truncate">
                    {file}:{line}
                  </span>
                </div>

                <p className="text-[12px] text-neutral-400 leading-relaxed">
                  {message}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}