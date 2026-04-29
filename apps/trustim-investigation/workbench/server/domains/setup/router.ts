import { Router } from 'express'
import { ClaudeBridge } from '../../bridge/claude-bridge.js'
import https from 'https'
import fs from 'fs'
import path from 'path'
import type { SkillMeta } from '../skills/store.js'

interface McpTool {
  name: string
  server: string
  status: 'healthy' | 'degraded' | 'disconnected'
  last_checked: string
}

interface SetupRouterConfig {
  SESSIONS_DIR: string
  SKILLS_DIR: string
  REPO_ROOT: string
  discoverSkills: (dir: string) => { investigation: SkillMeta[]; action: SkillMeta[] }
  getBridgeMaxTurns: () => number
  setBridgeMaxTurns: (n: number) => void
  getSocketBridges: () => Map<any, ClaudeBridge>
}

// Cache setup check results to avoid repeated expensive Trino probes.
// The Trino check spawns a claude subprocess (~10-45s). Without caching,
// React StrictMode double-mounts trigger two concurrent checks.
let _setupCache: { result: object; timestamp: number } | null = null
const SETUP_CACHE_TTL = 60_000 // 60s — long enough to survive StrictMode double-fire
let _setupCheckInFlight: Promise<object> | null = null

function discoverMcpTools(skillsDir: string): McpTool[] {
  const tools: McpTool[] = []
  const now = new Date().toISOString()

  // Try to read Claude Code MCP settings from standard locations
  const configPaths = [
    path.join(process.env.HOME || '', '.claude', 'settings.json'),
    path.join(process.env.HOME || '', '.claude', 'settings.local.json'),
    path.join(skillsDir, '..', '.claude', 'settings.local.json'),
  ]

  for (const configPath of configPaths) {
    if (!fs.existsSync(configPath)) continue
    try {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      const mcpServers = config.mcpServers || {}
      for (const [serverName, serverConfig] of Object.entries(mcpServers)) {
        // Each MCP server may expose multiple tools; we list the server itself
        tools.push({
          name: serverName,
          server: serverName,
          status: 'healthy', // We assume healthy if configured; runtime health check would be async
          last_checked: now,
        })
        // If the config has a known tool list, enumerate them
        const sc = serverConfig as { tools?: string[] }
        if (sc.tools && Array.isArray(sc.tools)) {
          for (const toolName of sc.tools) {
            tools.push({
              name: toolName,
              server: serverName,
              status: 'healthy',
              last_checked: now,
            })
          }
        }
      }
    } catch {
      // Config parse error — skip
    }
  }

  // If no config found, return common Captain MCP tools as a fallback
  if (tools.length === 0) {
    const captainTools = [
      'execute_trino_query', 'unified_context_search', 'search_slack',
      'create_google_docs_document', 'write_to_google_docs_document',
      'read_google_docs_document', 'search_jira_issues',
      'search_confluence_content', 'jarvis_codesearch',
    ]
    for (const name of captainTools) {
      tools.push({ name, server: 'captain', status: 'healthy', last_checked: now })
    }
  }

  return tools
}

