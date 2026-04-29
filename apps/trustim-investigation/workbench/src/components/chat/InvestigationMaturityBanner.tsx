import { getUncoveredDimensions } from '../../utils/investigation-checklist'

interface InvestigationMaturityBannerProps {
  nodes: Record<string, { label: string; query: string; tags: string[]; confidence: number; status: string }>
}

/** Investigation maturity banner — shows when investigation has good coverage */
export function InvestigationMaturityBanner({ nodes }: InvestigationMaturityBannerProps) {
  const nodeList = Object.values(nodes)
  if (nodeList.length < 5) return null // Don't show until there's substance

  const completed = nodeList.filter(n => n.status === 'completed').length
  const uncovered = getUncoveredDimensions(nodes)
  const coveredPct = Math.round(((8 - uncovered.length) / 8) * 100)
  const hasSev = nodeList.some(n => (n.tags || []).some(t => t.startsWith('SEV-')))

  // Only show when coverage is meaningful
  if (coveredPct < 50 && !hasSev) return null

  if (coveredPct >= 75) {
    return (
      <div className="px-4 py-2 bg-green-900/10 border-t border-green-900/20 flex items-center gap-2 flex-shrink-0">
        <span className="text-[11px] text-green-400">Investigation coverage: <strong>{coveredPct}%</strong> ({completed} nodes). Ready to publish.</span>
        <button
          onClick={() => {
            import('../../utils/export').then(({ generateAuditReport }) => {
              import('../../store/session').then(({ useSessionStore }) => {
                const data = useSessionStore.getState().getSessionData()
                if (data) navigator.clipboard.writeText(generateAuditReport(data))
              })
            })
            import('../../store/toast').then(({ useToastStore }) =>
              useToastStore.getState().addToast('Audit report copied to clipboard', 'success', 3000)
            )
          }}
          className="text-[10px] text-green-300 hover:text-green-200 underline ml-auto"
        >
          Copy audit report
        </button>
      </div>
    )
  }

  if (uncovered.length > 0 && uncovered.length <= 3) {
    return (
      <div className="px-4 py-1.5 bg-surface-2/30 border-t border-surface-3 flex-shrink-0">
        <span className="text-[10px] text-gray-500">
          Coverage {coveredPct}% — unchecked: {uncovered.join(', ')}
        </span>
      </div>
    )
  }

  return null
}
