import { safePath } from '../../middleware/sanitize.js'
import fs from 'fs'
import path from 'path'

export function loadSession(sessionsDir: string, id: string): any | null {
  const filePath = safePath(sessionsDir, `${id}.json`)
  if (!filePath || !fs.existsSync(filePath)) return null
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'))
  } catch {
    return null
  }
}

export function loadAllSessionFiles(sessionsDir: string): Array<{ filename: string; data: any }> {
  const files = fs.readdirSync(sessionsDir).filter(f => f.endsWith('.json'))
  const results: Array<{ filename: string; data: any }> = []
  for (const f of files) {
    try {
      const data = JSON.parse(fs.readFileSync(path.join(sessionsDir, f), 'utf-8'))
      results.push({ filename: f, data })
    } catch { /* skip corrupt files */ }
  }
  return results
}

export function saveSession(sessionsDir: string, id: string, data: any): Promise<void> {
  const filePath = safePath(sessionsDir, `${id}.json`)
  if (!filePath) return Promise.reject(new Error('Invalid path'))
  return new Promise((resolve, reject) => {
    fs.writeFile(filePath, JSON.stringify(data), (err) => {
      if (err) reject(err)
      else resolve()
    })
  })
}

export function deleteSessionFile(sessionsDir: string, id: string): void {
  const filePath = safePath(sessionsDir, `${id}.json`)
  if (filePath && fs.existsSync(filePath)) fs.unlinkSync(filePath)
}

export function deleteNotebook(notebooksDir: string, sessionId: string): void {
  const sanitized = sessionId.replace(/[^a-zA-Z0-9_-]/g, '')
  const nbPath = safePath(notebooksDir, `investigation-${sanitized.slice(0, 8)}.ipynb`)
  if (nbPath && fs.existsSync(nbPath)) fs.unlinkSync(nbPath)
}

export function sessionFileExists(sessionsDir: string, id: string): boolean {
  const filePath = safePath(sessionsDir, `${id}.json`)
  return !!filePath && fs.existsSync(filePath)
}

export function listSessionFilenames(sessionsDir: string): string[] {
  try { return fs.readdirSync(sessionsDir).filter(f => f.endsWith('.json')) }
  catch { return [] }
}

export function getSessionFileMtime(sessionsDir: string, filename: string): number {
  return fs.statSync(path.join(sessionsDir, filename)).mtimeMs
}

export function deleteSessionByFilename(sessionsDir: string, filename: string): void {
  try { fs.unlinkSync(path.join(sessionsDir, filename)) } catch { /* ignore */ }
}

export function readSessionByFilename(sessionsDir: string, filename: string): any | null {
  try { return JSON.parse(fs.readFileSync(path.join(sessionsDir, filename), 'utf-8')) }
  catch { return null }
}
