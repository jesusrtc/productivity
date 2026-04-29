import { Router } from 'express'
import { sanitizeId } from '../../middleware/sanitize.js'
import { initAutomationsStore, getAllAutomations, findAutomation, saveAutomation, loadAutomation, deleteAutomation, type AutomationsStoreConfig } from './store.js'
import { runAutomation } from './service.js'

export interface AutomationsRouterConfig {
  AUTOMATIONS_DIR: string
  SKILLS_DIR: string
  REPO_ROOT: string
}

export default function createAutomationsRouter(config: AutomationsRouterConfig): Router {
  const storeConfig: AutomationsStoreConfig = { automationsDir: config.AUTOMATIONS_DIR, skillsDir: config.SKILLS_DIR }
  initAutomationsStore(storeConfig)
  const router = Router()

  // Legacy migration endpoint — now a no-op since automations are dynamic
  // MUST be before :id routes to avoid Express route shadowing
  router.post('/migrate', (_req, res) => {
    const all = getAllAutomations(storeConfig)
    res.json({ migrated: all.length, message: 'Automations are now loaded dynamically from skills', errors: [] })
  })

  router.get('/', (req, res) => {
    const { category, exec_type, search } = req.query as Record<string, string>
    const all = getAllAutomations(storeConfig)
    const filtered = all
      .filter(a => !category || a.category === category)
      .filter(a => !exec_type || a.exec_type === exec_type)
      .filter(a => !search || a.name.toLowerCase().includes(search.toLowerCase()) || a.description?.toLowerCase().includes(search.toLowerCase()))
      .map(a => ({
        id: a.id,
        name: a.name,
        description: a.description,
        category: a.category,
        exec_type: a.exec_type,
        input_count: (a.inputs || []).length,
        source_skill: a.source_skill,
        source: a.source,
      }))
    res.json(filtered)
  })

  router.get('/:id', (req, res) => {
    const auto = findAutomation(sanitizeId(req.params.id), storeConfig)
    if (!auto) { res.status(404).json({ error: 'Not found' }); return }
    res.json(auto)
  })

  router.post('/', (req, res) => {
    const id = `custom-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    const automation = { ...req.body, id, source: 'custom', created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
    try {
      saveAutomation(config.AUTOMATIONS_DIR, id, automation)
    } catch {
      res.status(400).json({ error: 'Invalid ID' }); return
    }
    res.json(automation)
  })

  router.put('/:id', (req, res) => {
    const id = sanitizeId(req.params.id)
    const existing = loadAutomation(config.AUTOMATIONS_DIR, id)
    if (!existing) { res.status(404).json({ error: 'Can only edit custom automations' }); return }
    const updated = { ...existing, ...req.body, id: existing.id, created_at: existing.created_at, updated_at: new Date().toISOString() }
    saveAutomation(config.AUTOMATIONS_DIR, id, updated)
    res.json(updated)
  })

  router.delete('/:id', (req, res) => {
    deleteAutomation(config.AUTOMATIONS_DIR, sanitizeId(req.params.id))
    res.json({ success: true })
  })

  router.post('/:id/run', async (req, res) => {
    const automation = findAutomation(sanitizeId(req.params.id), storeConfig)
    if (!automation) { res.status(404).json({ error: 'Not found' }); return }
    const result = await runAutomation(automation, req.body.inputs || {}, config.REPO_ROOT)
    res.json(result)
  })

  return router
}
