import { useState, useEffect, useMemo } from 'react'
import { investigationsApi, setupApi, playbooksApi } from '../../api'
import { useAlertStore } from '../../store/alert'
import { useSessionStore } from '../../store/session'
import type { AlertStatus, AlertSeverity } from '../../types/alert'
import { AlertDetail } from './AlertDetail'

const STATUS_ORDER: AlertStatus[] = ['new', 'investigating', 'resolved', 'dismissed']
const SEVERITY_COLORS: Record<AlertSeverity, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-blue-400',
  info: 'bg-gray-400',
}
const SEVERITY_TEXT: Record<AlertSeverity, string> = {
  critical: 'text-red-400',
  high: 'text-orange-400',
  medium: 'text-yellow-400',
  low: 'text-blue-400',
  info: 'text-gray-400',
}

interface Props {
  onNavigateToInvestigation: (sessionId?: string, name?: string) => void
}

export function AlertQueue({ onNavigateToInvestigation }: Props) {
  const alerts = useAlertStore((s) => s.alerts)
  const loading = useAlertStore((s) => s.loading)
  const filters = useAlertStore((s) => s.filters)
  const fetchAlerts = useAlertStore((s) => s.fetchAlerts)
  const setFilters = useAlertStore((s) => s.setFilters)
  const clearFilters = useAlertStore((s) => s.clearFilters)
  const selectAlert = useAlertStore((s) => s.selectAlert)
  const selectedAlertId = useAlertStore((s) => s.selectedAlertId)
  const syncStatus = useAlertStore((s) => s.syncStatus)
  const triggerSync = useAlertStore((s) => s.triggerSync)
  const deleteAlert = useAlertStore((s) => s.deleteAlert)

  const [search, setSearch] = useState(filters.search || '')
  const [statusFilter, setStatusFilter] = useState<AlertStatus | 'all'>('all')
  const [showCreate, setShowCreate] = useState(false)
  const [bgInvestigations, setBgInvestigations] = useState<Array<{ id: string; sessionId: string; prompt: string; status: string; nodeCount: number; startedAt: string }>>([])

  useEffect(() => { fetchAlerts() }, [])

  // Poll for background investigations
  useEffect(() => {
    const poll = () => {
      investigationsApi.list().then(setBgInvestigations).catch(() => {})
    }
    poll()
    const timer = setInterval(poll, 3000)
    return () => clearInterval(timer)
  }, [])

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: alerts.length }
    for (const a of alerts) counts[a.status] = (counts[a.status] || 0) + 1
    return counts
  }, [alerts])

  const displayed = useMemo(() => {
    let list = alerts
    if (statusFilter !== 'all') list = list.filter(a => a.status === statusFilter)
    return list
  }, [alerts, statusFilter])

  const handleSearch = (q: string) => {
    setSearch(q)
    setFilters({ search: q || undefined })
  }

  const handleStartInvestigation = async (alertId: string, mode?: string, playbookId?: string) => {
    try {
      // Check if Claude bridge is available before attempting to start
      const bridgeRes = await setupApi.bridgeStatus().catch(() => ({ available: false, ready: false, message: '' }))
      if (!bridgeRes.available) {
        const { useToastStore } = await import('../../store/toast')
        useToastStore.getState().addToast(
          'Claude CLI not found — background investigations require the claude CLI. You can still open investigations manually from the chat.',
          'warning', 8000
        )
        // Fall back: open an empty investigation tab instead of failing silently
        const sessionId = crypto.randomUUID()
        const alert = alerts.find(a => a.id === alertId)
        const sessionName = `Alert: ${alert?.title.slice(0, 50) || alertId}`
        onNavigateToInvestigation(sessionId, sessionName)
        return
      }

      const alert = alerts.find(a => a.id === alertId)
      if (!alert) { console.error('Alert not found:', alertId); return }

      const fullAlert = await useAlertStore.getState().fetchAlert(alertId)
      if (!fullAlert) { console.error('Failed to fetch alert:', alertId); return }

      const sessionId = crypto.randomUUID()
      const sessionName = `Alert: ${fullAlert.title.slice(0, 50)}`
      const prompt = [
        `Investigate this alert: ${fullAlert.title}`,
        fullAlert.description || '',
        `Alert type: ${fullAlert.alert_type || 'unknown'}, Severity: ${fullAlert.severity}`,
        fullAlert.iocs?.length > 0 ? `IOCs: ${fullAlert.iocs.map((i: { type: string; value: string }) => `${i.type}:${i.value}`).join(', ')}` : '',
        mode === 'autonomous' ? '\n[MODE: Autonomous — you have access to all investigation skills. Decide which queries to run and how to investigate, same as a CLI invocation.]' : '',
      ].filter(Boolean).join('\n')

      // If playbook mode, run playbook first then background agent for remaining analysis
      if (mode === 'playbook' && playbookId) {
        // Start playbook execution
        await playbooksApi.run(playbookId!, {}, sessionId)
        // Start background agent — it will see playbook results via the session file and decide if more investigation is needed
        await investigationsApi.start(sessionId, prompt + '\n\n[MODE: Playbook + LLM — A structured playbook is running investigation queries for this alert. Wait for the playbook results to appear in the session, then analyze them. If the playbook results provide enough evidence for a conclusion, summarize findings. If not, use the skills plugin to run additional queries. You have full access to all investigation skills — use Read/Glob to find relevant SQL templates in skills/actions/.]', alertId, sessionName)
      } else {
        // Pure background agent investigation
        await investigationsApi.start(sessionId, prompt, alertId, sessionName)
      }

      await useAlertStore.getState().linkSession(alertId, sessionId)
      await useAlertStore.getState().transitionStatus(alertId, 'investigating')

      fetchAlerts()
      selectAlert(null)
      onNavigateToInvestigation(sessionId, sessionName)
    } catch (err) {
      console.error('Start investigation error:', err)
    }
  }

  return (
    <div className="h-full flex">
      {/* Main alert list */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-3 flex-shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-medium text-gray-200">Alerts</h2>
            <span className="text-[12px] text-gray-500 tabular-nums">{alerts.length} total</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => triggerSync()}
              disabled={syncStatus.syncing}
              className="text-[11px] bg-surface-3 hover:bg-surface-4 text-gray-300 px-3 py-1.5 rounded-md transition-colors disabled:text-gray-600"
            >
              {syncStatus.syncing ? 'Syncing...' : 'Sync InResponse (7d)'}
            </button>
            {syncStatus.lastSync && (
              <span className="text-[10px] text-gray-600">Last: {timeAgo(syncStatus.lastSync)}</span>
            )}
            <button
              onClick={() => setShowCreate(true)}
              className="text-[11px] bg-accent-blue/20 hover:bg-accent-blue/30 text-accent-blue px-3 py-1.5 rounded-md transition-colors"
            >
              + Create
            </button>
          </div>
        </div>

        {/* Background investigations status */}
        {bgInvestigations.length > 0 && (
          <div className="px-6 py-2 border-b border-surface-3 flex-shrink-0">
            <h4 className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">Active Investigations ({bgInvestigations.filter(i => i.status === 'running').length} running)</h4>
            <div className="space-y-1">
              {bgInvestigations.map(inv => (
                <div
                  key={inv.id}
                  className="flex items-center gap-2 text-[12px] px-2 py-1.5 rounded-md cursor-pointer hover:bg-white/[0.04] transition-colors"
                  onClick={() => onNavigateToInvestigation(inv.sessionId, inv.prompt?.slice(0, 50))}
                >
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    inv.status === 'running' ? 'bg-yellow-400 animate-pulse'
                    : inv.status === 'completed' ? 'bg-green-400'
                    : inv.status === 'failed' ? 'bg-red-400'
                    : 'bg-gray-500'
                  }`} />
                  <span className="text-gray-300 truncate flex-1">{inv.prompt.slice(0, 60)}...</span>
                  <span className="text-gray-500 tabular-nums">{inv.nodeCount} steps</span>
                  <span className="text-[10px] text-accent-blue hover:text-blue-400">View</span>
                  {inv.status === 'running' && (
                    <button
                      onClick={(e) => { e.stopPropagation(); investigationsApi.stop(inv.sessionId).then(() => {
                        setBgInvestigations(prev => prev.filter(i => i.id !== inv.id))
                      })}}
                      className="text-[10px] text-red-400 hover:text-red-300"
                    >
                      Stop
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Search + Status tabs */}
        <div className="px-6 py-3 border-b border-surface-3 space-y-2 flex-shrink-0">
          <input
            type="text"
            value={search}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Search alerts..."
            className="w-full bg-surface-2/60 border border-white/[0.06] rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue/50"
          />
          <div className="flex gap-1">
            {(['all', ...STATUS_ORDER] as const).map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`text-[11px] px-3 py-1 rounded-md transition-colors ${
                  statusFilter === s
                    ? 'bg-accent-blue/20 text-accent-blue'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-surface-3'
                }`}
              >
                {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
                {statusCounts[s] ? ` (${statusCounts[s]})` : ''}
              </button>
            ))}
          </div>
        </div>

        {/* Alert list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-6 space-y-2">
              {[1,2,3,4,5].map(i => (
                <div key={i} className="bg-white/[0.02] rounded-lg px-4 py-3 animate-pulse">
                  <div className="h-3 bg-surface-3 rounded w-3/4 mb-2" />
                  <div className="h-2 bg-surface-3 rounded w-1/2" />
                </div>
              ))}
            </div>
          ) : displayed.length === 0 ? (
            <div className="p-6 text-center py-20">
              <div className="text-3xl mb-3 opacity-20">{'\u{1F514}'}</div>
              <p className="text-[14px] text-gray-400 mb-1">
                {search ? 'No matching alerts' : 'No alerts yet'}
              </p>
              <p className="text-[12px] text-gray-500">
                Click "Sync InResponse" to pull recent alerts, or create one manually.
              </p>
            </div>
          ) : (
            <div className="p-3 space-y-1">
              {displayed.map(a => (
                <div
                  key={a.id}
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-colors ${
                    selectedAlertId === a.id
                      ? 'bg-accent-blue/10 border border-accent-blue/20'
                      : 'bg-white/[0.02] hover:bg-white/[0.05] border border-transparent'
                  }`}
                  onClick={() => selectAlert(selectedAlertId === a.id ? null : a.id)}
                >
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${SEVERITY_COLORS[a.severity]}`} title={a.severity} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] text-gray-200 truncate">{a.title}</span>
                      {a.external_id && <span className="text-[10px] text-gray-600 font-mono">#{a.external_id}</span>}
                    </div>
                    <div className="flex items-center gap-2 text-[11px] text-gray-500 mt-0.5">
                      <span className={SEVERITY_TEXT[a.severity]}>{a.severity}</span>
                      <span className="text-gray-600">|</span>
                      <span>{a.alert_type || 'untyped'}</span>
                      <span className="text-gray-600">|</span>
                      <span>{timeAgo(a.created_at)}</span>
                      {a.session_count > 0 && (
                        <>
                          <span className="text-gray-600">|</span>
                          <span className="text-accent-cyan">{a.session_count} session{a.session_count > 1 ? 's' : ''}</span>
                        </>
                      )}
                      {a.ioc_count > 0 && <><span className="text-gray-600">|</span><span>{a.ioc_count} IOCs</span></>}
                      {a.related_count > 0 && <><span className="text-gray-600">|</span><span>{a.related_count} related</span></>}
                    </div>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded flex-shrink-0 ${
                    a.status === 'new' ? 'bg-blue-900/30 text-blue-400'
                    : a.status === 'investigating' ? 'bg-yellow-900/30 text-yellow-400'
                    : a.status === 'resolved' ? 'bg-green-900/30 text-green-400'
                    : 'bg-gray-800 text-gray-500'
                  }`}>
                    {a.status}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); if (confirm(`Delete "${a.title}"?`)) deleteAlert(a.id) }}
                    className="text-gray-600 hover:text-red-400 transition-colors flex-shrink-0"
                    title="Delete"
                  >
                    {'\u2715'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-2 border-t border-surface-3 flex items-center justify-between text-[11px] text-gray-500 flex-shrink-0">
          <span>{displayed.length} of {alerts.length} alerts</span>
          {Object.keys(filters).length > 0 && (
            <button onClick={clearFilters} className="text-accent-blue hover:text-blue-400 transition-colors">Clear filters</button>
          )}
        </div>
      </div>

      {/* Alert fullAlert side panel */}
      {selectedAlertId && (
        <div className="w-[420px] border-l border-surface-3 flex-shrink-0">
          <AlertDetail
            alertId={selectedAlertId}
            onClose={() => selectAlert(null)}
            onStartInvestigation={handleStartInvestigation}
            onNavigateToSession={(sid) => onNavigateToInvestigation(sid)}
          />
        </div>
      )}

      {/* Create alert modal */}
      {showCreate && <CreateAlertModal onClose={() => setShowCreate(false)} />}
    </div>
  )
}

