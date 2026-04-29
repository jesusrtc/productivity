/**
 * IRIS Alert Sync — Pulls alerts from IRIS API for the trust-incident-auto-alert plan.
 *
 * Uses the IRIS REST API directly (no CLI dependency, no auth needed on corp network).
 * Runs periodically, deduplicates by IRIS incident ID, and upserts into local alerts dir.
 */

import fs from 'fs'
import path from 'path'
import http from 'http'
import https from 'https'

export interface SyncConfig {
  enabled: boolean
  intervalMs: number
  alertsDir: string
  /** How many days back to fetch when syncing alerts */
  lookbackDays: number
  /** How many alerts to fetch per sync */
  limit: number
  /** IRIS plan names to pull from */
  plans: string[]
}

const DEFAULT_CONFIG: SyncConfig = {
  enabled: false,
  intervalMs: 5 * 60 * 1000,
  alertsDir: '',
  lookbackDays: 7,
  limit: 50,
  plans: ['trust-incident-auto-alert', 'trust-incident-intake-email', 'trust-incident-intake', 'abuse-incidents-thirdeye'],
}

let syncTimer: ReturnType<typeof setInterval> | null = null
let config: SyncConfig = { ...DEFAULT_CONFIG }
let lastSyncTime: string | null = null
let syncInProgress = false

export function initSync(alertsDir: string): void {
  config.alertsDir = alertsDir
  fs.mkdirSync(alertsDir, { recursive: true })
}

export function startSync(overrides?: Partial<SyncConfig>): void {
  if (overrides) config = { ...config, ...overrides }
  config.enabled = true
  stopSync()
  syncTimer = setInterval(() => runSync(), config.intervalMs)
  runSync()
}

export function stopSync(): void {
  if (syncTimer) { clearInterval(syncTimer); syncTimer = null }
}

export function getSyncStatus() {
  return {
    enabled: config.enabled,
    intervalMs: config.intervalMs,
    lookbackDays: config.lookbackDays,
    lastSync: lastSyncTime,
    syncing: syncInProgress,
    plans: config.plans,
  }
}

export async function runSync(lookbackDays?: number): Promise<{ added: number; updated: number; total: number; errors: string[] }> {
  if (syncInProgress || !config.alertsDir) {
    return { added: 0, updated: 0, total: 0, errors: ['Sync in progress or not configured'] }
  }

  syncInProgress = true
  const result = { added: 0, updated: 0, total: 0, errors: [] as string[] }

  try {
    // Fetch from all configured plans in parallel
    const allResults = await Promise.all(
      config.plans.map(plan => fetchIrisAlerts(plan, config.limit))
    )
    // Merge and deduplicate by IRIS incident ID
    const seen = new Set<string>()
    const irisAlerts: Record<string, unknown>[] = []
    for (const batch of allResults) {
      for (const alert of batch) {
        const key = String(alert.id)
        if (!seen.has(key)) {
          seen.add(key)
          irisAlerts.push(alert)
        }
      }
    }
    result.total = irisAlerts.length

    // Filter by lookback days if specified
    const effectiveLookbackDays = lookbackDays ?? config.lookbackDays
    const cutoff = effectiveLookbackDays
      ? Date.now() - effectiveLookbackDays * 24 * 60 * 60 * 1000
      : 0
    const filtered = cutoff > 0
      ? irisAlerts.filter(a => (a.created as number) * 1000 >= cutoff)
      : irisAlerts

    for (const irisAlert of filtered) {
      try {
        const alert = mapIrisAlert(irisAlert)
        const filePath = path.join(config.alertsDir, `${alert.id}.json`)

        if (fs.existsSync(filePath)) {
          const existing = JSON.parse(fs.readFileSync(filePath, 'utf-8'))
          const merged = {
            ...existing,
            title: alert.title,
            description: alert.description,
            severity: alert.severity,
            alert_type: alert.alert_type,
            metadata: { ...asRecord(existing.metadata), ...asRecord(alert.metadata) },
            updated_at: new Date().toISOString(),
          }
          fs.writeFileSync(filePath, JSON.stringify(merged, null, 2))
          result.updated++
        } else {
          fs.writeFileSync(filePath, JSON.stringify(alert, null, 2))
          result.added++
        }
      } catch (e) {
        result.errors.push(`Failed to process alert ${irisAlert.id}: ${e}`)
      }
    }

    lastSyncTime = new Date().toISOString()
  } catch (e) {
    result.errors.push(`Sync failed: ${e}`)
  } finally {
    syncInProgress = false
  }

  return result
}

