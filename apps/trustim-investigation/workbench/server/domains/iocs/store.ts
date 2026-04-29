import fs from 'fs'

export interface IocEntry {
  value: string
  type: string
  sessions: string[]
  firstSeen: string
  lastSeen: string
}

export function loadIocDb(iocDbPath: string): Record<string, IocEntry> {
  try { return JSON.parse(fs.readFileSync(iocDbPath, 'utf-8')) }
  catch { return {} }
}

export function saveIocDb(iocDbPath: string, db: Record<string, IocEntry>): void {
  fs.writeFileSync(iocDbPath, JSON.stringify(db))
}
