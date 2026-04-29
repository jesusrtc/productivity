import { safePath } from '../../middleware/sanitize.js'
import fs from 'fs'
import path from 'path'

export function loadAlert(alertsDir: string, id: string): any | null {
  const filePath = safePath(alertsDir, `${id}.json`)
  if (!filePath || !fs.existsSync(filePath)) return null
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'))
  } catch {
    return null
  }
}

export function loadAllAlerts(alertsDir: string): any[] {
  const files = fs.readdirSync(alertsDir).filter(f => f.endsWith('.json'))
  const alerts: any[] = []
  for (const f of files) {
    try {
      alerts.push(JSON.parse(fs.readFileSync(path.join(alertsDir, f), 'utf-8')))
    } catch { /* skip corrupted files */ }
  }
  return alerts
}

export function saveAlert(alertsDir: string, id: string, data: any): void {
  const filePath = safePath(alertsDir, `${id}.json`)
  if (!filePath) throw new Error('Invalid ID')
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2))
}

export function deleteAlert(alertsDir: string, id: string): void {
  const filePath = safePath(alertsDir, `${id}.json`)
  if (filePath && fs.existsSync(filePath)) fs.unlinkSync(filePath)
}
