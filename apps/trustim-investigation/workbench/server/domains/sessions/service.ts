import { safePath } from '../../middleware/sanitize.js'
import { loadIocDb, saveIocDb } from '../iocs/store.js'
import { deleteSessionFile, deleteNotebook } from './store.js'
import fs from 'fs'
import path from 'path'

export function getMaxSeverity(nodes: Record<string, { confidence?: number; tags?: string[] }>): string {
  let maxConf = 0
  let hasSev = ''
  for (const node of Object.values(nodes)) {
    if ((node.confidence || 0) > maxConf) maxConf = node.confidence || 0
    const sevTag = (node.tags || []).find(t => t.startsWith('SEV-'))
    if (sevTag && (!hasSev || sevTag < hasSev)) hasSev = sevTag // SEV-1 < SEV-2 (lower is worse)
  }
  if (hasSev) return hasSev
  if (maxConf > 0.7) return 'critical'
  if (maxConf > 0.5) return 'high'
  if (maxConf > 0.3) return 'medium'
  if (maxConf > 0.1) return 'low'
  return 'benign'
}

export interface SessionSummary {
  id: string
  name: string
  created_at: string
  updated_at: string
  node_count: number
  max_severity: string
  max_confidence: number
  completed_count: number
  has_sev: boolean
  skills_used: string[]
  starting_input_type: string
}

export function summarizeSession(data: any): SessionSummary | null {
  try {
    const nodes = Object.values(data.nodes || {}) as Array<{ confidence?: number; status?: string; tags?: string[] }>
    const maxConf = nodes.length > 0 ? Math.max(0, ...nodes.map(n => n.confidence || 0)) : 0
    const completedCount = nodes.filter(n => n.status === 'completed').length
    const hasSev = nodes.some(n => (n.tags || []).some(t => t.startsWith('SEV-')))
    return {
      id: data.id,
      name: data.name,
      created_at: data.created_at,
      updated_at: data.updated_at,
      node_count: nodes.length,
      max_severity: getMaxSeverity(data.nodes || {}),
      max_confidence: maxConf,
      completed_count: completedCount,
      has_sev: hasSev,
      skills_used: (data.skills_used || []).slice(0, 3),
      starting_input_type: data.starting_input_type,
    }
  } catch {
    return null
  }
}

export interface DeleteCascadeConfig {
  sessionsDir: string
  notebooksDir: string
  alertsDir: string
  iocDbPath: string
  sessionId: string
  stopBackgroundInvestigation: (id: string) => boolean
}

export function deleteSessionCascade(config: DeleteCascadeConfig): void {
  const { sessionsDir, notebooksDir, alertsDir, iocDbPath, sessionId, stopBackgroundInvestigation } = config

  deleteSessionFile(sessionsDir, sessionId)
  deleteNotebook(notebooksDir, sessionId)

  // Remove IOCs associated with this session
  try {
    const db = loadIocDb(iocDbPath)
    let changed = false
    for (const [key, entry] of Object.entries(db)) {
      entry.sessions = entry.sessions.filter((sid: string) => sid !== sessionId)
      if (entry.sessions.length === 0) { delete db[key]; changed = true }
      else changed = true
    }
    if (changed) saveIocDb(iocDbPath, db)
  } catch { /* ignore */ }

  // Unlink session from any alerts that reference it
  try {
    const alertFiles = fs.readdirSync(alertsDir).filter(f => f.endsWith('.json'))
    for (const f of alertFiles) {
      const alertPath = path.join(alertsDir, f)
      try {
        const alert = JSON.parse(fs.readFileSync(alertPath, 'utf-8'))
        if (alert.session_ids?.includes(sessionId)) {
          alert.session_ids = alert.session_ids.filter((sid: string) => sid !== sessionId)
          fs.writeFileSync(alertPath, JSON.stringify(alert, null, 2))
        }
      } catch { /* skip corrupt alert files */ }
    }
  } catch { /* ignore */ }

  stopBackgroundInvestigation(sessionId)

  // Re-delete session file after a delay (agent finalization may re-create it)
  setTimeout(() => {
    deleteSessionFile(sessionsDir, sessionId)
  }, 3000)
}
