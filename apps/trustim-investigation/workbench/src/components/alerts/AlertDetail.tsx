import { useState, useEffect } from 'react'
import { useAlertStore } from '../../store/alert'
import { useSessionStore } from '../../store/session'
import { sessionsApi, playbooksApi } from '../../api'
import type { Alert, AlertStatus, AlertSummary } from '../../types/alert'

export type InvestigationMode = 'autonomous' | 'playbook'

interface Props {
  alertId: string
  onClose: () => void
  onStartInvestigation: (alertId: string, mode: InvestigationMode, playbookId?: string) => void
  onNavigateToSession?: (sessionId: string) => void
}

const STATUS_TRANSITIONS: Record<AlertStatus, AlertStatus[]> = {
  new: ['investigating', 'dismissed'],
  investigating: ['resolved', 'dismissed'],
  resolved: ['investigating'],
  dismissed: ['new', 'investigating'],
}

export function AlertDetail({ alertId, onClose, onStartInvestigation, onNavigateToSession }: Props) {
  const fetchAlert = useAlertStore((s) => s.fetchAlert)
  const fetchRelated = useAlertStore((s) => s.fetchRelated)
  const transitionStatus = useAlertStore((s) => s.transitionStatus)
  const updateAlert = useAlertStore((s) => s.updateAlert)

  const [alert, setAlert] = useState<Alert | null>(null)
  const [related, setRelated] = useState<AlertSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [showModeModal, setShowModeModal] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchAlert(alertId),
      fetchRelated(alertId),
    ]).then(([a, r]) => {
      setAlert(a)
      setRelated(r)
      setLoading(false)
    })
  }, [alertId])

  if (loading || !alert) {
    return (
      <div className="h-full bg-surface-1 p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-surface-3 rounded w-3/4" />
          <div className="h-3 bg-surface-3 rounded w-1/2" />
          <div className="h-20 bg-surface-3 rounded" />
        </div>
      </div>
    )
  }

  const handleTransition = async (status: AlertStatus) => {
    await transitionStatus(alertId, status)
    const updated = await fetchAlert(alertId)
    if (updated) setAlert(updated)
  }

  return (
    <div className="h-full bg-surface-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-surface-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <SeverityBadge severity={alert.severity} />
            <StatusBadge status={alert.status} />
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>
        <h3 className="text-[15px] font-medium text-gray-200 leading-snug">{alert.title}</h3>
        {alert.external_id && (
          <span className="text-[11px] text-gray-500 font-mono">InResponse #{alert.external_id}</span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {/* Actions */}
        <div className="flex gap-2 flex-wrap">
          {alert.status !== 'resolved' && (
            <button
              onClick={() => setShowModeModal(true)}
              className="text-[12px] bg-accent-blue hover:bg-blue-600 text-white px-4 py-1.5 rounded-md transition-colors"
            >
              {alert.status === 'investigating' ? 'New Investigation' : 'Start Investigation'}
            </button>
          )}
          {STATUS_TRANSITIONS[alert.status]?.filter(s => s !== 'investigating').map(next => (
            <button
              key={next}
              onClick={() => handleTransition(next)}
              className="text-[12px] bg-surface-3 hover:bg-surface-4 text-gray-300 px-3 py-1.5 rounded-md transition-colors"
            >
              {next === 'resolved' ? 'Resolve' : next === 'dismissed' ? 'Dismiss' : next === 'new' ? 'Reopen' : next}
            </button>
          ))}
        </div>

        {/* Description */}
        {alert.description && (
          <div>
            <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Description</h4>
            <p className="text-[13px] text-gray-300 leading-relaxed whitespace-pre-wrap">{alert.description}</p>
          </div>
        )}

        {/* Suggested playbook */}
        <SuggestedPlaybook alertType={alert.alert_type} />

        {/* Metadata */}
        <div className="grid grid-cols-2 gap-2 text-[12px]">
          <div>
            <span className="text-gray-500">Type</span>
            <div className="text-gray-300">{alert.alert_type || '—'}</div>
          </div>
          <div>
            <span className="text-gray-500">Source</span>
            <div className="text-gray-300">{alert.source}</div>
          </div>
          <div>
            <span className="text-gray-500">Assignee</span>
            <div className="text-gray-300">{alert.assignee || '—'}</div>
          </div>
          <div>
            <span className="text-gray-500">Created</span>
            <div className="text-gray-300">{new Date(alert.created_at).toLocaleString()}</div>
          </div>
          {alert.incident_id && (
            <div>
              <span className="text-gray-500">Incident</span>
              <div className="text-accent-cyan font-mono">{alert.incident_id}</div>
            </div>
          )}
        </div>

        {/* IOCs */}
        {(alert.iocs || []).length > 0 && (
          <div>
            <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">IOCs ({(alert.iocs || []).length})</h4>
            <div className="flex flex-wrap gap-1">
              {(alert.iocs || []).map((ioc, i) => (
                <span key={i} className="text-[11px] bg-surface-3 text-gray-300 px-2 py-0.5 rounded font-mono">
                  <span className="text-gray-500">{ioc.type}:</span> {ioc.value}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Linked sessions */}
        {(alert.session_ids || []).length > 0 && (
          <div>
            <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Linked Sessions ({(alert.session_ids || []).length})</h4>
            <div className="space-y-1">
              {(alert.session_ids || []).map(sid => (
                <button
                  key={sid}
                  onClick={() => {
                    // Navigate immediately, load session in parallel
                    if (onNavigateToSession) onNavigateToSession(sid)
                    sessionsApi.get(sid)
                      .then((data: any) => { if (data?.id) useSessionStore.getState().loadSession(data) })
                      .catch(() => {})
                  }}
                  className="text-[12px] text-accent-blue hover:text-blue-400 transition-colors block"
                >
                  Session {sid.slice(0, 8)}...
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Related alerts (cross-alert context) */}
        {related.length > 0 && (
          <div>
            <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Related Alerts ({related.length})</h4>
            <div className="space-y-1">
              {related.map(r => (
                <div
                  key={r.id}
                  className="bg-surface-2/40 rounded-lg px-3 py-2 cursor-pointer hover:bg-surface-2/60 transition-colors"
                  onClick={() => useAlertStore.getState().selectAlert(r.id)}
                >
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={r.severity} small />
                    <span className="text-[12px] text-gray-200 truncate">{r.title}</span>
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    {r.alert_type} | {r.status} | {r.ioc_count} IOCs
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tags */}
        {(alert.tags || []).length > 0 && (
          <div>
            <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Tags</h4>
            <div className="flex flex-wrap gap-1">
              {(alert.tags || []).map(t => (
                <span key={t} className="text-[10px] bg-accent-purple/10 text-accent-purple px-2 py-0.5 rounded">{t}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Investigation mode modal */}
      {showModeModal && (
        <InvestigationModeModal
          alertType={alert.alert_type}
          onSelect={(mode, playbookId) => { setShowModeModal(false); onStartInvestigation(alertId, mode, playbookId) }}
          onClose={() => setShowModeModal(false)}
        />
      )}
    </div>
  )
}

function InvestigationModeModal({ alertType, onSelect, onClose }: {
  alertType: string
  onSelect: (mode: InvestigationMode, playbookId?: string) => void
  onClose: () => void
}) {
  const [playbooks, setPlaybooks] = useState<Array<{ id: string; name: string; category: string; nodes: any[] }>>([])
  const [selectedPlaybook, setSelectedPlaybook] = useState<string>('')
  const [mode, setMode] = useState<InvestigationMode>('autonomous')

  useEffect(() => {
    playbooksApi.list().then((pbs: any) => {
      setPlaybooks(Array.isArray(pbs) ? pbs : [])
      // Auto-select a playbook matching the alert type
      const match = pbs.find((p: any) => alertType && p.category?.toLowerCase().includes(alertType.toLowerCase()))
      if (match) { setSelectedPlaybook(match.id); setMode('playbook') }
    }).catch(() => {})
  }, [alertType])

  const modes = [
    { id: 'autonomous' as const, label: 'Autonomous', desc: 'LLM has access to all skills and decides which queries to run — same as CLI invocation.', icon: '\u{1F916}' },
    { id: 'playbook' as const, label: 'Playbook + LLM', desc: 'Run a structured playbook first, then LLM analyzes results and fills gaps.', icon: '\u{1F4CB}' },
  ]

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[120]" onClick={onClose}>
      <div className="bg-surface-1 border border-surface-3 rounded-xl p-5 w-[440px]" onClick={e => e.stopPropagation()}>
        <h3 className="text-[14px] font-medium text-gray-200 mb-4">Choose Investigation Mode</h3>

        {/* Mode selection */}
        <div className="space-y-2 mb-4">
          {modes.map(m => (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              className={`w-full text-left px-3 py-2.5 rounded-lg border-2 transition-colors ${
                mode === m.id
                  ? 'border-accent-blue bg-accent-blue/10'
                  : 'border-surface-3 hover:border-surface-4'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="text-[14px]">{m.icon}</span>
                <span className="text-[13px] text-gray-200 font-medium">{m.label}</span>
              </div>
              <p className="text-[11px] text-gray-500 mt-0.5 ml-6">{m.desc}</p>
            </button>
          ))}
        </div>

        {/* Playbook picker (shown when playbook mode selected) */}
        {mode === 'playbook' && (
          <div className="mb-4">
            <label className="text-[11px] text-gray-500 block mb-1">Select Playbook</label>
            <select
              value={selectedPlaybook}
              onChange={e => setSelectedPlaybook(e.target.value)}
              className="w-full bg-surface-2 border border-surface-4 rounded-lg px-3 py-2 text-[12px] text-gray-200 focus:outline-none focus:border-accent-blue/50"
            >
              <option value="">-- Choose a playbook --</option>
              {playbooks.map(p => (
                <option key={p.id} value={p.id}>{p.name} ({(p.nodes || []).length} steps)</option>
              ))}
            </select>
            {selectedPlaybook && playbooks.find(p => p.id === selectedPlaybook) && (
              <p className="text-[10px] text-gray-600 mt-1">
                {playbooks.find(p => p.id === selectedPlaybook)?.category} — {playbooks.find(p => p.id === selectedPlaybook)?.nodes?.length} steps
              </p>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="text-[12px] text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-md">Cancel</button>
          <button
            onClick={() => onSelect(mode, mode === 'playbook' ? selectedPlaybook || undefined : undefined)}
            disabled={mode === 'playbook' && !selectedPlaybook}
            className="text-[12px] bg-accent-blue hover:bg-blue-600 text-white px-4 py-1.5 rounded-md disabled:opacity-50"
          >
            Start Investigation
          </button>
        </div>
      </div>
    </div>
  )
}

function SeverityBadge({ severity, small }: { severity: string; small?: boolean }) {
  const colors: Record<string, string> = {
    critical: 'bg-red-900/30 text-red-400',
    high: 'bg-orange-900/30 text-orange-400',
    medium: 'bg-yellow-900/30 text-yellow-400',
    low: 'bg-blue-900/30 text-blue-400',
    info: 'bg-gray-800 text-gray-400',
  }
  return (
    <span className={`${small ? 'text-[9px] px-1.5 py-0.5' : 'text-[10px] px-2 py-0.5'} rounded ${colors[severity] || colors.info}`}>
      {severity}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    new: 'bg-blue-900/30 text-blue-400',
    investigating: 'bg-yellow-900/30 text-yellow-400',
    resolved: 'bg-green-900/30 text-green-400',
    dismissed: 'bg-gray-800 text-gray-500',
  }
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded ${colors[status] || colors.new}`}>
      {status}
    </span>
  )
}

/** Auto-suggest a matching playbook based on alert type */
function SuggestedPlaybook({ alertType }: { alertType: string }) {
  const [match, setMatch] = useState<{ id: string; name: string; nodes: any[]; category: string } | null>(null)

  useEffect(() => {
    if (!alertType) return
    playbooksApi.list()
      .then((pbs: any) => {
        const found = pbs.find((p: any) =>
          alertType.toLowerCase().includes(p.category?.toLowerCase()) ||
          p.category?.toLowerCase().includes(alertType.toLowerCase()) ||
          p.name?.toLowerCase().includes(alertType.toLowerCase())
        )
        setMatch(found || null)
      })
      .catch(() => {})
  }, [alertType])

  if (!match) return null

  return (
    <div className="bg-green-900/10 border border-green-900/20 rounded-lg px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] bg-green-600 text-white px-1.5 py-0.5 rounded font-medium">Suggested</span>
        <span className="text-[12px] text-green-400">{match.name}</span>
        <span className="text-[10px] text-gray-500">{(match.nodes || []).length} steps</span>
      </div>
      <p className="text-[10px] text-gray-500 mt-0.5">This playbook matches the alert type. Select "Playbook + LLM" when starting the investigation.</p>
    </div>
  )
}
