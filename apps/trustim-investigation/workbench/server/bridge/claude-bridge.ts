/**
 * Claude Code Bridge — Real subprocess integration with Claude Code CLI.
 *
 * Spawns `claude -p "message" --output-format stream-json --verbose` and parses
 * the actual streaming JSON format which emits events like:
 *
 *   {"type":"system","subtype":"init","tools":[...],"mcp_servers":[...]}
 *   {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}
 *   {"type":"assistant","message":{"content":[{"type":"tool_use","id":"...","name":"Bash","input":{...}}]}}
 *   {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"...","content":"..."}]}}
 *   {"type":"result","subtype":"success","result":"final text","session_id":"..."}
 */

import { spawn, type ChildProcess } from 'child_process'

export interface BridgeEvent {
  type: 'init' | 'text' | 'tool_start' | 'tool_end' | 'result' | 'error' | 'done'
  data: {
    text?: string
    toolName?: string
    toolId?: string
    toolInput?: Record<string, unknown>
    toolResult?: string
    serverName?: string
    error?: string
    exitCode?: number
    tools?: string[]
    mcpServers?: Array<{ name: string; status: string }>
    /** Token usage from assistant messages */
    inputTokens?: number
    outputTokens?: number
  }
}

export type BridgeEventHandler = (event: BridgeEvent) => void

export class ClaudeBridge {
  private handlers: Set<BridgeEventHandler> = new Set()
  private activeProc: ChildProcess | null = null
  private projectDir: string
  private _available: boolean | null = null
  /** Maps tool_use id → tool name so tool_end can pass the name for matching */
  private pendingToolNames: Map<string, string> = new Map()
  /** Resolves when an in-progress abort completes (process group fully dead) */
  private abortPromise: Promise<void> | null = null
  maxTurns: number = 25

  constructor(projectDir: string) {
    this.projectDir = projectDir
  }

  async isAvailable(): Promise<boolean> {
    if (this._available !== null) return this._available
    return new Promise((resolve) => {
      const check = spawn('which', ['claude'])
      check.on('close', (code) => {
        this._available = code === 0
        resolve(this._available)
      })
      check.on('error', () => {
        this._available = false
        resolve(false)
      })
    })
  }

  isReady(): boolean {
    return this._available === true
  }

