import { useGraphStore } from '../../store/graph'

interface AutoInvestigateBannerProps {
  nodes: Record<string, { status: string; label: string; result_summary?: string; timestamp: string }>
}

/** Auto-investigate progress banner — reactively subscribes to autoInvestigateNodeId */
export function AutoInvestigateBanner({ nodes }: AutoInvestigateBannerProps) {
  const autoNodeId = useGraphStore((s) => s.autoInvestigateNodeId)
  if (!autoNodeId) return null

  const allNodes = Object.values(nodes)
  const running = allNodes.filter(n => n.status === 'running').length
  const completed = allNodes.filter(n => n.status === 'completed').length
  const failed = allNodes.filter(n => n.status === 'failed').length
  const done = completed + failed
  const latest = allNodes.filter(n => n.status === 'completed').sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0]

  return (
    <div className="bg-accent-cyan/[0.06] border border-accent-cyan/15 rounded-xl p-3 animate-[fadeIn_0.2s_ease-out]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[13px] text-accent-cyan">
          <div className="w-2 h-2 bg-accent-cyan rounded-full animate-pulse" />
          <span className="font-medium">Auto-investigating...</span>
          <span className="text-[11px] text-gray-500">
            {running > 0 ? `${running} running, ` : ''}{done}/{allNodes.length}{failed > 0 ? ` (${failed} failed)` : ''}
          </span>
        </div>
        <button
          onClick={() => useGraphStore.getState().stopAutoInvestigate()}
          className="text-[11px] text-orange-400 hover:text-orange-300 transition-colors"
        >
          Stop
        </button>
      </div>
      {latest && (
        <div className="mt-1.5 text-[11px] text-gray-500 truncate">
          Latest: {latest.label} — {latest.result_summary?.slice(0, 60) || 'processing...'}
        </div>
      )}
    </div>
  )
}
