import { Router } from 'express'
import { sanitizeId } from '../../middleware/sanitize.js'
import { loadAlert, loadAllAlerts, saveAlert, deleteAlert } from './store.js'
import { normalizeAlertSummary, filterAlerts, getRelatedAlerts } from './service.js'
import type { AlertFilters } from './service.js'

interface AlertsRouterConfig {
  ALERTS_DIR: string
  initSync: (dir: string) => void
  startSync: (opts: { intervalMs: number; lookbackDays: number }) => void
  stopSync: () => void
  runSync: (lookbackDays: number) => Promise<any>
  getSyncStatus: () => any
}

export default function createAlertsRouter(config: AlertsRouterConfig): Router {
  const router = Router()
  const { ALERTS_DIR, initSync, startSync, stopSync, runSync, getSyncStatus } = config

  initSync(ALERTS_DIR)

  // SYNC ROUTES FIRST (before :id to fix Express route shadowing bug)
  router.get('/sync/status', (_req, res) => { res.json(getSyncStatus()) })

  router.post('/sync', async (req, res) => {
    const lookbackDays = Number(req.body?.lookbackDays) || 7
    res.json(await runSync(lookbackDays))
  })

  router.post('/sync/start', (req, res) => {
    startSync({ intervalMs: req.body.intervalMs || 5 * 60 * 1000, lookbackDays: req.body.lookbackDays || 7 })
    res.json({ success: true, ...getSyncStatus() })
  })

  router.post('/sync/stop', (_req, res) => {
    stopSync()
    res.json({ success: true, ...getSyncStatus() })
  })

  // LIST alerts
  router.get('/', (req, res) => {
    const all = loadAllAlerts(ALERTS_DIR).map(normalizeAlertSummary)
    const filters = req.query as AlertFilters
    const filtered = filterAlerts(all, filters)
    filtered.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    res.json(filtered)
  })

  // RELATED alerts
  router.get('/:id/related', (req, res) => {
    const alert = loadAlert(ALERTS_DIR, sanitizeId(req.params.id))
    if (!alert) { res.json([]); return }
    res.json(getRelatedAlerts(alert, loadAllAlerts(ALERTS_DIR)))
  })

  // GET single alert
  router.get('/:id', (req, res) => {
    const alert = loadAlert(ALERTS_DIR, sanitizeId(req.params.id))
    if (!alert) { res.status(404).json({ error: 'Alert not found' }); return }
    res.json(alert)
  })

  // CREATE alert
  router.post('/', (req, res) => {
    const id = sanitizeId(req.body.id || `alert-${Date.now()}`)
    const alert = {
      id,
      title: req.body.title || 'Untitled Alert',
      description: req.body.description || '',
      status: req.body.status || 'new',
      severity: req.body.severity || 'medium',
      source: req.body.source || 'manual',
      alert_type: req.body.alert_type || '',
      assignee: req.body.assignee || '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      session_ids: [],
      related_alert_ids: [],
      iocs: req.body.iocs || [],
      metadata: req.body.metadata || {},
      tags: req.body.tags || [],
    }
    try {
      saveAlert(ALERTS_DIR, id, alert)
      res.json(alert)
    } catch {
      res.status(400).json({ error: 'Invalid ID' })
    }
  })

  // UPDATE alert
  router.patch('/:id', (req, res) => {
    const existing = loadAlert(ALERTS_DIR, sanitizeId(req.params.id))
    if (!existing) { res.status(404).json({ error: 'Alert not found' }); return }
    const updated = { ...existing, ...req.body, id: existing.id, updated_at: new Date().toISOString() }
    try {
      saveAlert(ALERTS_DIR, existing.id, updated)
      res.json(updated)
    } catch {
      res.status(500).json({ error: 'Failed to update alert' })
    }
  })

  // DELETE alert
  router.delete('/:id', (req, res) => {
    deleteAlert(ALERTS_DIR, sanitizeId(req.params.id))
    res.json({ success: true })
  })

  return router
}
