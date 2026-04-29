import { useState, useEffect } from 'react'
import { alertsApi } from '../../api'
import type { AlertSummary } from '../../types/alert'

interface Props {
  alertId?: string
  sessionId?: string
}

/** Sidebar showing related alerts during an investigation */
export function RelatedAlertsSidebar({ alertId, sessionId }: Props) {
  const [related, setRelated] = useState<AlertSummary[]>([])
  const [linkedAlertId, setLinkedAlertId] = useState<string | null>(alertId || null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (alertId) { setLinkedAlertId(alertId); return }
    if (!sessionId) return
    alertsApi.list()
      .then(alerts => {
        const linked = alerts.find((a: any) => (a.session_ids || []).includes(sessionId))
        if (linked) setLinkedAlertId(linked.id)
      })
      .catch(() => {})
  }, [alertId, sessionId])

  useEffect(() => {
    if (!linkedAlertId) return
    alertsApi.related(linkedAlertId)
      .then(setRelated)
      .catch(() => {})
  }, [linkedAlertId])

  if (!linkedAlertId && related.length === 0) return null

  return (
    <div className="border-t border-surface-3 flex-shrink-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 w-full text-left hover:bg-white/[0.02]"
      >
        <span className="text-[10px] bg-orange-600 text-white px-1.5 py-0.5 rounded font-medium">Alerts</span>
        <span className="text-[10px] text-gray-500">{related.length} related</span>
        <span className="text-[10px] text-gray-600 ml-auto">{open ? '\u25BC' : '\u25B2'}</span>
      </button>
      {open && related.length > 0 && (
        <div className="px-3 pb-2 space-y-1">
          {related.map(r => (
            <div key={r.id} className="flex items-center gap-2 px-2 py-1.5 rounded bg-surface-2/40 text-[10px]">
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                r.severity === 'critical' ? 'bg-red-500' : r.severity === 'high' ? 'bg-orange-500' : r.severity === 'medium' ? 'bg-yellow-500' : 'bg-blue-400'
              }`} />
              <div className="flex-1 min-w-0">
                <div className="text-gray-300 truncate">{r.title}</div>
                <div className="text-gray-600">{r.alert_type} | {r.status} | {r.ioc_count} IOCs</div>
              </div>
            </div>
          ))}
        </div>
      )}
      {open && related.length === 0 && linkedAlertId && (
        <p className="px-3 pb-2 text-[10px] text-gray-600">No related alerts found</p>
      )}
    </div>
  )
}
