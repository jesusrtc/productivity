import express from 'express'
import http from 'http'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'
import rateLimit from 'express-rate-limit'
import { getCaptainClient } from './bridge/captain-client.js'
import { initSync, startSync, stopSync, runSync, getSyncStatus } from './inresponse-sync.js'
import { initBackgroundAgents, stopBackgroundInvestigation } from './background-agents.js'
import { createWsHandler } from './ws/handler.js'
import createSessionsRouter, { cleanupSessions } from './domains/sessions/router.js'
import createAlertsRouter from './domains/alerts/router.js'
import createAutomationsRouter from './domains/automations/router.js'
import createPlaybooksRouter from './domains/playbooks/router.js'
import createSkillsRouter, { watchSkills } from './domains/skills/router.js'
import { discoverSkills } from './domains/skills/store.js'
import createSetupRouter from './domains/setup/router.js'
import createInvestigationsRouter from './domains/investigations/router.js'
import createNotebooksRouter from './domains/notebooks/router.js'
import createIocsRouter from './domains/iocs/router.js'
import createMiscRouter from './domains/misc/router.js'

// ----- Directory constants -----
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SESSIONS_DIR = path.resolve(__dirname, '..', '.sessions')
const SKILLS_DIR = path.resolve(__dirname, '..', '..', 'skills')
const REPO_ROOT = path.resolve(__dirname, '..', '..')
const ALERTS_DIR = path.resolve(__dirname, '..', '.alerts')
const AUTOMATIONS_DIR = path.resolve(__dirname, '..', '.automations')
const PLAYBOOKS_DIR = path.resolve(__dirname, '..', '.playbooks')
const NOTEBOOKS_DIR = path.resolve(REPO_ROOT, 'notebooks')
const IOC_DB_PATH = path.resolve(SESSIONS_DIR, '..', '.ioc-db.json')
const PORT = Number(process.env.PORT || 3100)

for (const dir of [SESSIONS_DIR, ALERTS_DIR, PLAYBOOKS_DIR, AUTOMATIONS_DIR]) {
  fs.mkdirSync(dir, { recursive: true })
}

// ----- Express app -----
const app = express()
app.use(express.json({ limit: '50mb' }))
app.use('/api', rateLimit({ windowMs: 60_000, max: 600, standardHeaders: true, legacyHeaders: false }))

// ----- HTTP + WebSocket -----
const server = http.createServer(app)
const wsHandler = createWsHandler(server, { SESSIONS_DIR, REPO_ROOT })
const { broadcast } = wsHandler

// ----- Trino query proxy (bypasses MCP timing issues) -----
app.post('/api/trino/query', async (req, res) => {
  const { query, server: trinoServer, headless_account } = req.body as {
    query?: string; server?: string; headless_account?: string
  }
  if (!query) { res.status(400).json({ error: 'Missing query' }); return }
  const account = headless_account || 'trustim'
  const preamble = `SET SESSION li_authorization_user = '${account}'`
  try {
    const captain = getCaptainClient()
    const raw = await captain.callTool('execute_trino_query', {
      query,
      server: trinoServer || 'holdem',
      preamble_sql: preamble,
    })
    res.json({ success: true, result: raw })
  } catch (err) {
    res.status(500).json({ success: false, error: String(err).slice(0, 1000) })
  }
})

// ----- Google Docs proxy (bypasses MCP timing issues in bridge subprocess) -----
app.post('/api/docs/create', async (req, res) => {
  const { title } = req.body as { title?: string }
  if (!title) { res.status(400).json({ error: 'Missing title' }); return }
  try {
    const captain = getCaptainClient()
    const raw = await captain.callTool('create_google_docs_document', { title })
    res.json({ success: true, result: raw })
  } catch (err) {
    res.status(500).json({ success: false, error: String(err).slice(0, 1000) })
  }
})

app.post('/api/docs/write', async (req, res) => {
  const { document_id, elements, clear_before_write } = req.body as {
    document_id?: string; elements?: unknown[]; clear_before_write?: boolean
  }
  if (!document_id || !elements) { res.status(400).json({ error: 'Missing document_id or elements' }); return }
  try {
    const captain = getCaptainClient()
    const raw = await captain.callTool('write_to_google_docs_document', {
      document_id, elements, ...(clear_before_write ? { clear_before_write } : {}),
    })
    res.json({ success: true, result: raw })
  } catch (err) {
    res.status(500).json({ success: false, error: String(err).slice(0, 1000) })
  }
})

app.post('/api/docs/read', async (req, res) => {
  const { document_id } = req.body as { document_id?: string }
  if (!document_id) { res.status(400).json({ error: 'Missing document_id' }); return }
  try {
    const captain = getCaptainClient()
    const raw = await captain.callTool('read_google_docs_document', { document_id })
    res.json({ success: true, result: raw })
  } catch (err) {
    res.status(500).json({ success: false, error: String(err).slice(0, 1000) })
  }
})

// ----- Mount domain routers -----
app.use('/api/investigations', createInvestigationsRouter())
app.use('/api/notebook', createNotebooksRouter({ NOTEBOOKS_DIR }))
app.use('/api/iocs', createIocsRouter({ IOC_DB_PATH }))
app.use('/api/sessions', createSessionsRouter({ SESSIONS_DIR, NOTEBOOKS_DIR, ALERTS_DIR, IOC_DB_PATH, stopBackgroundInvestigation }))
app.use('/api/alerts', createAlertsRouter({ ALERTS_DIR, initSync, startSync, stopSync, runSync, getSyncStatus }))
app.use('/api/automations', createAutomationsRouter({ AUTOMATIONS_DIR, SKILLS_DIR, REPO_ROOT }))
app.use('/api', createPlaybooksRouter({ PLAYBOOKS_DIR, SESSIONS_DIR, REPO_ROOT, broadcast }))
app.use('/api/skills', createSkillsRouter({ SKILLS_DIR }))
app.use('/api', createSetupRouter({
  SESSIONS_DIR, SKILLS_DIR, REPO_ROOT, discoverSkills,
  getBridgeMaxTurns: () => wsHandler.getBridgeMaxTurns(),
  setBridgeMaxTurns: (n: number) => wsHandler.setBridgeMaxTurns(n),
  getSocketBridges: () => wsHandler.getSocketBridges(),
}))
app.use('/api', createMiscRouter({ SESSIONS_DIR, ALERTS_DIR, PLAYBOOKS_DIR }))

// ----- Startup -----
initBackgroundAgents(SESSIONS_DIR, REPO_ROOT, broadcast)
cleanupSessions(SESSIONS_DIR)

process.on('uncaughtException', (err) => console.error('Uncaught exception:', err.message))
process.on('unhandledRejection', (reason) => console.error('Unhandled rejection:', reason))
for (const signal of ['SIGINT', 'SIGTERM', 'exit'] as const) {
  process.on(signal, () => {
    for (const b of wsHandler.getSocketBridges().values()) b.abort()
    getCaptainClient().close()
  })
}

server.listen(PORT, () => {
  console.log(`Juniper server running on http://localhost:${PORT}`)
  console.log(`WebSocket available at ws://localhost:${PORT}/ws`)
  console.log(`Sessions stored in: ${SESSIONS_DIR}`)
  console.log(`Skills directory: ${SKILLS_DIR}`)
  watchSkills(SKILLS_DIR, broadcast)
})
