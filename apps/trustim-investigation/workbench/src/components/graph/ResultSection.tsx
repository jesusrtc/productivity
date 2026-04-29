import { useState, useEffect } from 'react'
import type { InvestigationNode } from '../../types'
import { ResultRenderer } from './ResultRenderer'
import { extractIOCs } from '../../utils/ioc-extraction'
import { HighlightedText } from './HighlightedText'

/** Result section with search-within-output (Ctrl+F) */
export function ResultSection({ node }: { node: InvestigationNode }) {
  const [searchTerm, setSearchTerm] = useState('')
  const [showSearch, setShowSearch] = useState(false)

  // Ctrl+F when drawer is open focuses the search
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
        e.preventDefault()
        setShowSearch(true)
      }
      if (e.key === 'Escape' && showSearch) {
        setShowSearch(false)
        setSearchTerm('')
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [showSearch])

  const matchCount = searchTerm.trim() && node.result_raw
    ? (node.result_raw.match(new RegExp(searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')) || []).length
    : 0

  return (
    <section className="px-4 py-3 border-b border-surface-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-gray-400 uppercase">Results</h3>
        <div className="flex items-center gap-2">
          {/* Quick IOC copy — extract IPs, domains, hashes from results */}
          {node.result_raw && (
            <button
              onClick={() => {
                const iocs = extractIOCs(node.result_raw)
                if (iocs.length > 0) {
                  navigator.clipboard.writeText(iocs.join('\n'))
                  import('../../store/toast').then(({ useToastStore }) =>
                    useToastStore.getState().addToast(`Copied ${iocs.length} IOCs to clipboard`, 'success', 2000)
                  )
                } else {
                  import('../../store/toast').then(({ useToastStore }) =>
                    useToastStore.getState().addToast('No IOCs found in results', 'info', 2000)
                  )
                }
              }}
              className="text-[10px] text-accent-cyan hover:text-cyan-300 transition-colors"
              title="Extract and copy IP addresses, domains, hashes from results"
            >
              Copy IOCs
            </button>
          )}
          {showSearch && (
            <div className="flex items-center gap-1">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search..."
                className="bg-surface-2 border border-surface-4 rounded px-2 py-0.5 text-[10px] text-gray-200 w-[120px] focus:outline-none focus:border-accent-blue/50"
                autoFocus
              />
              {searchTerm && <span className="text-[10px] text-gray-500 tabular-nums">{matchCount}</span>}
            </div>
          )}
          <button
            onClick={() => { setShowSearch(!showSearch); setSearchTerm('') }}
            className={`text-[10px] transition-colors ${showSearch ? 'text-accent-blue' : 'text-gray-500 hover:text-gray-300'}`}
          >
            {showSearch ? 'Done' : 'Search'}
          </button>
          <button
            onClick={() => navigator.clipboard.writeText(node.result_raw)}
            className="text-[10px] text-gray-500 hover:text-gray-300"
          >
            Copy
          </button>
        </div>
      </div>
      {node.status === 'running' && !node.result_raw ? (
        <p className="text-xs text-gray-500 italic">Awaiting results...</p>
      ) : searchTerm.trim() ? (
        <pre className="bg-surface-0 rounded-xl p-3 text-[12px] text-gray-300 overflow-x-auto whitespace-pre-wrap font-mono border border-white/[0.04] max-h-[300px] overflow-y-auto leading-relaxed">
          <HighlightedText text={node.result_raw || ''} search={searchTerm} />
        </pre>
      ) : (
        <ResultRenderer raw={node.result_raw} summary={node.result_summary} />
      )}
    </section>
  )
}