function CreateAlertModal({ onClose }: { onClose: () => void }) {
  const createAlert = useAlertStore((s) => s.createAlert)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [severity, setSeverity] = useState<AlertSeverity>('medium')
  const [alertType, setAlertType] = useState('')

  const handleSubmit = async () => {
    if (!title.trim()) return
    await createAlert({ title: title.trim(), description: description.trim(), severity, alert_type: alertType })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[110]" onClick={onClose}>
      <div className="bg-surface-1 border border-surface-3 rounded-xl p-6 w-[420px]" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-medium text-gray-200 mb-4">Create Alert</h3>
        <div className="space-y-3">
          <input type="text" value={title} onChange={e => setTitle(e.target.value)} placeholder="Alert title"
            className="w-full bg-surface-2 border border-surface-4 rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue/50" autoFocus />
          <textarea value={description} onChange={e => setDescription(e.target.value)} placeholder="Description (optional)" rows={3}
            className="w-full bg-surface-2 border border-surface-4 rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue/50 resize-none" />
          <div className="flex gap-2">
            <select value={severity} onChange={e => setSeverity(e.target.value as AlertSeverity)}
              className="bg-surface-2 border border-surface-4 rounded-lg px-2 py-2 text-[12px] text-gray-300 focus:outline-none">
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Info</option>
            </select>
            <input type="text" value={alertType} onChange={e => setAlertType(e.target.value)} placeholder="Type (e.g., ATO, Fake Accounts)"
              className="flex-1 bg-surface-2 border border-surface-4 rounded-lg px-3 py-2 text-[12px] text-gray-200 placeholder-gray-500 focus:outline-none" />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="text-[12px] text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-md transition-colors">Cancel</button>
          <button onClick={handleSubmit} disabled={!title.trim()}
            className="text-[12px] bg-accent-blue hover:bg-blue-600 text-white px-4 py-1.5 rounded-md transition-colors disabled:opacity-50">Create</button>
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
  return `${d}d ago`
}