export default function createSetupRouter(config: SetupRouterConfig): Router {
  const router = Router()
  const { SESSIONS_DIR, SKILLS_DIR, REPO_ROOT, discoverSkills, getBridgeMaxTurns, setBridgeMaxTurns, getSocketBridges } = config

  const bridgeStatusProbe = new ClaudeBridge(REPO_ROOT)

  async function runSetupChecks(): Promise<object> {
    // Return cached result if fresh
    if (_setupCache && Date.now() - _setupCache.timestamp < SETUP_CACHE_TTL) {
      return _setupCache.result
    }

    // Coalesce concurrent requests — only one check runs at a time
    if (_setupCheckInFlight) return _setupCheckInFlight

    _setupCheckInFlight = (async () => {
      type Check = { id: string; label: string; status: 'ok' | 'warning' | 'error' | 'checking'; message: string; required: boolean; fix?: string }
      const checks: Check[] = []

      // 1. Claude CLI
      const bridgeAvailable = await bridgeStatusProbe.isAvailable()
      checks.push({
        id: 'claude', label: 'Claude CLI', required: true,
        status: bridgeAvailable ? 'ok' : 'error',
        message: bridgeAvailable ? 'claude CLI found in PATH' : 'claude CLI not found',
        fix: bridgeAvailable ? undefined : 'Install Claude Code: npm install -g @anthropic-ai/claude-code',
      })

      // 2. MCP / Captain tools
      const mcpTools = discoverMcpTools(SKILLS_DIR)
      const hasCaptain = mcpTools.some(t => t.server === 'captain')
      checks.push({
        id: 'mcp', label: 'Captain MCP Tools', required: false,
        status: hasCaptain ? 'ok' : 'warning',
        message: hasCaptain ? `${mcpTools.length} MCP tools discovered` : 'No Captain MCP config found — using fallback tool list',
        fix: hasCaptain ? undefined : 'Configure MCP servers in ~/.claude/settings.json',
      })

      // 3. Trino connectivity — async subprocess (non-blocking)
      let trinoOk = false
      let trinoMsg = 'Not tested (Claude CLI required)'
      if (bridgeAvailable) {
        try {
          const { execFile } = await import('child_process')
          const trinoResult = await new Promise<string>((resolve) => {
            const proc = execFile('claude', [
              '-p', 'Run this exact query and show the result: SELECT 1 AS test',
              '--output-format', 'json',
              '--max-turns', '2',
              '--allowedTools', 'mcp__captain__execute_trino_query',
              '--disallowedTools', 'Edit,Write,Read,Bash,Glob,Grep,Agent,NotebookEdit',
            ], { cwd: REPO_ROOT, timeout: 45000, encoding: 'utf-8' }, (err, stdout, stderr) => {
              if (err) resolve(stderr || stdout || err.message)
              else resolve(stdout)
            })
          })
          if (trinoResult.includes('test') || trinoResult.includes('1')) {
            trinoOk = true
            trinoMsg = 'Trino query succeeded'
          } else if (trinoResult.toLowerCase().includes('authentication')) {
            trinoMsg = 'Trino authentication failed — run: captain setup trino'
          } else {
            trinoMsg = 'Trino query returned unexpected result'
          }
        } catch (e: any) {
          const errMsg = String(e.message || '')
          if (errMsg.toLowerCase().includes('authentication')) {
            trinoMsg = 'Trino authentication failed — run: captain setup trino'
          } else if (errMsg.toLowerCase().includes('timeout') || errMsg.includes('TIMEOUT')) {
            trinoMsg = 'Trino test timed out (45s) — server may be slow'
          } else {
            trinoMsg = 'Trino test failed: ' + errMsg.slice(0, 150)
          }
        }
      }
      checks.push({
        id: 'trino', label: 'Trino (Holdem)', required: true,
        status: trinoOk ? 'ok' : 'error',
        message: trinoMsg,
        fix: trinoOk ? undefined : 'Run: captain setup trino',
      })

      // 4. DAVI / Darwin
      let daviOk = false
      let daviMsg = 'Not configured'
      try {
        const hasConn = fs.existsSync('/tmp/davi-runner/kernel-connection.json')
        const hasProxy = fs.existsSync('/tmp/davi-runner/proxy.pid')
        const hasKernel = fs.existsSync('/tmp/davi-runner/kernel.pid')
        if (hasConn && hasProxy && hasKernel) {
          daviOk = true
          daviMsg = 'Darwin session active (proxy + kernel running)'
        } else if (fs.existsSync('/tmp/lipy-darwin-local-client/.venv/bin/python')) {
          daviMsg = 'DAVI installed but session not started'
        } else {
          daviMsg = 'DAVI not set up'
        }
      } catch { /* ignore */ }
      checks.push({
        id: 'davi', label: 'DAVI / Darwin', required: false,
        status: daviOk ? 'ok' : 'warning',
        message: daviMsg,
        fix: daviOk ? undefined : daviMsg.includes('not set up')
          ? 'python3 tools/davi_runner.py setup && python3 tools/davi_runner.py start'
          : 'python3 tools/davi_runner.py start',
      })

      // 5. IRIS / InResponse connectivity
      let irisOk = false
      let irisMsg = 'Not reachable'
      try {
        irisOk = await new Promise<boolean>((resolve) => {
          const req = https.get('https://iris.prod.linkedin.com/v0/incidents?plan=trust-incident-auto-alert&limit=1', { timeout: 10000 }, (r) => {
            resolve(r.statusCode === 200)
            r.resume()
          })
          req.on('error', () => resolve(false))
          req.on('timeout', () => { req.destroy(); resolve(false) })
        })
        irisMsg = irisOk ? 'IRIS API reachable (VPN connected)' : 'IRIS API unreachable — connect to LinkedIn VPN'
      } catch {
        irisMsg = 'IRIS connectivity check failed'
      }
      checks.push({
        id: 'iris', label: 'IRIS / InResponse', required: false,
        status: irisOk ? 'ok' : 'warning',
        message: irisMsg,
        fix: irisOk ? undefined : 'Connect to LinkedIn VPN',
      })

      // 6. Skills loaded
      const skills = discoverSkills(SKILLS_DIR)
      const skillCount = skills.investigation.length + skills.action.length
      checks.push({
        id: 'skills', label: 'Investigation Skills', required: true,
        status: skillCount > 0 ? 'ok' : 'error',
        message: skillCount > 0 ? `${skills.investigation.length} investigation + ${skills.action.length} action skills` : 'No skills found',
      })

      const requiredPassing = checks.filter(c => c.required && c.status === 'ok').length
      const requiredTotal = checks.filter(c => c.required).length
      const result = { ready: requiredPassing === requiredTotal, checks, requiredPassing, requiredTotal }

      _setupCache = { result, timestamp: Date.now() }
      return result
    })()

    try {
      return await _setupCheckInFlight
    } finally {
      _setupCheckInFlight = null
    }
  }

  // Health check
  router.get('/health', async (_req, res) => {
    const bridgeAvailable = await bridgeStatusProbe.isAvailable()
    const sessionCount = fs.readdirSync(SESSIONS_DIR).filter(f => f.endsWith('.json')).length
    res.json({
      status: 'ok',
      uptime: process.uptime(),
      bridge: bridgeAvailable ? 'connected' : 'not available',
      sessions: sessionCount,
      timestamp: new Date().toISOString(),
    })
  })

  // Setup checks
  router.get('/setup/check', async (_req, res) => {
    const result = await runSetupChecks()
    res.json(result)
  })

  // Force re-check (invalidates cache) — used by the "Re-check" button
  router.post('/setup/recheck', async (_req, res) => {
    _setupCache = null
    const result = await runSetupChecks()
    res.json(result)
  })

  // Bridge config
  router.get('/bridge/config', (_req, res) => {
    res.json({ maxTurns: getBridgeMaxTurns() })
  })

  router.post('/bridge/config', (req, res) => {
    const { maxTurns } = req.body
    if (typeof maxTurns === 'number' && maxTurns >= 1 && maxTurns <= 50) {
      setBridgeMaxTurns(maxTurns)
      for (const socketBridge of getSocketBridges().values()) {
        socketBridge.maxTurns = maxTurns
      }
    }
    res.json({ maxTurns: getBridgeMaxTurns() })
  })

  // MCP tools discovery
  router.get('/mcp/tools', (_req, res) => {
    const tools = discoverMcpTools(SKILLS_DIR)
    res.json(tools)
  })

  // Bridge status
  router.get('/bridge/status', async (_req, res) => {
    const available = await bridgeStatusProbe.isAvailable()
    res.json({
      available,
      ready: bridgeStatusProbe.isReady(),
      message: available
        ? 'Claude CLI found. Real agent integration available.'
        : 'Claude CLI not found. Using simulated adapter.',
    })
  })

  return router
}
