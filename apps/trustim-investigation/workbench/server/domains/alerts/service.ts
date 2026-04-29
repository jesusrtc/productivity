export interface AlertSummary {
  id: string
  external_id?: string
  title: string
  status: string
  severity: string
  source: string
  alert_type: string
  assignee?: string
  created_at: string
  updated_at: string
  session_count: number
  ioc_count: number
  related_count: number
  tags: string[]
}

export interface AlertFilters {
  status?: string
  severity?: string
  source?: string
  alert_type?: string
  assignee?: string
  search?: string
  date_from?: string
  date_to?: string
}

export function normalizeAlertSummary(data: any): AlertSummary {
  return {
    id: data.id,
    external_id: data.external_id,
    title: data.title,
    status: data.status || 'new',
    severity: data.severity || 'medium',
    source: data.source || 'manual',
    alert_type: data.alert_type || '',
    assignee: data.assignee,
    created_at: data.created_at,
    updated_at: data.updated_at,
    session_count: (data.session_ids || []).length,
    ioc_count: (data.iocs || []).length,
    related_count: (data.related_alert_ids || []).length,
    tags: data.tags || [],
  }
}

export function filterAlerts(alerts: AlertSummary[], filters: AlertFilters): AlertSummary[] {
  let result = alerts
  if (filters.status) { const s = filters.status.split(','); result = result.filter(a => s.includes(a.status)) }
  if (filters.severity) { const s = filters.severity.split(','); result = result.filter(a => s.includes(a.severity)) }
  if (filters.source) { const s = filters.source.split(','); result = result.filter(a => s.includes(a.source)) }
  if (filters.alert_type) result = result.filter(a => a.alert_type === filters.alert_type)
  if (filters.assignee) result = result.filter(a => a.assignee === filters.assignee)
  if (filters.search) { const q = filters.search.toLowerCase(); result = result.filter(a => a.title.toLowerCase().includes(q) || a.alert_type.toLowerCase().includes(q)) }
  if (filters.date_from) result = result.filter(a => a.created_at >= filters.date_from!)
  if (filters.date_to) result = result.filter(a => a.created_at <= filters.date_to!)
  return result
}

export function getRelatedAlerts(alert: any, allAlerts: any[]): any[] {
  const alertIocs = new Set((alert.iocs || []).map((i: { type: string; value: string }) => `${i.type}:${i.value}`))
  const alertType = alert.alert_type
  const alertDate = new Date(alert.created_at).getTime()
  const sevenDays = 7 * 24 * 60 * 60 * 1000

  return allAlerts
    .filter(other => other.id !== alert.id)
    .map(other => {
      let score = 0
      const otherIocs = (other.iocs || []).map((i: { type: string; value: string }) => `${i.type}:${i.value}`)
      for (const ioc of otherIocs) { if (alertIocs.has(ioc)) score += 3 }
      if (other.alert_type === alertType && alertType) score += 2
      if (Math.abs(new Date(other.created_at).getTime() - alertDate) < sevenDays) score += 1
      if (other.incident_id && other.incident_id === alert.incident_id) score += 5
      if (score === 0) return null
      return { ...other, _relevance: score }
    })
    .filter(Boolean)
    .sort((a: any, b: any) => b._relevance - a._relevance)
    .slice(0, 10)
}
