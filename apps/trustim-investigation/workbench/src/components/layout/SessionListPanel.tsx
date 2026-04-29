import { useState, useEffect, useRef } from 'react'
import { sessionsApi } from '../../api'
import { useSessionStore } from '../../store/session'
import type { SessionSummary } from '../../types'

interface Props {
  onClose: () => void
  onCompare?: () => void
}

/** Searchable session list panel — load, delete, or compare sessions */
export function SessionListPanel({ onClose, onCompare }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<'date' | 'nodes' | 'name'>('date')
  const loadSession = useSessionStore((s) => s.loadSession)
  const currentSession = useSessionStore((s) => s.currentSession)
  const linkSession = useSessionStore((s) => s.linkSession)
  const linkedIds = new Set(currentSession?.linked_sessions || [])
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    sessionsApi.list()
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = sessions
    .filter(s => !search || s.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'date') return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      if (sortBy === 'nodes') return b.node_count - a.node_count
      return a.name.localeCompare(b.name)
    })

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div ref={panelRef} className="glass-panel rounded-2xl p-6 w-[520px] max-h-[80vh] flex flex-col animate-[fadeIn_0.2s_ease-out]" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">Investigations ({sessions.length})</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>

        {/* Search + Sort */}
        <div className="flex gap-2 mb-3">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search investigations..."
            className="flex-1 bg-surface-2/60 border border-white/[0.06] rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue/50"
            autoFocus
          />
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value as 'date' | 'nodes' | 'name')}
            className="bg-surface-2/60 border border-white/[0.06] rounded-lg px-2 text-[12px] text-gray-300 focus:outline-none"
          >
            <option value="date">Recent</option>
            <option value="nodes">Most nodes</option>
            <option value="name">Name</option>
          </select>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto space-y-1">
          {loading ? (
            <div className="space-y-2 py-2">
              {[1,2,3,4].map(i => (
                <div key={i} className="bg-white/[0.02] rounded-lg px-3 py-3 animate-pulse">
                  <div className="h-3 bg-surface-3 rounded w-3/4 mb-2" />
                  <div className="h-2 bg-surface-3 rounded w-1/2" />
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-center text-gray-500 py-8">{search ? 'No matching investigations' : 'No saved investigations'}</p>
          ) : (
            filtered.map(s => (
              <div key={s.id} className="flex items-center gap-2 group">
                <button
                  onClick={() => {
                    sessionsApi.get(s.id)
                      .then(data => { loadSession(data); onClose() })
                  }}
                  className="flex-1 text-left bg-white/[0.02] hover:bg-white/[0.05] rounded-lg px-3 py-2.5 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] text-gray-200 truncate flex-1">{s.name}</span>
                    {s.has_sev && <span className="text-[9px] bg-red-900/30 text-red-400 px-1.5 py-0.5 rounded">SEV</span>}
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-gray-500 mt-0.5">
                    <span className="tabular-nums">{s.node_count} nodes</span>
                    <span className="text-gray-600">|</span>
                    <span>{timeAgo(s.updated_at)}</span>
                    {s.max_confidence != null && s.max_confidence > 0 && (
                      <>
                        <span className="text-gray-600">|</span>
                        <span className="tabular-nums">{(s.max_confidence * 100).toFixed(0)}%</span>
                      </>
                    )}
                  </div>
                </button>
                {currentSession && s.id !== currentSession.id && (
                  <button
                    onClick={() => { linkSession(s.id) }}
                    className={`px-1 text-[10px] transition-colors ${
                      linkedIds.has(s.id) ? 'text-accent-cyan' : 'text-gray-500 hover:text-accent-cyan'
                    }`}
                    title={linkedIds.has(s.id) ? 'Linked' : 'Link to current investigation'}
                  >
                    {linkedIds.has(s.id) ? '\u2714' : '\u{1F517}'}
                  </button>
                )}
                <button
                  onClick={() => {
                    if (confirm(`Delete "${s.name}"?${s.node_count > 5 ? `\n\nThis investigation has ${s.node_count} nodes.` : ''}`)) {
                      sessionsApi.delete(s.id)
                        .then(() => {
                          // Remove from local panel list
                          setSessions(prev => prev.filter(x => x.id !== s.id))
                          // Remove from global store so Recent Investigations updates
                          const store = useSessionStore.getState()
                          store.setSessionList(store.sessionList.filter(x => x.id !== s.id))
                          // Clean up localStorage backup
                          try { localStorage.removeItem(`investigation-backup-${s.id}`) } catch {}
                          // If we just deleted the active session, close it
                          if (store.currentSession?.id === s.id) {
                            store.closeSession()
                          }
                          // Close the tab if open
                          window.dispatchEvent(new CustomEvent('closeInvestigationTab', { detail: { sessionId: s.id } }))
                          // Refresh alerts to remove the session link
                          import('../../store/alert').then(({ useAlertStore }) => useAlertStore.getState().fetchAlerts()).catch(() => {})
                        })
                    }
                  }}
                  className="text-gray-600 hover:text-red-400 px-1 transition-colors"
                  title="Delete"
                >
                  {'\u2715'}
                </button>
              </div>
            ))
          )}
        </div>

        <div className="mt-4 pt-3 border-t border-surface-3 flex justify-between text-[11px] text-gray-500">
          <span>{filtered.length} of {sessions.length} investigations</span>
          <div className="flex gap-3">
            {onCompare && sessions.length >= 2 && (
              <button
                onClick={() => { onClose(); onCompare() }}
                className="text-accent-purple hover:text-purple-400 transition-colors"
              >
                Compare
              </button>
            )}
            <button
              onClick={() => window.open('/api/export/all', '_blank')}
              className="text-accent-blue hover:text-blue-400 transition-colors"
            >
              Export all
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function timeAgo(dateStr: string): string {
  const ms = Date.now() - new Date(dateStr).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d}d ago`
  return new Date(dateStr).toLocaleDateString()
}
