import { safePath } from '../../middleware/sanitize.js'
import fs from 'fs'
import path from 'path'

export interface AutomationsStoreConfig {
  automationsDir: string
  skillsDir: string
}

// Headless account mapping for skill categories
export const ACCOUNT_MAP: Record<string, string> = {
  'registration-events': 'register', 'account-takeover': 'ir2ato', 'scraping': 'ir2scraping',
  'login-analysis': 'login', 'fake-account-research': 'ir2fake', 'challenge-events': 'trustim',
  'invitation-scoring': 'trustim', 'site-traffic': 'trustim', 'rule-performance': 'trustim',
  'account-activity': 'trustim', 'device-fingerprint': 'trustim',
}

// DAVI widget definitions (always available)
export const DAVI_WIDGETS = [
  { id: 'davi-sevcalculator', name: 'SevCalculatorWidget', desc: 'Automated cohort SEV assessment (DIHE + scraping WoW)', category: 'sev-assessment', params: [{ name: 'COHORT_MEMBER_IDS', type: 'string', description: 'SQL subquery returning member IDs', required: true }], body: 'SevCalculatorWidget(cohort_member_ids={COHORT_MEMBER_IDS})' },
  { id: 'davi-dihe', name: 'DiheWidget', desc: 'DIHE analysis by account type', category: 'impact-analysis', params: [{ name: 'ACCOUNT_TYPE', type: 'string', description: 'fake or ato', required: true, default: 'fake' }, { name: 'PERIOD', type: 'string', description: 'Time period', required: false, default: '7d' }], body: 'DiheWidget(account_type={ACCOUNT_TYPE}, period={PERIOD})' },
  { id: 'davi-ipactivity', name: 'IPActivityWidget', desc: 'IP/search pivot from member IDs or IPs', category: 'ato', params: [{ name: 'INPUT_VALUES', type: 'member_id_list', description: 'Member IDs or IPs', required: true }, { name: 'PERIOD', type: 'string', description: 'Lookback period', required: false, default: '30d' }], body: 'IPActivityWidget(input_values={INPUT_VALUES}, period={PERIOD})' },
  { id: 'davi-scraping', name: 'CaptainScrapingWidget', desc: 'Per-member scraping patterns (InVizor)', category: 'scraping', params: [{ name: 'MEMBER_IDS', type: 'member_id_list', description: 'Member IDs', required: true }], body: 'CaptainScrapingWidget(member_ids={MEMBER_IDS})' },
  { id: 'davi-surface', name: 'SurfaceVisualizationWidget', desc: 'Registration traffic visualization with NL filtering', category: 'registration', params: [{ name: 'START_DATE', type: 'date', description: 'Start date', required: true }, { name: 'END_DATE', type: 'date', description: 'End date', required: true }, { name: 'PROMPT', type: 'string', description: 'Natural language filter', required: false, default: 'top 10 countries hourly line chart' }], body: 'SurfaceVisualizationWidget(start_date={START_DATE}, end_date={END_DATE}, prompt={PROMPT})' },
  { id: 'davi-keywords', name: 'KeywordsAnalysisWidget', desc: 'Find members searching specific keywords', category: 'messaging-abuse', params: [{ name: 'KEYWORDS', type: 'string', description: 'Comma-separated keywords', required: true }, { name: 'PERIOD', type: 'string', description: 'Lookback period', required: false, default: '7d' }], body: 'KeywordsAnalysisWidget(keywords={KEYWORDS}, period={PERIOD})' },
  { id: 'davi-searchterms', name: 'SearchTermRankingWidget', desc: 'Search term ranking by member IDs', category: 'messaging-abuse', params: [{ name: 'MIDS', type: 'member_id_list', description: 'Member IDs', required: true }, { name: 'PERIOD', type: 'string', description: 'Lookback period', required: false, default: '30d' }], body: 'SearchTermRankingWidget(mids={MIDS}, period={PERIOD})' },
  { id: 'davi-magicplot', name: 'MagicPlotWidget', desc: 'Auto-detect and plot any DataFrame', category: 'utility', params: [{ name: 'DATA_QUERY', type: 'string', description: 'SQL query or DataFrame expression', required: true }], body: 'MagicPlotWidget(data_query={DATA_QUERY})' },
]

/** Module-level default config — set once via initAutomationsStore() */
let _defaultConfig: AutomationsStoreConfig | null = null

/** Initialize the store with default config (called at app startup) */
export function initAutomationsStore(config: AutomationsStoreConfig): void {
  _defaultConfig = config
}

function resolveConfig(config?: AutomationsStoreConfig): AutomationsStoreConfig {
  const resolved = config || _defaultConfig
  if (!resolved) throw new Error('AutomationsStore not initialized — call initAutomationsStore() first')
  return resolved
}

/** Skill automation cache */
let _skillAutomationCache: any[] | null = null
let _skillAutomationCacheTime = 0

