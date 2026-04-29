import { Router } from 'express'
import { sanitizeId, safePath } from '../../middleware/sanitize.js'
import { loadSession, loadAllSessionFiles, saveSession, sessionFileExists, listSessionFilenames, getSessionFileMtime, deleteSessionByFilename, readSessionByFilename } from './store.js'
import { summarizeSession, deleteSessionCascade } from './service.js'

interface SessionsRouterConfig {
  SESSIONS_DIR: string
  NOTEBOOKS_DIR: string
  ALERTS_DIR: string
  IOC_DB_PATH: string
  stopBackgroundInvestigation: (sessionId: string) => boolean
}

export default function createSessionsRouter(config: SessionsRouterConfig): Router {
  const router = Router()
  const { SESSIONS_DIR, NOTEBOOKS_DIR, ALERTS_DIR, IOC_DB_PATH, stopBackgroundInvestigation } = config

  router.get('/', (_req, res) => {
    const sessions = loadAllSessionFiles(SESSIONS_DIR)
    const summaries = sessions
      .map(({ data }) => summarizeSession(data))
      .filter(Boolean)
    res.json(summaries)
  })

  router.get('/:id', (req, res) => {
    const id = sanitizeId(req.params.id)
    const data = loadSession(SESSIONS_DIR, id)
    if (!data) {
      const exists = sessionFileExists(SESSIONS_DIR, id)
      res.status(exists ? 500 : 404).json({
        error: exists ? 'Corrupted session file' : 'Session not found'
      })
      return
    }
    res.json(data)
  })

  router.put('/:id', async (req, res) => {
    const id = sanitizeId(req.params.id)
    const filePath = safePath(SESSIONS_DIR, `${id}.json`)
    if (!filePath) { res.status(400).json({ error: 'Invalid ID' }); return }
    const data = { ...req.body, updated_at: new Date().toISOString() }
    try {
      await saveSession(SESSIONS_DIR, id, data)
      res.json({ success: true })
    } catch {
      res.status(500).json({ error: 'Failed to save session' })
    }
  })

  router.delete('/:id', (req, res) => {
    const sessionId = sanitizeId(req.params.id)
    deleteSessionCascade({
      sessionsDir: SESSIONS_DIR,
      notebooksDir: NOTEBOOKS_DIR,
      alertsDir: ALERTS_DIR,
      iocDbPath: IOC_DB_PATH,
      sessionId,
      stopBackgroundInvestigation,
    })
    res.json({ success: true })
  })

  return router
}

/** Clean up old/empty sessions on startup */
export function cleanupSessions(sessionsDir: string) {
  try {
    const files = listSessionFilenames(sessionsDir)
    const now = Date.now()
    const DAY_MS = 24 * 60 * 60 * 1000
    const MAX_SESSIONS = 100
    let deleted = 0

    for (const f of files) {
      try {
        const mtime = getSessionFileMtime(sessionsDir, f)
        if (now - mtime > DAY_MS) {
          const data = readSessionByFilename(sessionsDir, f)
          if (data && Object.keys(data.nodes || {}).length === 0) {
            deleteSessionByFilename(sessionsDir, f)
            deleted++
          }
        }
      } catch { /* skip corrupt files */ }
    }

    const remaining = listSessionFilenames(sessionsDir)
    if (remaining.length > MAX_SESSIONS) {
      const sorted = remaining
        .map(f => ({ name: f, mtime: getSessionFileMtime(sessionsDir, f) }))
        .sort((a, b) => a.mtime - b.mtime)
      for (const f of sorted.slice(0, remaining.length - MAX_SESSIONS)) {
        deleteSessionByFilename(sessionsDir, f.name)
        deleted++
      }
    }

    if (deleted > 0) console.log(`Session cleanup: deleted ${deleted} old/empty sessions`)
  } catch { /* ignore cleanup errors */ }
}
