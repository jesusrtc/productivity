interface AgentStepProgressProps {
  nodes: Record<string, { status: string; label: string; tool_name: string | null; confidence: number; duration_ms: number }>
}

/** Shows step-by-step progress while agent is working */
export function AgentStepProgress({ nodes }: AgentStepProgressProps) {
  const nodeList = Object.values(nodes)
  const completed = nodeList.filter(n => n.status === 'completed').length
  const running = nodeList.filter(n => n.status === 'running').length
  const failed = nodeList.filter(n => n.status === 'failed').length
  const done = completed + failed
  const total = nodeList.length

  if (total <= 1) return null

  const recentCompleted = nodeList
    .filter(n => n.status === 'completed' && n.label)
    .slice(-3)

  const runningNode = nodeList.find(n => n.status === 'running')
  const completedPct = total > 0 ? (completed / total) * 100 : 0
  const failedPct = total > 0 ? (failed / total) * 100 : 0

  return (
    <div className="mt-1.5 space-y-1">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden flex">
          <div className="h-full bg-accent-blue rounded-l-full transition-all duration-500" style={{ width: `${completedPct}%` }} />
          {failedPct > 0 && <div className="h-full bg-red-500/60 transition-all duration-500" style={{ width: `${failedPct}%` }} />}
        </div>
        <span className="text-[10px] text-gray-500 tabular-nums whitespace-nowrap">
          {done}/{total}{running > 0 ? ` (${running} active)` : ''}{failed > 0 ? ` (${failed} failed)` : ''}
        </span>
      </div>
      {runningNode && (
        <div className="flex items-center gap-1.5 text-[10px]">
          <div className="w-1 h-1 bg-accent-blue rounded-full animate-pulse" />
          <span className="text-accent-blue truncate">{runningNode.tool_name || runningNode.label}</span>
        </div>
      )}
      {recentCompleted.length > 0 && (
        <div className="space-y-0.5">
          {recentCompleted.map((n, i) => (
            <div key={i} className="flex items-center gap-1.5 text-[10px] text-gray-600">
              <span className="text-green-600">{'\u2713'}</span>
              <span className="truncate">{n.label}</span>
              {n.confidence > 0 && (
                <span className="text-gray-600 tabular-nums ml-auto">{(n.confidence * 100).toFixed(0)}%</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
