import { Router } from 'express'
import { sanitizeId } from '../../middleware/sanitize.js'
import { getActiveInvestigations, startBackgroundInvestigation, stopBackgroundInvestigation, getInvestigation, resumeBackgroundInvestigation } from '../../background-agents.js'

interface InvestigationsRouterConfig {
  // no config needed — investigations only use background-agents imports
}

export default function createInvestigationsRouter(_config?: InvestigationsRouterConfig): Router {
  const router = Router()

  router.get('/', (_req, res) => {
    res.json(getActiveInvestigations())
  })

  router.post('/:sessionId/resume', (req, res) => {
    const resumed = resumeBackgroundInvestigation(sanitizeId(req.params.sessionId))
    res.json({ resumed })
  })

  router.get('/:sessionId', (req, res) => {
    const inv = getInvestigation(sanitizeId(req.params.sessionId))
    if (!inv) { res.status(404).json({ error: 'Not found' }); return }
    res.json(inv)
  })

  router.post('/start', (req, res) => {
    const { sessionId, prompt, alertId, sessionName } = req.body || {}
    if (!sessionId || !prompt) {
      res.status(400).json({ error: 'sessionId and prompt required' })
      return
    }
    const inv = startBackgroundInvestigation(sanitizeId(sessionId), prompt, alertId, sessionName)
    res.json(inv)
  })

  router.delete('/:sessionId', (req, res) => {
    const stopped = stopBackgroundInvestigation(sanitizeId(req.params.sessionId))
    res.json({ stopped })
  })

  return router
}