/** Dynamically parse action skills into automations — cached for 30s */
function loadSkillAutomations(skillsDir: string): any[] {
  if (_skillAutomationCache && Date.now() - _skillAutomationCacheTime < 30000) return _skillAutomationCache

  const automations: any[] = []
  const actionSkillsDir = path.join(skillsDir, 'actions')
  if (!fs.existsSync(actionSkillsDir)) { _skillAutomationCache = []; _skillAutomationCacheTime = Date.now(); return [] }

  try {
    const skillDirs = fs.readdirSync(actionSkillsDir).filter(d => {
      try { return fs.statSync(path.join(actionSkillsDir, d)).isDirectory() } catch { return false }
    })

    for (const dir of skillDirs) {
      const skillPath = path.join(actionSkillsDir, dir, 'SKILL.md')
      if (!fs.existsSync(skillPath)) continue
      try {
        const content = fs.readFileSync(skillPath, 'utf-8')
        const fmMatch = content.match(/^---\n([\s\S]*?)\n---/)
        let name = dir, description = ''
        if (fmMatch) {
          const nameMatch = fmMatch[1].match(/name:\s*(.+)/)
          const descMatch = fmMatch[1].match(/description:\s*(.+)/)
          if (nameMatch) name = nameMatch[1].trim()
          if (descMatch) description = descMatch[1].trim()
        }
        const sqlBlocks = content.match(/```sql\n([\s\S]*?)```/g) || []
        for (let i = 0; i < sqlBlocks.length; i++) {
          const sql = sqlBlocks[i].replace(/```sql\n/, '').replace(/```$/, '').trim()
          const paramMatches = [...new Set(sql.match(/\{([A-Z_]+)\}/g) || [])]
          const inputs = paramMatches.map(p => {
            const pn = p.replace(/[{}]/g, '')
            return { name: pn, type: pn.includes('DATE') ? 'date' : pn.includes('MEMBER') ? 'member_id_list' : 'string', description: pn.toLowerCase().replace(/_/g, ' '), required: true }
          })
          const blockIndex = content.indexOf(sqlBlocks[i])
          const headerMatch = content.slice(0, blockIndex).match(/###?\s+(.+)\n[^#]*$/)?.[1] || `Query ${i + 1}`
          automations.push({
            id: `skill-${dir}-${i}`,
            name: `${name}: ${headerMatch}`,
            description: description || headerMatch,
            category: dir,
            exec_type: 'trino_query',
            exec_body: sql,
            exec_config: { headless_account: ACCOUNT_MAP[dir] || 'trustim' },
            inputs,
            outputs: [{ name: 'result', type: 'string', description: 'Query result', required: true }],
            source: 'skill',
            source_skill: dir,
          })
        }
      } catch { /* skip corrupt skills */ }
    }
  } catch { /* skills dir issue */ }

  // Add DAVI widgets
  for (const w of DAVI_WIDGETS) {
    automations.push({
      id: w.id,
      name: w.name,
      description: w.desc,
      category: w.category,
      exec_type: 'davi_widget',
      exec_body: w.body,
      exec_config: { widget_name: w.name, timeout: 300000 },
      inputs: w.params,
      outputs: [{ name: 'result', type: 'string', description: 'Widget output', required: true }],
      source: 'built-in',
    })
  }

  _skillAutomationCache = automations
  _skillAutomationCacheTime = Date.now()
  return automations
}

/** Load custom user-created automations from disk */
function loadCustomAutomations(automationsDir: string): any[] {
  const customAutos: any[] = []
  try {
    const files = fs.readdirSync(automationsDir).filter(f => f.endsWith('.json'))
    for (const f of files) {
      try {
        const data = JSON.parse(fs.readFileSync(path.join(automationsDir, f), 'utf-8'))
        data.source = 'custom'
        customAutos.push(data)
      } catch { /* skip */ }
    }
  } catch { /* dir may not exist */ }
  return customAutos
}

/** Get all automations: dynamic from skills + custom from .automations/ */
export function getAllAutomations(config?: AutomationsStoreConfig): any[] {
  const c = resolveConfig(config)
  const skillAutos = loadSkillAutomations(c.skillsDir)
  const customAutos = loadCustomAutomations(c.automationsDir)
  return [...skillAutos, ...customAutos]
}

/** Find an automation by ID (skill-based or custom) */
export function findAutomation(id: string, config?: AutomationsStoreConfig): any | null {
  const all = getAllAutomations(config)
  return all.find(a => a.id === id) || null
}

/** Save a custom automation to disk */
export function saveAutomation(automationsDir: string, id: string, data: any): void {
  const filePath = safePath(automationsDir, `${id}.json`)
  if (!filePath) throw new Error('Invalid ID')
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2))
}

/** Load an existing custom automation from disk (returns null if not found) */
export function loadAutomation(automationsDir: string, id: string): any | null {
  const filePath = safePath(automationsDir, `${id}.json`)
  if (!filePath || !fs.existsSync(filePath)) return null
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'))
}

/** Delete a custom automation from disk */
export function deleteAutomation(automationsDir: string, id: string): void {
  const filePath = safePath(automationsDir, `${id}.json`)
  if (filePath && fs.existsSync(filePath)) fs.unlinkSync(filePath)
}