  /**
   * Send a message to Claude Code via `claude -p` and stream events back.
   */
  async send(message: string, systemPrompt?: string): Promise<void> {
    const available = await this.isAvailable()
    if (!available) {
      this.emit({ type: 'error', data: { error: 'claude CLI not found in PATH' } })
      this.emit({ type: 'done', data: {} })
      return
    }

    // Kill any active process and wait for it to fully die before spawning
    this.abort()
    if (this.abortPromise) {
      await this.abortPromise
    }

    // Investigation agent context — ONLY investigation, no development
    const defaultSystemPrompt = [
      'You are a Trust & Safety INVESTIGATION AGENT. Your ONLY job is to run Trino queries and analyze results.',
      '',
      'CRITICAL RULES:',
      '- DO NOT modify code, build features, create files, or run development commands.',
      '- DO NOT ask clarifying questions. The user prompt IS your scope. Start querying IMMEDIATELY.',
      '- You have access to the trustim-investigation skills plugin. Use Read/Glob to find relevant skill SQL templates in skills/ directory.',
      '- For Trino: use Bash to curl -s -X POST http://localhost:3100/api/trino/query -H "Content-Type: application/json" -d \'{"query":"SQL"}\'. Optional fields: "headless_account" (default trustim), "server" (default holdem). DO NOT use execute_trino_query MCP tool.',
      '- For Google Docs: use Bash to curl the local API proxy. DO NOT use MCP tools directly (they are not available in this subprocess).',
      '  Create: curl -s -X POST http://localhost:3100/api/docs/create -H "Content-Type: application/json" -d \'{"title":"TITLE"}\'',
      '  Write:  curl -s -X POST http://localhost:3100/api/docs/write -H "Content-Type: application/json" -d \'{"document_id":"ID","elements":[...]}\'',
      '  Read:   curl -s -X POST http://localhost:3100/api/docs/read -H "Content-Type: application/json" -d \'{"document_id":"ID"}\'',
      '- Use Bash for ir CLI and davi_runner.py, Read/Glob/Grep for skills.',
      '- Ignore any project rules about coding patterns, tests, or development workflows.',
      '',
      `TODAY: ${new Date().toISOString().split('T')[0]} (partition format: ${new Date().toISOString().split('T')[0]}-00)`,
      '',
      'INVESTIGATION APPROACH:',
      '1. FIRST: Read the relevant SKILL.md files for the investigation topic. Use Read("skills/actions/<name>/SKILL.md") to load the SQL templates. DO NOT write queries from memory — the skill files have the correct column names, JOINs, and WHERE clauses.',
      '2. Adapt the skill SQL templates to the specific investigation (fill in dates, member IDs, domains, etc).',
      '3. Run adapted queries using the curl command above. One sentence of reasoning, then execute.',
      '4. When you find signals, read additional skill files for follow-up dimensions.',
      '5. Default date: yesterday. Default scope: full population.',
      '6. If a query fails with COLUMN_NOT_FOUND or TABLE_NOT_FOUND, re-read the SKILL.md and fix the column names. If the skill file does not cover the table, run DESCRIBE first.',
      '7. NEVER fabricate SQL from scratch when a skill template exists. The skill files are the source of truth for column names and query patterns.',
      '',
      'TABLE COLUMN RULES:',
      '- tracking.* tables use DOT notation: header.memberid, email, ip2str(requestheader.ipasbytes)',
      '- tracking_column.* tables use DOUBLE UNDERSCORE: header__memberid, requestheader__ip',
      '- NEVER mix them. If unsure, DESCRIBE the table first.',
      '- Prefer tracking.scoreeventforregistration over tracking_column.scoreEvent for registration scoring.',
      '',
      'KEY PATTERNS:',
      '- Registration: email domains (split_part), IP clustering, device fingerprints (canvashash, webglrenderer)',
      '- ATO: scoreevent SCORER_LOGIN, activated rules (MITM, ColorFish)',
      '- Scraping: userrequestdenialevent, block filter rules',
      '- Challenge: securitychallengeevent, solve rates, IRSF',
      '- Impact: u_tds.fact_experience_base (DIHE), u_metrics.user_flagging_v3_union (T7D WoW)',
      '',
      'TABLES: tracking.registrationevent, tracking.scoreevent, tracking.securitychallengeevent,',
      'tracking.userrequestdenialevent, TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent,',
      'prod_foundation_tables.dim_member_trust_restrictions, u_metrics.user_flagging_v3_union',
      '',
      'AVAILABLE INVESTIGATION SKILLS (exact paths: skills/actions/<name>/SKILL.md — use Read to load, e.g. Read("skills/actions/registration-events/SKILL.md")):',
      '- registration-events: email domain detection, IP coordination, cookie signals, suspicious patterns, cold reg analysis',
      '- account-activity: 2FA tracking, email changes, ASTA job results, password resets, login history',
      '- challenge-events: challenge rates, solve rates by type, IRSF detection, Telesign cost analysis',
      '- device-fingerprint: canvas hash clustering, WebGL renderer analysis, SwiftShader detection, RTT analysis',
      '- invitation-scoring: mass sender detection, delay impact, messaging abuse, ABI analysis',
      '- rule-performance: activated rule analysis, MITM/ColorFish detection, rule hit rates',
      '- site-traffic: denial events, block filter rules, scraping patterns, egression check',
      '- fake-account-research: DIHE breakdown, profile completion, restriction status, dormant account signals',
      '',
      'INVESTIGATION CHECKLIST — cover these dimensions:',
      '1. Email domains (split_part analysis)',
      '2. IP clustering (coordination, datacenter vs residential)',
      '3. Device fingerprints (canvas hash, WebGL, SwiftShader)',
      '4. Challenge rates (captcha, Telesign)',
      '5. Restriction status (dim_member_trust_restrictions)',
      '6. WoW metrics (T7D week-over-week)',
      '7. Impact assessment (DIHE via fact_experience_base)',
      '8. SEV assessment (if findings warrant it)',
      '',
      'ANALYSIS OUTPUT FORMAT — When reporting findings between queries, structure your analysis like a T&S investigation report:',
      '- Lead with specific numbers and comparisons ("+20.7% above 7-day avg", "3× global WoW")',
      '- Identify distinct campaigns/clusters with IOCs: email patterns, IP ranges, user agents, device fingerprints',
      '- Use tables in your reasoning (markdown tables are fine) for baselines, breakdowns, model performance',
      '- Flag defense gaps explicitly (e.g., "⚠️ DEFENSE GAP: these accounts are ALL unrestricted")',
      '- For your FINAL response, include: Executive Summary (2-3 sentences), per-entity findings with data tables, SEV assessment with threshold table, Recommended Actions (🔴 Immediate, 🟠 Short-term, 🟡 Medium-term, 🟢 Monitoring)',
    ].join('\n')

    const fullSystemPrompt = systemPrompt
      ? `${defaultSystemPrompt}\n\n${systemPrompt}`
      : defaultSystemPrompt

    const args = [
      '-p', message,
      '--output-format', 'stream-json',
      '--verbose',
      '--max-turns', String(this.maxTurns),
      '--system-prompt', fullSystemPrompt,
      // Restrict code modification tools — but allow all investigation tools (same as CLI)
      '--disallowedTools',
      'Edit', 'Write', 'NotebookEdit',
      // Pre-approve investigation tools so the subprocess doesn't prompt for permission
      '--allowedTools',
      'mcp__captain__search_slack',
      'mcp__captain__search_jira_issues',
      'mcp__captain__get_jira_issue',
      'mcp__captain__create_google_docs_document',
      'mcp__captain__write_to_google_docs_document',
      'mcp__captain__read_google_docs_document',
      'mcp__captain__search_confluence_content',
      'mcp__captain__unified_context_search',
      'mcp__captain__jarvis_codesearch',
      'Read',
      'Glob',
      'Grep',
      'Bash',
    ]

    const proc = spawn('claude', args, {
      cwd: this.projectDir,
      env: { ...process.env },
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: true, // Own process group so we can kill all children on abort
    })
    this.activeProc = proc

    let buffer = ''

    proc.stdout?.on('data', (chunk: Buffer) => {
      buffer += chunk.toString()
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.trim()) this.processEvent(line.trim())
      }
    })

    proc.stderr?.on('data', (chunk: Buffer) => {
      const msg = chunk.toString().trim()
      // Filter out the bun AVX warning
      if (msg && !msg.includes('CPU lacks AVX') && !msg.startsWith('warn:') && !msg.startsWith('https://')) {
        this.emit({ type: 'error', data: { error: msg } })
      }
    })

    return new Promise<void>((resolve) => {
      proc.on('close', (code) => {
        if (buffer.trim()) this.processEvent(buffer.trim())
        this.activeProc = null
        this.emit({ type: 'done', data: { exitCode: code ?? 0 } })
        resolve()
      })
      proc.on('error', (err) => {
        this.activeProc = null
        this.emit({ type: 'error', data: { error: err.message } })
        this.emit({ type: 'done', data: {} })
        resolve()
      })
    })
  }

  abort(): void {
    const proc = this.activeProc
    if (!proc || !proc.pid) {
      this.activeProc = null
      this.abortPromise = null
      return
    }
    const pid = proc.pid

    this.activeProc = null

    // Kill the entire process group (claude + all its children: MCP servers, Bash subprocesses, etc.)
    // Negative PID kills the whole group since we spawned with detached: true
    try {
      process.kill(-pid, 'SIGTERM')
    } catch {
      // Process may have already exited
      this.abortPromise = null
      return
    }

    // Track when the process group is fully dead so send() can wait
    this.abortPromise = new Promise<void>((resolve) => {
      // Escalate to SIGKILL after 3s if it doesn't die
      const escalationTimer = setTimeout(() => {
        try {
          process.kill(-pid, 'SIGKILL')
        } catch {
          // Already dead
        }
        // Give SIGKILL 1s to take effect, then resolve regardless
        setTimeout(() => { this.abortPromise = null; resolve() }, 1000)
      }, 3000)

      // Clean up immediately if the process exits on its own
      proc.once('close', () => {
        clearTimeout(escalationTimer)
        this.abortPromise = null
        resolve()
      })
    })
  }

  onEvent(handler: BridgeEventHandler): void { this.handlers.add(handler) }
  offEvent(handler: BridgeEventHandler): void { this.handlers.delete(handler) }

  private emit(event: BridgeEvent): void {
    for (const handler of this.handlers) handler(event)
  }

  /**
   * Parse a single JSON line from claude's stream-json output.
   * Matches the REAL format observed from `claude -p --output-format stream-json --verbose`.
   */
  private processEvent(line: string): void {
    let event: Record<string, unknown>
    try {
      event = JSON.parse(line)
    } catch {
      return // Skip non-JSON lines
    }

    const type = event.type as string

    // --- System init: contains available tools and MCP servers ---
    if (type === 'system' && event.subtype === 'init') {
      this.emit({
        type: 'init',
        data: {
          tools: event.tools as string[] || [],
          mcpServers: event.mcp_servers as Array<{ name: string; status: string }> || [],
        },
      })
      return
    }

    // --- Assistant message: contains text or tool_use content blocks ---
    if (type === 'assistant') {
      const msg = event.message as Record<string, unknown> | undefined
      if (!msg) return
      const content = msg.content as Array<Record<string, unknown>> | undefined
      if (!Array.isArray(content)) return

      for (const block of content) {
        if (block.type === 'text' && block.text) {
          this.emit({ type: 'text', data: { text: String(block.text) } })
        } else if (block.type === 'tool_use') {
          const toolName = String(block.name || 'unknown')
          const toolId = String(block.id || '')
          const toolInput = (block.input || {}) as Record<string, unknown>
          // Track name so tool_end can pass it for matching
          if (toolId) this.pendingToolNames.set(toolId, toolName)
          this.emit({
            type: 'tool_start',
            data: {
              toolName,
              toolId,
              toolInput,
              serverName: this.inferServer(toolName),
            },
          })
        } else if (block.type === 'thinking' && block.thinking) {
          // Capture agent thinking for observability display
          this.emit({ type: 'text', data: { text: String(block.thinking) } })
        }
      }

      // Extract token usage from the message
      const usage = msg.usage as Record<string, unknown> | undefined
      if (usage) {
        const inputTokens = Number(usage.input_tokens || 0) + Number(usage.cache_creation_input_tokens || 0) + Number(usage.cache_read_input_tokens || 0)
        const outputTokens = Number(usage.output_tokens || 0)
        if (inputTokens > 0 || outputTokens > 0) {
          this.emit({ type: 'text', data: { inputTokens, outputTokens } })
        }
      }
      return
    }

    // --- Tool result (user message with tool_result content) ---
    if (type === 'user') {
      const msg = event.message as Record<string, unknown> | undefined
      if (!msg) return
      const content = msg.content as Array<Record<string, unknown>> | undefined
      if (!Array.isArray(content)) return

      for (const block of content) {
        if (block.type === 'tool_result') {
          const resultContent = block.content
          let resultText = ''

          if (typeof resultContent === 'string') {
            resultText = resultContent
          } else if (Array.isArray(resultContent)) {
            // tool_result content can be an array of text blocks
            resultText = resultContent.map((c: Record<string, unknown>) => String(c.text || c.content || '')).join('\n')
          } else if (resultContent && typeof resultContent === 'object') {
            resultText = JSON.stringify(resultContent, null, 2)
          }

          // Check for the tool_use_result metadata which has richer info
          const meta = event.tool_use_result as Record<string, unknown> | undefined
          if (meta) {
            if (meta.stdout) resultText = String(meta.stdout)
            if (meta.type === 'text' && meta.file) {
              const file = meta.file as Record<string, unknown>
              resultText = String(file.content || resultText)
            }
          }

          const isError = block.is_error === true || (meta?.is_error === true)
          const toolUseId = String(block.tool_use_id || '')

          // Look up the tool name from our pending map so the server can match
          // tool_end to tool_start even when IDs don't align exactly
          const toolName = this.pendingToolNames.get(toolUseId) || ''
          this.pendingToolNames.delete(toolUseId)

          this.emit({
            type: 'tool_end',
            data: {
              toolName,
              toolId: toolUseId,
              toolResult: resultText,
              error: isError ? resultText : undefined,
            },
          })
        }
      }
      return
    }

    // --- Final result ---
    if (type === 'result') {
      this.emit({
        type: 'result',
        data: { text: String(event.result || '') },
      })
      return
    }
  }

  private inferServer(toolName: string): string {
    if (toolName.startsWith('mcp__captain__')) return 'captain'
    if (toolName.startsWith('mcp__')) return toolName.split('__')[1] || 'mcp'
    if (['Bash', 'Read', 'Write', 'Edit', 'Glob', 'Grep', 'Agent', 'WebFetch', 'Task', 'Skill'].includes(toolName)) {
      return 'claude-code'
    }
    return 'unknown'
  }
}
