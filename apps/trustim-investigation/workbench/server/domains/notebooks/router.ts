import { Router } from 'express'
import { sanitizeId } from '../../middleware/sanitize.js'
import { loadNotebook, saveNotebook, initNotebook, notebookPath } from './store.js'
import fs from 'fs'
import path from 'path'

interface NotebooksRouterConfig {
  NOTEBOOKS_DIR: string
}

export default function createNotebooksRouter(config: NotebooksRouterConfig): Router {
  const router = Router()
  const { NOTEBOOKS_DIR } = config

  router.post('/append', (req, res) => {
    const { sessionId, sessionName, nodeId, label, query, resultRaw, severity, timestamp } = req.body
    if (!sessionId || !query) {
      res.status(400).json({ error: 'sessionId and query required' })
      return
    }

    let nb = loadNotebook(NOTEBOOKS_DIR, sessionId)
    if (!nb) {
      nb = initNotebook(sessionId, sessionName)
    }

    // Add markdown header for the node with rich metadata
    const nodeTs = timestamp || new Date().toISOString()
    nb.cells.push({
      cell_type: 'markdown',
      metadata: { node_id: nodeId },
      source: [
        `## ${label || 'Query'}\n`,
        `\n`,
        `**Severity:** ${severity || 'benign'} | **Time:** ${nodeTs}\n`,
        ...(req.body.confidence ? [`**Confidence:** ${(req.body.confidence * 100).toFixed(0)}%\n`] : []),
        ...(req.body.reasoning ? [`**Reasoning:** ${req.body.reasoning}\n`] : []),
        ...(req.body.tags?.length ? [`**Tags:** ${req.body.tags.join(', ')}\n`] : []),
      ],
    })

    // Add code cell with the query
    nb.cells.push({
      cell_type: 'code',
      metadata: { node_id: nodeId, timestamp: nodeTs, severity: severity || 'benign' },
      source: [query],
      outputs: resultRaw ? [{ output_type: 'stream', name: 'stdout', text: [resultRaw.slice(0, 50000)] }] : [],
      execution_count: (nb.cells as Array<{ cell_type?: string }>).filter((c) => c.cell_type === 'code').length + 1,
    })

    const nbPath = saveNotebook(NOTEBOOKS_DIR, sessionId, nb)
    if (!nbPath) { res.status(400).json({ error: 'Invalid session ID' }); return }
    const nbName = `investigation-${sanitizeId(sessionId).slice(0, 8)}`
    res.json({ success: true, path: nbPath, notebook: nbName })
  })

  router.get('/:sessionId', (req, res) => {
    const nbPath = notebookPath(NOTEBOOKS_DIR, req.params.sessionId)
    if (!nbPath) { res.status(400).json({ error: 'Invalid path' }); return }
    if (!fs.existsSync(nbPath)) {
      res.status(404).json({ error: 'Notebook not found' })
      return
    }
    const absPath = path.resolve(nbPath)
    if (!absPath.startsWith(path.resolve(NOTEBOOKS_DIR))) {
      res.status(400).json({ error: 'Invalid path' })
      return
    }
    const nbName = `investigation-${sanitizeId(req.params.sessionId).slice(0, 8)}`
    res.setHeader('Content-Type', 'application/x-ipynb+json')
    res.setHeader('Content-Disposition', `attachment; filename="${nbName}.ipynb"`)
    res.sendFile(absPath)
  })

  return router
}
