import { useState, useEffect, useRef, useMemo } from 'react'
import { sessionsApi, miscApi } from '../../api'
import { useSessionStore } from '../../store/session'
import type { SessionSummary } from '../../types'

interface Props {
  onClose: () => void
}

/** Cmd+K quick-open overlay — fuzzy search sessions and actions */
export function QuickOpen({ onClose }: Props) {
  const [query, setQuery] = useState('')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [pastQueries, setPastQueries] = useState<{ query: string; label: string; session: string }[]>([])
  const [selectedIdx, setSelectedIdx] = useState(0)
  const loadSession = useSessionStore((s) => s.loadSession)
  const newSession = useSessionStore((s) => s.newSession)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    sessionsApi.list().then(setSessions).catch(() => {})
    miscApi.listQueries().then(setPastQueries).catch(() => {})
    inputRef.current?.focus()
  }, [])

  // Built-in actions that always show
  const actions = [
    { id: 'new', label: 'New Investigation', detail: 'Start a blank session', action: () => { newSession(`Investigation — ${new Date().toLocaleDateString()}`, ''); onClose() } },
    { id: 'findings', label: 'Quick Findings', detail: 'Copy one-paragraph summary to clipboard', action: () => {
      import('../../utils/export').then(({ generateQuickFindings }) => {
        import('../../store/session').then(({ useSessionStore: ss }) => {
          const data = ss.getState().getSessionData()
          if (data) { navigator.clipboard.writeText(generateQuickFindings(data)); import('../../store/toast').then(({ useToastStore }) => useToastStore.getState().addToast('Quick findings copied', 'success', 2000)) }
        })
      })
      onClose()
    }},
    { id: 'publish', label: 'Publish Audit Report', detail: 'Copy full audit report to clipboard', action: () => {
      import('../../utils/export').then(({ generateAuditReport }) => {
        import('../../store/session').then(({ useSessionStore: ss }) => {
          const data = ss.getState().getSessionData()
          if (data) { navigator.clipboard.writeText(generateAuditReport(data)); import('../../store/toast').then(({ useToastStore }) => useToastStore.getState().addToast('Audit report copied', 'success', 2000)) }
        })
      })
      onClose()
    }},
    { id: 'checklist', label: 'Investigation Checklist', detail: 'Check investigation dimensions', action: () => { window.dispatchEvent(new Event('showChecklist')); onClose() } },
    { id: 'iocs', label: 'IOC Database', detail: 'Browse all known IOCs', action: () => { window.dispatchEvent(new Event('showIocBrowser')); onClose() } },
  ]

  const lq = query.toLowerCase()
  const matchedSessions = sessions.filter(s => !lq || s.name.toLowerCase().includes(lq))
  const matchedActions = actions.filter(a => !lq || a.label.toLowerCase().includes(lq))
  // Only show past queries when user is searching with 3+ chars
  const matchedQueries = useMemo(() => {
    if (lq.length < 3) return []
    return pastQueries.filter(q => q.label.toLowerCase().includes(lq) || q.query.toLowerCase().includes(lq)).slice(0, 5)
  }, [lq, pastQueries])

  const results = [
    ...matchedActions.map(a => ({ type: 'action' as const, id: a.id, label: a.label, detail: a.detail, run: a.action })),
    ...matchedSessions.map(s => ({ type: 'session' as const, id: s.id, label: s.name, detail: `${s.node_count} nodes | ${new Date(s.updated_at).toLocaleDateString()}`, run: () => {
      sessionsApi.get(s.id).then(data => { loadSession(data); onClose() })
    }})),
    ...matchedQueries.map((q, i) => ({ type: 'query' as const, id: `q-${i}`, label: q.label, detail: `${q.query.slice(0, 60)}... (from ${q.session})`, run: () => {
      navigator.clipboard.writeText(q.query)
      import('../../store/toast').then(({ useToastStore }) => useToastStore.getState().addToast('Query copied to clipboard', 'success', 2000))
      onClose()
    }})),
  ]

  useEffect(() => { setSelectedIdx(0) }, [query])

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIdx(i => Math.min(i + 1, results.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIdx(i => Math.max(i - 1, 0)) }
    if (e.key === 'Enter' && results[selectedIdx]) { results[selectedIdx].run() }
    if (e.key === 'Escape') { onClose() }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-start justify-center pt-[20vh] z-[110]" onClick={onClose}>
      <div className="glass-panel rounded-2xl w-[520px] shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Search investigations or type a command..."
          className="w-full bg-transparent px-5 py-4 text-[15px] text-gray-100 placeholder-gray-500 focus:outline-none border-b border-white/[0.06]"
          autoFocus
        />
        <div className="max-h-[320px] overflow-y-auto py-1">
          {results.length === 0 ? (
            <div className="px-5 py-6 text-center text-[13px] text-gray-500">No results</div>
          ) : (
            results.map((r, i) => (
              <button
                key={r.id}
                onClick={r.run}
                onMouseEnter={() => setSelectedIdx(i)}
                className={`w-full text-left px-5 py-2.5 flex items-center gap-3 transition-colors ${
                  i === selectedIdx ? 'bg-accent-blue/20' : 'hover:bg-white/[0.03]'
                }`}
              >
                <span className="text-[12px] text-gray-500 w-5">
                  {r.type === 'action' ? '\u{26A1}' : r.type === 'query' ? '\u{1F4DD}' : '\u{1F4C1}'}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-gray-200 truncate">{r.label}</div>
                  <div className="text-[11px] text-gray-500 truncate">{r.detail}</div>
                </div>
                {i === selectedIdx && (
                  <span className="text-[10px] text-gray-500">Enter</span>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
