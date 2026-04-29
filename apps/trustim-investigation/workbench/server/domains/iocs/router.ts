import { Router } from 'express'
import { loadIocDb, saveIocDb } from './store.js'
export type { IocEntry } from './store.js'

interface IocsRouterConfig {
  IOC_DB_PATH: string
}

export default function createIocsRouter(config: IocsRouterConfig): Router {
  const router = Router()
  const { IOC_DB_PATH } = config

  router.get('/', (_req, res) => {
    const db = loadIocDb(IOC_DB_PATH)
    const entries = Object.values(db).sort((a, b) => b.sessions.length - a.sessions.length)
    res.json({ count: entries.length, iocs: entries.slice(0, 200) })
  })

  router.post('/', (req, res) => {
    const { iocs, sessionId } = req.body as { iocs: { value: string; type: string }[]; sessionId: string }
    if (!iocs || !sessionId) { res.status(400).json({ error: 'iocs and sessionId required' }); return }
    const db = loadIocDb(IOC_DB_PATH)
    const now = new Date().toISOString()
    let added = 0
    for (const ioc of iocs.slice(0, 500)) {
      const key = `${ioc.type}:${ioc.value}`
      if (db[key]) {
        if (!db[key].sessions.includes(sessionId)) {
          db[key].sessions.push(sessionId)
          db[key].lastSeen = now
        }
      } else {
        db[key] = { value: ioc.value, type: ioc.type, sessions: [sessionId], firstSeen: now, lastSeen: now }
        added++
      }
    }
    saveIocDb(IOC_DB_PATH, db)
    res.json({ success: true, added, total: Object.keys(db).length })
  })

  router.get('/check', (req, res) => {
    const value = req.query.value as string
    if (!value) { res.json({ found: false }); return }
    const db = loadIocDb(IOC_DB_PATH)
    const matches = Object.values(db).filter(e => e.value === value)
    res.json({ found: matches.length > 0, matches })
  })

  return router
}
