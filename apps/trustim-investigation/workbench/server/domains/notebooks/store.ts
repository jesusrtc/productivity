import { sanitizeId, safePath } from '../../middleware/sanitize.js'
import fs from 'fs'

export interface NotebookData {
  nbformat: number
  nbformat_minor: number
  metadata: Record<string, unknown>
  cells: unknown[]
}

export function notebookPath(dir: string, sessionId: string): string | null {
  const nbName = `investigation-${sanitizeId(sessionId).slice(0, 8)}`
  return safePath(dir, `${nbName}.ipynb`)
}

export function loadNotebook(dir: string, sessionId: string): NotebookData | null {
  const nbPath = notebookPath(dir, sessionId)
  if (!nbPath || !fs.existsSync(nbPath)) return null
  try { return JSON.parse(fs.readFileSync(nbPath, 'utf-8')) }
  catch { return null }
}

export function saveNotebook(dir: string, sessionId: string, data: NotebookData): string | null {
  fs.mkdirSync(dir, { recursive: true })
  const nbPath = notebookPath(dir, sessionId)
  if (!nbPath) return null
  fs.writeFileSync(nbPath, JSON.stringify(data, null, 2))
  return nbPath
}

export function initNotebook(sessionId: string, sessionName?: string): NotebookData {
  return {
    nbformat: 4,
    nbformat_minor: 5,
    metadata: {
      kernelspec: { display_name: 'Juniper', language: 'sql', name: 'workbench' },
      investigation_id: sessionId,
      investigation_name: sessionName || 'Investigation',
    },
    cells: [{
      cell_type: 'markdown',
      metadata: {},
      source: [`# ${sessionName || 'Investigation'}\n`, `\nAuto-generated audit trail via Juniper.\n`],
    }],
  }
}
