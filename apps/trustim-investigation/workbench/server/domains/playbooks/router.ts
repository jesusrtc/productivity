import { Router } from 'express'
import { sanitizeId } from '../../middleware/sanitize.js'
import { findAutomation } from '../automations/store.js'
import { runPlaybook, getPlaybookExecutions, getPlaybookExecution, cancelPlaybookExecution } from '../../playbook-runner.js'
import { loadPlaybook, loadPlaybooks, savePlaybook, deletePlaybook, playbookExists } from './store.js'
import { computeEntryNodeIds } from './service.js'

export interface PlaybooksRouterConfig {
  PLAYBOOKS_DIR: string
  SESSIONS_DIR: string
  REPO_ROOT: string
  broadcast: (message: object) => void
}

export default function createPlaybooksRouter(config: PlaybooksRouterConfig): Router {
  const { PLAYBOOKS_DIR, SESSIONS_DIR, REPO_ROOT, broadcast } = config
  const router = Router()

  // ----- Playbooks CRUD -----

  router.get('/playbooks', (_req, res) => {
    res.json(loadPlaybooks(PLAYBOOKS_DIR))
  })

  router.get('/playbooks/:id', (req, res) => {
    const data = loadPlaybook(PLAYBOOKS_DIR, sanitizeId(req.params.id))
    if (!data) { res.status(404).json({ error: 'Not found' }); return }
    res.json(data)
  })

  router.post('/playbooks', (req, res) => {
    const id = `pb-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    const playbook = { ...req.body, id, version: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
    playbook.entry_node_ids = computeEntryNodeIds(playbook.nodes || [], playbook.edges || [])
    if (!savePlaybook(PLAYBOOKS_DIR, id, playbook)) { res.status(400).json({ error: 'Invalid' }); return }
    res.json(playbook)
  })

  router.put('/playbooks/:id', (req, res) => {
    const id = sanitizeId(req.params.id)
    const existing = loadPlaybook(PLAYBOOKS_DIR, id)
    if (!existing) { res.status(404).json({ error: 'Not found' }); return }
    const updated = { ...existing, ...req.body, id: existing.id, version: (existing.version || 0) + 1, created_at: existing.created_at, updated_at: new Date().toISOString() }
    updated.entry_node_ids = computeEntryNodeIds(updated.nodes || [], updated.edges || [])
    savePlaybook(PLAYBOOKS_DIR, id, updated)
    res.json(updated)
  })

  router.delete('/playbooks/:id', (req, res) => {
    deletePlaybook(PLAYBOOKS_DIR, sanitizeId(req.params.id))
    res.json({ success: true })
  })

  // Run a playbook
  router.post('/playbooks/:id/run', async (req, res) => {
    const id = sanitizeId(req.params.id)
    const playbook = loadPlaybook(PLAYBOOKS_DIR, id)
    if (!playbook) { res.status(404).json({ error: 'Not found' }); return }
    const { inputs = {}, sessionId } = req.body
    if (!sessionId) { res.status(400).json({ error: 'sessionId required' }); return }

    // Run asynchronously with single persistent Claude bridge
    runPlaybook(playbook, inputs, sessionId, SESSIONS_DIR, findAutomation, REPO_ROOT, broadcast)
      .catch(err => console.error('Playbook execution failed:', err))

    res.json({ id: `exec-pending`, playbook_id: playbook.id, session_id: sessionId, status: 'running', started_at: new Date().toISOString() })
  })

  // ----- Playbook Executions -----

  router.get('/playbook-executions', (_req, res) => {
    res.json(getPlaybookExecutions())
  })

  router.get('/playbook-executions/:id', (req, res) => {
    const exec = getPlaybookExecution(sanitizeId(req.params.id))
    if (!exec) { res.status(404).json({ error: 'Not found' }); return }
    res.json(exec)
  })

  router.delete('/playbook-executions/:id', (req, res) => {
    const cancelled = cancelPlaybookExecution(sanitizeId(req.params.id))
    res.json({ cancelled })
  })

  return router
}