/** Fetch alerts from IRIS REST API */
async function fetchIrisAlerts(plan: string, limit: number): Promise<Record<string, unknown>[]> {
  const url = `https://iris.prod.linkedin.com/v0/incidents?plan=${encodeURIComponent(plan)}&limit=${encodeURIComponent(String(limit))}`

  return new Promise((resolve) => {
    const req = https.get(url, { timeout: 30000 }, (res) => {
      let data = ''
      res.on('data', (chunk: Buffer) => { data += chunk.toString() })
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data)
          resolve(Array.isArray(parsed) ? parsed : [])
        } catch {
          console.error('IRIS sync: failed to parse response')
          resolve([])
        }
      })
    })
    req.on('error', (e) => {
      console.error('IRIS sync: request failed:', e.message)
      resolve([])
    })
    req.on('timeout', () => {
      req.destroy()
      resolve([])
    })
  })
}

/** Map IRIS incident to local alert format */
function mapIrisAlert(iris: Record<string, unknown>): Record<string, unknown> {
  const ctx = (iris.context || {}) as Record<string, unknown>
  const id = `iris-${iris.id}`
  const title = String(ctx.title || iris.title || 'Untitled Alert')
  const alertMetadata = ctx.alert_metadata ? tryParseJson(String(ctx.alert_metadata)) : {}
  // Build rich description from all available context fields
  const descParts = [
    String(ctx.description || ctx.summary || ''),
    // Include alert_metadata fields inline (e.g., total registrations, captcha count, detection method)
    ...Object.entries(alertMetadata).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`),
  ].filter(Boolean)
  const description = descParts.join('\n')
  const severity = mapSeverity(String(ctx.severity || 'minor'))
  const alertType = String(ctx.source || ctx.areas_of_impact || '')
  const reporter = String(ctx.reporter || '')
  const entityImpact = String(ctx.entity_impact || '')
  const playbook = String(ctx.playbook || '')
  const alertUrl = String(ctx.alert_url || '')

  // Extract IOCs from description, summary, and alert_metadata
  const textForIocs = [description, String(ctx.summary || ''), JSON.stringify(alertMetadata)].join(' ')
  const iocs = extractIOCs(textForIocs)

  return {
    id,
    external_id: String(iris.id),
    title,
    description,
    status: iris.active ? 'investigating' : iris.resolved ? 'resolved' : 'new',
    severity,
    source: 'iris',
    alert_type: alertType,
    assignee: String(iris.owner || reporter),
    created_at: iris.created ? new Date((iris.created as number) * 1000).toISOString() : new Date().toISOString(),
    updated_at: new Date().toISOString(),
    session_ids: [],
    related_alert_ids: [],
    iocs,
    incident_id: String(iris.id),
    metadata: {
      iris_id: iris.id,
      iris_plan: iris.plan,
      iris_plan_id: iris.plan_id,
      reporter,
      entity_impact: entityImpact,
      playbook,
      alert_url: alertUrl,
      alert_metadata: alertMetadata,
      alert_date: ctx.alert_date,
      context: ctx,
    },
    tags: [
      ...(entityImpact ? [entityImpact.toLowerCase()] : []),
      ...(alertType ? [alertType.toLowerCase()] : []),
    ].filter(Boolean),
  }
}

function mapSeverity(s: string): string {
  const lower = s.toLowerCase()
  if (lower === 'critical' || lower.includes('sev-1') || lower.includes('sev1')) return 'critical'
  if (lower === 'major' || lower.includes('sev-2') || lower.includes('sev2')) return 'high'
  if (lower === 'minor' || lower.includes('sev-3') || lower.includes('sev3')) return 'medium'
  if (lower === 'trivial' || lower.includes('sev-4') || lower.includes('sev4')) return 'low'
  return 'medium'
}

function extractIOCs(text: string): { type: string; value: string }[] {
  const iocs: { type: string; value: string }[] = []
  const seen = new Set<string>()

  const ips = text.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || []
  for (const ip of ips) {
    if (!seen.has(`ip:${ip}`)) { iocs.push({ type: 'ip', value: ip }); seen.add(`ip:${ip}`) }
  }

  const mids = text.match(/\b(\d{7,12})\b/g) || []
  for (const mid of mids) {
    if (!mid.startsWith('202') && !seen.has(`member_id:${mid}`)) {
      iocs.push({ type: 'member_id', value: mid }); seen.add(`member_id:${mid}`)
    }
  }

  const domains = text.match(/\b[a-z0-9][-a-z0-9]*\.[a-z]{2,10}\b/gi) || []
  for (const domain of domains) {
    if (!domain.match(/^\d/) && !(/^(.+\.)?linkedin\.com$/i.test(domain)) && !seen.has(`domain:${domain}`)) {
      iocs.push({ type: 'domain', value: domain }); seen.add(`domain:${domain}`)
    }
  }

  return iocs.slice(0, 50)
}

function tryParseJson(s: string): Record<string, unknown> {
  try { return JSON.parse(s) } catch { return {} }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}
