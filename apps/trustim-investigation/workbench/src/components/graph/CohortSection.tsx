import { useState } from 'react'
import type { InvestigationNode } from '../../types'
import type { ChatContext } from '../../store/session'
import { useSessionStore } from '../../store/session'
import { miscApi } from '../../api'
import { extractCohort, suggestCohortQueries } from '../../utils/cohort-extraction'

interface CohortSectionProps {
  node: InvestigationNode
  nodeId: string
  setChatContext: (ctx: ChatContext | null) => void
  selectNode: (id: string | null) => void
}

/** Shows extracted cohort entities with follow-up query suggestions */
export function CohortSection({ node, nodeId, setChatContext, selectNode }: CohortSectionProps) {
  const cohort = extractCohort(node.result_raw || '')
  const total = cohort.memberIds.length + cohort.ips.length + cohort.domains.length + cohort.deviceHashes.length
  // Auto-expand when significant entities found (>5)
  const [expanded, setExpanded] = useState(total > 5)
  const [knownIocs, setKnownIocs] = useState<string[]>([])
  if (total === 0) return null

  const suggestions = suggestCohortQueries(cohort)

  // Check top IPs against IOC database
  const checkHistory = () => {
    const checks = cohort.ips.slice(0, 5).map(ip =>
      miscApi.checkIoc(ip)
    )
    Promise.all(checks).then(results => {
      const known = results
        .map((r, i) => r.found ? cohort.ips[i] : null)
        .filter(Boolean) as string[]
      setKnownIocs(known)
      if (known.length > 0) {
        import('../../store/toast').then(({ useToastStore }) =>
          useToastStore.getState().addToast(`${known.length} IP(s) seen in previous investigations`, 'warning', 5000)
        )
      } else {
        import('../../store/toast').then(({ useToastStore }) =>
          useToastStore.getState().addToast('No IOCs found in previous investigations', 'info', 3000)
        )
      }
    })
  }

  return (
    <section className="px-4 py-2.5 border-t border-surface-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left"
      >
        <h3 className="text-xs font-medium text-gray-400 uppercase">Extracted Entities ({total})</h3>
        <span className="text-[10px] text-gray-500 ml-auto">{expanded ? '\u25B2' : '\u25BC'}</span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {/* Entity summary */}
          <div className="flex flex-wrap gap-2 text-[10px]">
            {cohort.memberIds.length > 0 && (
              <button
                onClick={() => navigator.clipboard.writeText(cohort.memberIds.join(', '))}
                className="bg-accent-blue/10 text-accent-blue px-2 py-0.5 rounded hover:bg-accent-blue/20 transition-colors"
                title="Click to copy member IDs"
              >
                {cohort.memberIds.length} member IDs
              </button>
            )}
            {cohort.ips.length > 0 && (
              <button
                onClick={() => navigator.clipboard.writeText(cohort.ips.join(', '))}
                className="bg-accent-cyan/10 text-accent-cyan px-2 py-0.5 rounded hover:bg-accent-cyan/20 transition-colors"
                title="Click to copy IPs"
              >
                {cohort.ips.length} IPs
              </button>
            )}
            {cohort.domains.length > 0 && (
              <button
                onClick={() => navigator.clipboard.writeText(cohort.domains.join(', '))}
                className="bg-accent-purple/10 text-accent-purple px-2 py-0.5 rounded hover:bg-accent-purple/20 transition-colors"
                title="Click to copy domains"
              >
                {cohort.domains.length} domains
              </button>
            )}
            {cohort.deviceHashes.length > 0 && (
              <span className="bg-surface-3 text-gray-400 px-2 py-0.5 rounded">{cohort.deviceHashes.length} hashes</span>
            )}
            {cohort.ips.length > 0 && (
              <button
                onClick={checkHistory}
                className="bg-yellow-900/20 text-yellow-400 px-2 py-0.5 rounded hover:bg-yellow-900/30 transition-colors"
                title="Check if these IOCs appeared in previous investigations"
              >
                Check history
              </button>
            )}
          </div>
          {knownIocs.length > 0 && (
            <div className="text-[10px] text-yellow-400 bg-yellow-900/10 rounded px-2 py-1">
              Previously seen: {knownIocs.join(', ')}
            </div>
          )}

          {/* Follow-up query suggestions based on cohort */}
          {suggestions.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map(s => (
                <button
                  key={s.label}
                  onClick={() => {
                    setChatContext({
                      nodeId,
                      label: node.label || '',
                      query: node.query,
                      result_summary: node.result_summary,
                      result_raw: node.result_raw,
                    })
                    useSessionStore.getState().addMessage('user', s.prompt)
                    selectNode(null)
                  }}
                  className="text-[10px] bg-white/[0.04] hover:bg-white/[0.08] text-gray-400 hover:text-gray-200 px-2 py-1 rounded transition-colors"
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
