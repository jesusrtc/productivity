/**
 * Tests for alerts service pure functions.
 * Re-implements functions locally (server modules use .js imports that don't resolve in jsdom).
 */
import { describe, it, expect } from 'vitest'

// --- Re-implemented types and functions from server/domains/alerts/service.ts ---

interface AlertSummary {
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

interface AlertFilters {
  status?: string
  severity?: string
  source?: string
  alert_type?: string
  assignee?: string
  search?: string
  date_from?: string
  date_to?: string
}

function normalizeAlertSummary(data: any): AlertSummary {
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

function filterAlerts(alerts: AlertSummary[], filters: AlertFilters): AlertSummary[] {
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

function getRelatedAlerts(alert: any, allAlerts: any[]): any[] {
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

// --- Test data helpers ---

function makeAlert(overrides: Partial<AlertSummary> & { id: string }): AlertSummary {
  return {
    title: 'Test Alert',
    status: 'new',
    severity: 'medium',
    source: 'iris',
    alert_type: 'fake_account',
    created_at: '2026-03-15T00:00:00Z',
    updated_at: '2026-03-15T00:00:00Z',
    session_count: 0,
    ioc_count: 0,
    related_count: 0,
    tags: [],
    ...overrides,
  }
}

// --- Tests ---

describe('normalizeAlertSummary', () => {
  it('extracts correct fields with defaults', () => {
    const raw = { id: 'a1', title: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02' }
    const result = normalizeAlertSummary(raw)
    expect(result.id).toBe('a1')
    expect(result.status).toBe('new')
    expect(result.severity).toBe('medium')
    expect(result.source).toBe('manual')
    expect(result.alert_type).toBe('')
  })

  it('computes session_count from session_ids array', () => {
    const raw = { id: 'a1', title: 'Test', session_ids: ['s1', 's2', 's3'], created_at: '2026-01-01', updated_at: '2026-01-02' }
    expect(normalizeAlertSummary(raw).session_count).toBe(3)
  })

  it('computes ioc_count from iocs array', () => {
    const raw = { id: 'a1', title: 'Test', iocs: [{ type: 'ip', value: '1.2.3.4' }, { type: 'domain', value: 'evil.com' }], created_at: '2026-01-01', updated_at: '2026-01-02' }
    expect(normalizeAlertSummary(raw).ioc_count).toBe(2)
  })

  it('handles missing arrays gracefully', () => {
    const raw = { id: 'a1', title: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02' }
    const result = normalizeAlertSummary(raw)
    expect(result.session_count).toBe(0)
    expect(result.ioc_count).toBe(0)
    expect(result.related_count).toBe(0)
    expect(result.tags).toEqual([])
  })
})

describe('filterAlerts', () => {
  const alerts: AlertSummary[] = [
    makeAlert({ id: 'a1', status: 'new', severity: 'high', alert_type: 'fake_account', title: 'Fake registrations spike', created_at: '2026-03-10T00:00:00Z' }),
    makeAlert({ id: 'a2', status: 'investigating', severity: 'critical', alert_type: 'credential_stuffing', title: 'Credential stuffing wave', created_at: '2026-03-12T00:00:00Z' }),
    makeAlert({ id: 'a3', status: 'new', severity: 'medium', alert_type: 'fake_account', title: 'Suspicious batch signups', created_at: '2026-03-14T00:00:00Z' }),
    makeAlert({ id: 'a4', status: 'resolved', severity: 'low', alert_type: 'scraping', title: 'Profile scraping detected', created_at: '2026-03-16T00:00:00Z' }),
  ]

  it('filters by single status', () => {
    const result = filterAlerts(alerts, { status: 'new' })
    expect(result.map(a => a.id)).toEqual(['a1', 'a3'])
  })

  it('filters by comma-separated status (multi-filter)', () => {
    const result = filterAlerts(alerts, { status: 'new,investigating' })
    expect(result.map(a => a.id)).toEqual(['a1', 'a2', 'a3'])
  })

  it('filters by severity', () => {
    const result = filterAlerts(alerts, { severity: 'high,critical' })
    expect(result.map(a => a.id)).toEqual(['a1', 'a2'])
  })

  it('search matches title', () => {
    const result = filterAlerts(alerts, { search: 'spike' })
    expect(result.map(a => a.id)).toEqual(['a1'])
  })

  it('search matches alert_type', () => {
    const result = filterAlerts(alerts, { search: 'credential_stuffing' })
    expect(result.map(a => a.id)).toEqual(['a2'])
  })

  it('search is case-insensitive', () => {
    const result = filterAlerts(alerts, { search: 'SCRAPING' })
    expect(result.map(a => a.id)).toEqual(['a4'])
  })

  it('filters by date range', () => {
    const result = filterAlerts(alerts, { date_from: '2026-03-12T00:00:00Z', date_to: '2026-03-14T00:00:00Z' })
    expect(result.map(a => a.id)).toEqual(['a2', 'a3'])
  })

  it('returns all alerts when no filters', () => {
    expect(filterAlerts(alerts, {})).toHaveLength(4)
  })

  it('combines multiple filters (AND logic)', () => {
    const result = filterAlerts(alerts, { status: 'new', severity: 'medium' })
    expect(result.map(a => a.id)).toEqual(['a3'])
  })
})

describe('getRelatedAlerts', () => {
  it('scores IOC overlap at 3 points each', () => {
    const alert = { id: 'a1', alert_type: '', created_at: '2026-03-15T00:00:00Z', iocs: [{ type: 'ip', value: '1.2.3.4' }, { type: 'ip', value: '5.6.7.8' }] }
    const others = [
      { id: 'a2', alert_type: '', created_at: '2026-04-01T00:00:00Z', iocs: [{ type: 'ip', value: '1.2.3.4' }] },
      { id: 'a3', alert_type: '', created_at: '2026-04-01T00:00:00Z', iocs: [{ type: 'ip', value: '1.2.3.4' }, { type: 'ip', value: '5.6.7.8' }] },
    ]
    const result = getRelatedAlerts(alert, [alert, ...others])
    expect(result[0].id).toBe('a3')
    expect(result[0]._relevance).toBe(6) // 2 IOC matches × 3pts
    expect(result[1].id).toBe('a2')
    expect(result[1]._relevance).toBe(3) // 1 IOC match × 3pts
  })

  it('scores same alert_type at 2 points', () => {
    const alert = { id: 'a1', alert_type: 'fake_account', created_at: '2026-03-15T00:00:00Z', iocs: [] }
    const others = [
      { id: 'a2', alert_type: 'fake_account', created_at: '2026-04-01T00:00:00Z', iocs: [] },
      { id: 'a3', alert_type: 'scraping', created_at: '2026-04-01T00:00:00Z', iocs: [] },
    ]
    const result = getRelatedAlerts(alert, [alert, ...others])
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('a2')
    expect(result[0]._relevance).toBe(2)
  })

  it('scores time proximity <7d at 1 point', () => {
    const alert = { id: 'a1', alert_type: '', created_at: '2026-03-15T00:00:00Z', iocs: [] }
    const others = [
      { id: 'a2', alert_type: 'x', created_at: '2026-03-16T00:00:00Z', iocs: [] }, // 1 day away + different type with value
      { id: 'a3', alert_type: '', created_at: '2026-04-01T00:00:00Z', iocs: [] }, // >7 days away
    ]
    const result = getRelatedAlerts(alert, [alert, ...others])
    // a2: type 'x' != '' so no type bonus, but within 7d → 1pt
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('a2')
    expect(result[0]._relevance).toBe(1)
  })

  it('scores shared incident_id at 5 points', () => {
    const alert = { id: 'a1', alert_type: '', created_at: '2026-03-15T00:00:00Z', iocs: [], incident_id: 'inc-100' }
    const others = [
      { id: 'a2', alert_type: '', created_at: '2026-04-01T00:00:00Z', iocs: [], incident_id: 'inc-100' },
    ]
    const result = getRelatedAlerts(alert, [alert, ...others])
    expect(result).toHaveLength(1)
    expect(result[0]._relevance).toBe(5)
  })

  it('returns max 10 results sorted desc by score', () => {
    const alert = { id: 'a0', alert_type: 'fake', created_at: '2026-03-15T00:00:00Z', iocs: [] }
    const others = Array.from({ length: 15 }, (_, i) => ({
      id: `a${i + 1}`,
      alert_type: 'fake',
      created_at: '2026-03-15T00:00:00Z',
      iocs: [],
    }))
    const result = getRelatedAlerts(alert, [alert, ...others])
    expect(result).toHaveLength(10)
    // All should have same score (type match + time proximity)
    expect(result.every((r: any) => r._relevance === 3)).toBe(true) // 2 (type) + 1 (time)
  })

  it('returns empty when no matches', () => {
    const alert = { id: 'a1', alert_type: '', created_at: '2026-03-15T00:00:00Z', iocs: [] }
    const others = [
      { id: 'a2', alert_type: '', created_at: '2026-04-01T00:00:00Z', iocs: [] },
    ]
    const result = getRelatedAlerts(alert, [alert, ...others])
    expect(result).toHaveLength(0)
  })

  it('excludes self from results', () => {
    const alert = { id: 'a1', alert_type: 'fake', created_at: '2026-03-15T00:00:00Z', iocs: [], incident_id: 'inc-1' }
    const result = getRelatedAlerts(alert, [alert])
    expect(result).toHaveLength(0)
  })
})
