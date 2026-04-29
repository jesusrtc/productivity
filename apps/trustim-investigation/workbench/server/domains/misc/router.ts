import { Router } from 'express'
import { sanitizeId, safePath } from '../../middleware/sanitize.js'
import fs from 'fs'
import path from 'path'

interface MiscRouterConfig {
  SESSIONS_DIR: string
  ALERTS_DIR: string
  PLAYBOOKS_DIR: string
}

export default function createMiscRouter(config: MiscRouterConfig): Router {
  const router = Router()
  const { SESSIONS_DIR, ALERTS_DIR, PLAYBOOKS_DIR } = config
  const TEMPLATES_DIR = path.resolve(SESSIONS_DIR, '..', '.templates')

  // ----- Demo Seed API -----

  router.post('/seed-demo', (_req, res) => {
    const now = new Date().toISOString()
    const yesterday = new Date(Date.now() - 86400000).toISOString()
    const twoDaysAgo = new Date(Date.now() - 2 * 86400000).toISOString()
    let seeded = { alerts: 0, playbooks: 0 }

    // Seed demo alerts (only if none exist)
    const existingAlerts = fs.readdirSync(ALERTS_DIR).filter(f => f.endsWith('.json'))
    if (existingAlerts.length === 0) {
      const demoAlerts = [
        {
          id: 'demo-alert-1', title: 'Registration spike from disposable .xyz domains', description: 'Cold registration volume increased 340% from .xyz and .icu TLDs in the last 24h. Top domain: ghksc.xyz with 527 registrations. Possible automated account creation campaign.',
          status: 'new', severity: 'high', source: 'iris', alert_type: 'registration_spike',
          created_at: yesterday, updated_at: yesterday, session_ids: [], related_alert_ids: ['demo-alert-2'], tags: ['auto-detected', 'fake-accounts'],
          iocs: [{ type: 'domain', value: 'ghksc.xyz' }, { type: 'domain', value: 'mailnesia.com' }, { type: 'ip', value: '185.220.101.34' }, { type: 'ip', value: '45.134.225.17' }],
          metadata: { iris_plan: 'trust-incident-auto-alert', wow_pct: 34.2 },
        },
        {
          id: 'demo-alert-2', title: 'SwiftShader device fingerprint clustering', description: 'Anomalous canvas hash clustering detected. 89 accounts sharing identical SwiftShader WebGL renderer with matching canvas hashes. RTT >200ms suggests proxy usage.',
          status: 'new', severity: 'medium', source: 'iris', alert_type: 'fake_account',
          created_at: yesterday, updated_at: yesterday, session_ids: [], related_alert_ids: ['demo-alert-1'], tags: ['device-fingerprint'],
          iocs: [{ type: 'device_hash', value: 'canvas:a3f8b2c1d4' }, { type: 'ip', value: '185.220.101.34' }],
          metadata: { members_affected: 89 },
        },
        {
          id: 'demo-alert-3', title: 'ATO credential washing via MITM proxy', description: 'MITM phishing rule (Evilginx) activations spiked 5x in the last 6 hours. 23 unique member IDs with password_result=PASS and MITM rule hit.',
          status: 'investigating', severity: 'critical', source: 'iris', alert_type: 'ato',
          created_at: twoDaysAgo, updated_at: yesterday, session_ids: [], related_alert_ids: [], tags: ['ato', 'phishing', 'evilginx'],
          iocs: [{ type: 'ip', value: '91.215.85.12' }, { type: 'ip', value: '91.215.85.13' }, { type: 'member_id', value: '123456789' }],
          metadata: { activated_rules: ['IMIR: MITM ATO', 'Incident Response: ColorFish ATO'], member_count: 23 },
        },
        {
          id: 'demo-alert-4', title: 'Guest scraping volume increase — block filter bypass', description: 'Denial event volume from block filter rules increased 22% WoW. New user agent patterns detected bypassing existing rules.',
          status: 'new', severity: 'medium', source: 'iris', alert_type: 'guest_scraping',
          created_at: now, updated_at: now, session_ids: [], related_alert_ids: [], tags: ['scraping'],
          iocs: [{ type: 'user_agent', value: 'Mozilla/5.0 (compatible; DataBot/2.0)' }],
          metadata: { denial_count_today: 145000, wow_pct: 22.1 },
        },
        {
          id: 'demo-alert-5', title: 'Challenge abuse — VoIP solve rate anomaly', description: 'Phone challenge solve rate from VoIP numbers jumped to 98.7% (baseline 62%). Possible IRSF or solver service.',
          status: 'new', severity: 'high', source: 'iris', alert_type: 'challenge_abuse',
          created_at: now, updated_at: now, session_ids: [], related_alert_ids: [], tags: ['challenge', 'voip', 'irsf'],
          iocs: [],
          metadata: { solve_rate: 98.7, baseline: 62.0, voip_count: 341 },
        },
      ]
      for (const alert of demoAlerts) {
        const p = safePath(ALERTS_DIR, `${alert.id}.json`)
        if (p) fs.writeFileSync(p, JSON.stringify(alert, null, 2))
      }
      seeded.alerts = demoAlerts.length
    }

    // Seed demo playbooks (only if none exist)
    const existingPlaybooks = fs.readdirSync(PLAYBOOKS_DIR).filter(f => f.endsWith('.json'))
    if (existingPlaybooks.length === 0) {
      const demoPlaybooks = [
        {
          id: 'pb-reg-spike', name: 'Registration Spike Triage', description: 'Automated registration spike investigation: email domains → IP clustering → device fingerprints → restriction check → SEV assessment.',
          category: 'registration_spike', version: 1, created_at: now, updated_at: now,
          inputs: [{ name: 'DATE', type: 'date', description: 'Investigation date', required: true, default: new Date(Date.now() - 86400000).toISOString().split('T')[0] }],
          nodes: [
            { id: 'n1', ref_id: 'registration-events', ref_type: 'automation', label: 'Email domain analysis', inputs: { DATE: '{{input.DATE}}' }, input_refs: {}, position: { x: 250, y: 0 } },
            { id: 'n2', ref_id: 'registration-events', ref_type: 'automation', label: 'IP clustering', inputs: { DATE: '{{input.DATE}}' }, input_refs: {}, position: { x: 100, y: 150 } },
            { id: 'n3', ref_id: 'device-fingerprint', ref_type: 'automation', label: 'Device fingerprints', inputs: { DATE: '{{input.DATE}}' }, input_refs: {}, position: { x: 400, y: 150 } },
            { id: 'n4', ref_id: '', ref_type: 'prompt', label: 'Analyze findings', inputs: {}, input_refs: {}, body: 'Analyze the registration spike findings from email domains, IP clusters, and device fingerprints. Determine if this is coordinated abuse.', position: { x: 250, y: 300 } },
            { id: 'n5', ref_id: '', ref_type: 'prompt', label: 'SEV Assessment', inputs: {}, input_refs: {}, body: 'Run SEV assessment based on accumulated findings. Check T7D WoW thresholds.', position: { x: 250, y: 450 } },
          ],
          edges: [
            { id: 'e1', source: 'n1', target: 'n4' },
            { id: 'e2', source: 'n2', target: 'n4' },
            { id: 'e3', source: 'n3', target: 'n4' },
            { id: 'e4', source: 'n4', target: 'n5' },
          ],
          entry_node_ids: ['n1', 'n2', 'n3'],
        },
        {
          id: 'pb-ato-triage', name: 'ATO Investigation', description: 'Account takeover investigation: login scoring → MITM rule check → credential washing detection → self-report correlation → SEV.',
          category: 'ato', version: 1, created_at: now, updated_at: now,
          inputs: [{ name: 'DATE', type: 'date', description: 'Investigation date', required: true, default: new Date(Date.now() - 86400000).toISOString().split('T')[0] }],
          nodes: [
            { id: 'n1', ref_id: 'login-score-events', ref_type: 'automation', label: 'Login score analysis', inputs: { DATE: '{{input.DATE}}' }, input_refs: {}, position: { x: 250, y: 0 } },
            { id: 'n2', ref_id: 'rule-performance', ref_type: 'automation', label: 'MITM rule activations', inputs: { DATE: '{{input.DATE}}' }, input_refs: {}, position: { x: 250, y: 150 } },
            { id: 'n3', ref_id: '', ref_type: 'prompt', label: 'Assess ATO impact', inputs: {}, input_refs: {}, body: 'Assess the scope of the ATO campaign based on login scoring and rule activations.', position: { x: 250, y: 300 } },
          ],
          edges: [
            { id: 'e1', source: 'n1', target: 'n2' },
            { id: 'e2', source: 'n2', target: 'n3' },
          ],
          entry_node_ids: ['n1'],
        },
        {
          id: 'pb-scraping', name: 'Scraping Investigation', description: 'Guest/member scraping triage: denial events → block filter rules → IP analysis → impact.',
          category: 'guest_scraping', version: 1, created_at: now, updated_at: now,
          inputs: [{ name: 'DAYS', type: 'number', description: 'Lookback days', required: false, default: '7' }],
          nodes: [
            { id: 'n1', ref_id: 'site-traffic', ref_type: 'automation', label: 'Denial event volume', inputs: {}, input_refs: {}, position: { x: 250, y: 0 } },
            { id: 'n2', ref_id: 'scraping-events', ref_type: 'automation', label: 'Block filter analysis', inputs: {}, input_refs: {}, position: { x: 250, y: 150 } },
            { id: 'n3', ref_id: '', ref_type: 'prompt', label: 'Summarize scraping', inputs: {}, input_refs: {}, body: 'Summarize scraping findings and recommend rule changes.', position: { x: 250, y: 300 } },
          ],
          edges: [
            { id: 'e1', source: 'n1', target: 'n2' },
            { id: 'e2', source: 'n2', target: 'n3' },
          ],
          entry_node_ids: ['n1'],
        },
      ]
      for (const pb of demoPlaybooks) {
        const p = safePath(PLAYBOOKS_DIR, `${pb.id}.json`)
        if (p) fs.writeFileSync(p, JSON.stringify(pb, null, 2))
      }
      seeded.playbooks = demoPlaybooks.length
    }

    res.json({ success: true, seeded })
  })

  // ----- Investigation Templates API -----

  router.get('/templates', (_req, res) => {
    fs.mkdirSync(TEMPLATES_DIR, { recursive: true })
    const files = fs.readdirSync(TEMPLATES_DIR).filter(f => f.endsWith('.json'))
    const templates = files.map(f => {
      try {
        const data = JSON.parse(fs.readFileSync(path.join(TEMPLATES_DIR, f), 'utf-8'))
        return { id: data.id, name: data.name, description: data.description, skills: data.skills, created_at: data.created_at }
      } catch { return null }
    }).filter(Boolean)
    res.json(templates)
  })

  router.post('/templates', (req, res) => {
    fs.mkdirSync(TEMPLATES_DIR, { recursive: true })
    const template = { ...req.body, id: sanitizeId(req.body.id || `tpl-${Date.now()}`), created_at: new Date().toISOString() }
    const tplPath = safePath(TEMPLATES_DIR, `${template.id}.json`)
    if (!tplPath) { res.status(400).json({ error: 'Invalid ID' }); return }
    fs.writeFileSync(tplPath, JSON.stringify(template, null, 2))
    res.json({ success: true, id: template.id })
  })

  router.delete('/templates/:id', (req, res) => {
    const filePath = safePath(TEMPLATES_DIR, `${sanitizeId(req.params.id)}.json`)
    if (filePath && fs.existsSync(filePath)) fs.unlinkSync(filePath)
    res.json({ success: true })
  })

  // ----- Query History API (cross-session query reuse) -----

  router.get('/queries', (_req, res) => {
    const files = fs.readdirSync(SESSIONS_DIR).filter(f => f.endsWith('.json'))
    const queries: { query: string; label: string; session: string; confidence: number; timestamp: string }[] = []

    for (const f of files.slice(-20)) { // Last 20 sessions
      try {
        const data = JSON.parse(fs.readFileSync(path.join(SESSIONS_DIR, f), 'utf-8'))
        for (const node of Object.values(data.nodes || {}) as Array<{ query?: string; label?: string; confidence?: number; timestamp?: string; status?: string }>) {
          if (node.query && node.status === 'completed' && node.query.toLowerCase().includes('select')) {
            queries.push({
              query: node.query,
              label: node.label || 'Query',
              session: data.name || f,
              confidence: node.confidence || 0,
              timestamp: node.timestamp || '',
            })
          }
        }
      } catch { /* skip corrupted files */ }
    }

    // Deduplicate by normalized query and sort by recency
    const seen = new Set<string>()
    const unique = queries
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
      .filter(q => {
        const key = q.query.replace(/\s+/g, ' ').trim().toLowerCase()
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
      .slice(0, 50)

    res.json(unique)
  })

  // ----- Bulk Export API -----

  router.get('/export/all', (_req, res) => {
    const files = fs.readdirSync(SESSIONS_DIR).filter(f => f.endsWith('.json'))
    const allSessions = files.map(f => {
      try { return JSON.parse(fs.readFileSync(path.join(SESSIONS_DIR, f), 'utf-8')) }
      catch { return null }
    }).filter(Boolean)

    res.setHeader('Content-Type', 'application/json')
    res.setHeader('Content-Disposition', 'attachment; filename="all-investigations.json"')
    res.json({ exported_at: new Date().toISOString(), session_count: allSessions.length, sessions: allSessions })
  })

  // ----- Export API -----

  router.post('/export/json', (req, res) => {
    res.setHeader('Content-Type', 'application/json')
    res.setHeader('Content-Disposition', `attachment; filename="investigation-${sanitizeId(req.body.id || 'export')}.json"`)
    res.json(req.body)
  })

  return router
}
