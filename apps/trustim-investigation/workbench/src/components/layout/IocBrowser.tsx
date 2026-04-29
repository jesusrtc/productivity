import { useState, useEffect } from 'react'
import { miscApi } from '../../api'

interface IocEntry {
  value: string
  type: string
  sessions: string[]
  firstSeen: string
  lastSeen: string
}

interface Props {
  onClose: () => void
}

/** Browse all known IOCs across investigations */
export function IocBrowser({ onClose }: Props) {
  const [iocs, setIocs] = useState<IocEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')

  useEffect(() => {
    miscApi.listIocs()
      .then((data: any) => setIocs(data.iocs || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = iocs.filter(ioc => {
    if (typeFilter !== 'all' && ioc.type !== typeFilter) return false
    if (filter && !ioc.value.toLowerCase().includes(filter.toLowerCase())) return false
    return true
  })

  const typeCounts: Record<string, number> = {}
  for (const ioc of iocs) typeCounts[ioc.type] = (typeCounts[ioc.type] || 0) + 1

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="glass-panel rounded-2xl p-6 w-[600px] max-h-[80vh] flex flex-col animate-[fadeIn_0.2s_ease-out]" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">IOC Database ({iocs.length})</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>

        <div className="flex gap-2 mb-3">
          <input
            type="text"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Search IOCs..."
            className="flex-1 bg-surface-2/60 border border-white/[0.06] rounded-lg px-3 py-1.5 text-[12px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue/50"
            autoFocus
          />
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
            className="bg-surface-2/60 border border-white/[0.06] rounded-lg px-2 text-[11px] text-gray-300 focus:outline-none"
          >
            <option value="all">All ({iocs.length})</option>
            {Object.entries(typeCounts).map(([type, count]) => (
              <option key={type} value={type}>{type} ({count})</option>
            ))}
          </select>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="text-center py-8 text-gray-500 text-sm">Loading...</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-8 text-gray-500 text-sm">
              {iocs.length === 0 ? 'No IOCs recorded yet. They are collected as investigations run.' : 'No matching IOCs'}
            </div>
          ) : (
            <table className="w-full text-[11px]">
              <thead className="text-gray-500 uppercase text-[10px] border-b border-surface-3 sticky top-0 bg-surface-1">
                <tr>
                  <th className="text-left py-1.5 px-2">Value</th>
                  <th className="text-left py-1.5 px-2">Type</th>
                  <th className="text-center py-1.5 px-2">Sessions</th>
                  <th className="text-left py-1.5 px-2">Last seen</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 100).map((ioc, i) => (
                  <tr key={i} className="border-b border-surface-3/50 hover:bg-white/[0.02]">
                    <td className="py-1 px-2 font-mono text-gray-200 truncate max-w-[200px]" title={ioc.value}>
                      <button
                        onClick={() => navigator.clipboard.writeText(ioc.value)}
                        className="hover:text-accent-blue transition-colors"
                        title="Click to copy"
                      >
                        {ioc.value}
                      </button>
                    </td>
                    <td className="py-1 px-2">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] ${
                        ioc.type === 'ip' ? 'bg-accent-cyan/10 text-accent-cyan' :
                        ioc.type === 'domain' ? 'bg-accent-purple/10 text-accent-purple' :
                        'bg-surface-3 text-gray-400'
                      }`}>{ioc.type}</span>
                    </td>
                    <td className="py-1 px-2 text-center tabular-nums text-gray-400">
                      {ioc.sessions.length}
                    </td>
                    <td className="py-1 px-2 text-gray-500 tabular-nums">
                      {new Date(ioc.lastSeen).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="mt-3 pt-3 border-t border-surface-3 text-[10px] text-gray-500">
          {filtered.length} IOCs shown{filtered.length > 100 ? ' (first 100)' : ''}. Click a value to copy.
        </div>
      </div>
    </div>
  )
}
