import { useState, useEffect, useMemo } from 'react'
import { sessionsApi, automationsApi, playbooksApi, investigationsApi, miscApi } from '../../api'
import { useSessionStore } from '../../store/session'
import { useAlertStore } from '../../store/alert'
import { createDemoSession } from '../../utils/demo-session'

interface Props {
  onOpenInvestigation: (sessionId: string) => void
  onNewInvestigation: () => void
  onNavigateToAlerts: () => void
}

export function HomePage({ onOpenInvestigation, onNewInvestigation, onNavigateToAlerts }: Props) {
  const sessionList = useSessionStore((s) => s.sessionList)
  const alerts = useAlertStore((s) => s.alerts)
  const [bgInvestigations, setBgInvestigations] = useState<Array<{ id: string; sessionId: string; prompt: string; status: string; nodeCount: number }>>([])
  const [automationCount, setAutomationCount] = useState(0)
  const [playbookCount, setPlaybookCount] = useState(0)

  useEffect(() => {
    sessionsApi.list().then(list => {
      useSessionStore.getState().setSessionList(Array.isArray(list) ? list : [])
    }).catch(() => {})
    automationsApi.list().then(d => setAutomationCount(Array.isArray(d) ? d.length : 0)).catch(() => {})
    playbooksApi.list().then(d => setPlaybookCount(Array.isArray(d) ? d.length : 0)).catch(() => setPlaybookCount(0))
    useAlertStore.getState().fetchAlerts()
  }, [])

  useEffect(() => {
    const poll = () => { investigationsApi.list().then(d => setBgInvestigations(d as any)).catch(() => {}) }
    poll()
    const timer = setInterval(poll, 5000)
    return () => clearInterval(timer)
  }, [])

  const recentSessions = [...sessionList]
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 8)

  const newAlerts = alerts.filter(a => a.status === 'new').length
  const investigatingAlerts = alerts.filter(a => a.status === 'investigating').length
  const runningInvestigations = bgInvestigations.filter(i => i.status === 'running')

  // ROI calculation
  const roi = useMemo(() => {
    const totalInvestigations = sessionList.length
    const totalNodes = sessionList.reduce((sum, s) => sum + (s.node_count || 0), 0)
    // Estimates: each node = 1 query. Manual query cycle: ~8 min (write SQL + run + analyze). Automated: ~30s.
    const manualMinPerNode = 8
    const autoMinPerNode = 0.5
    const manualHours = (totalNodes * manualMinPerNode) / 60
    const autoHours = (totalNodes * autoMinPerNode) / 60
    const savedHours = Math.max(0, manualHours - autoHours)
    // Cost: $75/hr average analyst cost
    const costPerHour = 75
    const savedDollars = savedHours * costPerHour
    return { totalInvestigations, totalNodes, manualHours, autoHours, savedHours, savedDollars }
  }, [sessionList])

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto py-10 px-6">
        <h1 className="text-2xl font-medium text-gray-200 mb-1">Juniper</h1>
        <p className="text-[13px] text-gray-500 mb-6">Trust SOAR Platform</p>

        {/* Stats cards */}
        <div className="grid grid-cols-5 gap-3 mb-8">
          <StatCard label="Investigations" value={sessionList.length} color="text-accent-blue" />
          <StatCard label="Alerts" value={alerts.length} sub={newAlerts > 0 ? `${newAlerts} new` : undefined} color="text-orange-400" />
          <StatCard label="Automations" value={automationCount} color="text-purple-400" />
          <StatCard label="Playbooks" value={playbookCount} color="text-green-400" />
          <StatCard label="Hours Saved" value={Math.round(roi.savedHours)} sub={`~$${Math.round(roi.savedDollars).toLocaleString()}`} color="text-accent-cyan" />
        </div>

        {/* ROI widget */}
        {roi.totalNodes > 0 && (
          <div className="bg-surface-2/30 border border-white/[0.06] rounded-xl p-4 mb-8">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[12px] text-gray-500 uppercase tracking-wider">Time Saved with Juniper</h3>
              <span className="text-[10px] text-gray-600">{roi.totalNodes} queries across {roi.totalInvestigations} investigations</span>
            </div>
            <div className="flex items-center gap-6">
              {/* Big number: time saved */}
              <div>
                <div className="text-3xl font-bold text-accent-cyan tabular-nums">{Math.round(roi.savedHours)}h</div>
                <div className="text-[11px] text-gray-500">saved</div>
              </div>
              {/* Stacked bar: saved (green) + actual time used (small blue) */}
              <div className="flex-1">
                <div className="h-3 bg-surface-3 rounded-full overflow-hidden flex">
                  <div className="h-full bg-green-500/70 rounded-l-full" style={{ width: `${(roi.savedHours / roi.manualHours) * 100}%` }} title={`${roi.savedHours.toFixed(1)}h saved`} />
                  <div className="h-full bg-accent-blue/50 rounded-r-full" style={{ width: `${(roi.autoHours / roi.manualHours) * 100}%` }} title={`${roi.autoHours.toFixed(1)}h actual`} />
                </div>
                <div className="flex justify-between mt-1.5 text-[10px]">
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-green-500/70 inline-block" /> <span className="text-gray-400">{roi.savedHours.toFixed(1)}h saved</span></span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-accent-blue/50 inline-block" /> <span className="text-gray-400">{roi.autoHours.toFixed(1)}h with Juniper</span></span>
                  </div>
                  <span className="text-gray-500">Would have taken {roi.manualHours.toFixed(1)}h manually</span>
                </div>
              </div>
              {/* Dollar savings */}
              <div className="text-right">
                <div className="text-lg font-semibold text-green-400 tabular-nums">~${Math.round(roi.savedDollars).toLocaleString()}</div>
                <div className="text-[10px] text-gray-500">est. savings</div>
              </div>
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div className="flex gap-3 mb-8">
          <button onClick={onNewInvestigation} className="bg-accent-blue hover:bg-blue-600 text-white text-[13px] px-5 py-2.5 rounded-lg transition-colors">
            New Investigation
          </button>
          <button onClick={onNavigateToAlerts} className="bg-surface-2 hover:bg-surface-3 text-gray-300 text-[13px] px-5 py-2.5 rounded-lg border border-white/[0.06] transition-colors">
            Alert Queue{newAlerts > 0 ? ` (${newAlerts} new)` : ''}
          </button>
          <button onClick={() => {
            const demo = createDemoSession()
            useSessionStore.getState().loadSession(demo)
            window.dispatchEvent(new CustomEvent('openInvestigationTab', { detail: { sessionId: demo.id, name: demo.name } }))
          }} className="bg-surface-2 hover:bg-surface-3 text-gray-300 text-[13px] px-5 py-2.5 rounded-lg border border-white/[0.06] transition-colors">
            Load Demo
          </button>
          <button onClick={async () => {
            const { useToastStore } = await import('../../store/toast')
            useToastStore.getState().addToast('Syncing alerts from IRIS...', 'info', 3000)
            await useAlertStore.getState().triggerSync()
            useAlertStore.getState().fetchAlerts()
            useToastStore.getState().addToast('Alert sync complete', 'success', 3000)
          }} className="bg-surface-2 hover:bg-surface-3 text-gray-300 text-[13px] px-5 py-2.5 rounded-lg border border-white/[0.06] transition-colors">
            Sync Alerts
          </button>
          {(alerts.length === 0 || playbookCount === 0) && (
            <button onClick={async () => {
              const { useToastStore } = await import('../../store/toast')
              try {
                const data = await miscApi.seedDemo()
                useToastStore.getState().addToast(`Seeded ${data.seeded.alerts} alerts + ${data.seeded.playbooks} playbooks`, 'success', 4000)
                // Refresh all counts
                useAlertStore.getState().fetchAlerts()
                playbooksApi.list().then(d => setPlaybookCount(Array.isArray(d) ? d.length : 0)).catch(() => {})
                automationsApi.list().then(d => setAutomationCount(Array.isArray(d) ? d.length : 0)).catch(() => {})
              } catch {
                useToastStore.getState().addToast('Failed to seed demo data', 'error', 4000)
              }
            }} className="bg-green-900/30 hover:bg-green-900/50 text-green-400 text-[13px] px-5 py-2.5 rounded-lg border border-green-900/40 transition-colors">
              Seed Demo Data
            </button>
          )}
        </div>

        {/* Running investigations */}
        {runningInvestigations.length > 0 && (
          <div className="mb-8">
            <h3 className="text-[12px] text-gray-500 uppercase tracking-wider mb-3">Running Investigations</h3>
            <div className="space-y-2">
              {runningInvestigations.map(inv => (
                <div key={inv.id} onClick={() => onOpenInvestigation(inv.sessionId)}
                  className="flex items-center gap-3 px-4 py-3 rounded-lg bg-surface-2/40 border border-white/[0.06] cursor-pointer hover:bg-surface-2/60 transition-colors">
                  <span className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse flex-shrink-0" />
                  <span className="text-[13px] text-gray-200 truncate flex-1">{inv.prompt.slice(0, 80)}</span>
                  <span className="text-[11px] text-gray-500 tabular-nums">{inv.nodeCount} steps</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent investigations */}
        <div>
          <h3 className="text-[12px] text-gray-500 uppercase tracking-wider mb-3">Recent Investigations</h3>
          {recentSessions.length === 0 ? (
            <p className="text-[13px] text-gray-500 py-6">No investigations yet. Start one from the alert queue or click "New Investigation".</p>
          ) : (
            <div className="space-y-1">
              {recentSessions.map(s => (
                <div key={s.id} onClick={() => onOpenInvestigation(s.id)}
                  className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-white/[0.03] cursor-pointer transition-colors group">
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] text-gray-200 truncate">{s.name}</div>
                    <div className="text-[11px] text-gray-500">{s.node_count || 0} nodes | {timeAgo(s.updated_at)}</div>
                  </div>
                  <span className="text-[10px] text-gray-600 group-hover:text-accent-blue transition-colors">Open</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, color }: { label: string; value: number; sub?: string; color: string }) {
  return (
    <div className="bg-surface-2/30 border border-white/[0.06] rounded-xl px-4 py-3">
      <div className={`text-xl font-bold tabular-nums ${color}`}>{value}</div>
      <div className="text-[11px] text-gray-500">{label}</div>
      {sub && <div className="text-[10px] text-gray-600 mt-0.5">{sub}</div>}
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
