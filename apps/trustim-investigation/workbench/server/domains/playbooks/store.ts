import { safePath } from '../../middleware/sanitize.js'
import fs from 'fs'
import path from 'path'

export function loadPlaybook(dir: string, id: string): any | null {
  const filePath = safePath(dir, `${id}.json`)
  if (!filePath || !fs.existsSync(filePath)) return null
  try { return JSON.parse(fs.readFileSync(filePath, 'utf-8')) }
  catch { return null }
}

export function loadPlaybooks(dir: string): any[] {
  try {
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'))
    return files.map(f => {
      try { return JSON.parse(fs.readFileSync(path.join(dir, f), 'utf-8')) } catch { return null }
    }).filter(Boolean)
  } catch { return [] }
}

export function savePlaybook(dir: string, id: string, data: any): string | null {
  const filePath = safePath(dir, `${id}.json`)
  if (!filePath) return null
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2))
  return filePath
}

export function deletePlaybook(dir: string, id: string): void {
  const filePath = safePath(dir, `${id}.json`)
  if (filePath && fs.existsSync(filePath)) fs.unlinkSync(filePath)
}

export function playbookExists(dir: string, id: string): boolean {
  const filePath = safePath(dir, `${id}.json`)
  return !!filePath && fs.existsSync(filePath)
}
