import { WebSocket } from 'ws'
import { ClaudeBridge, type BridgeEvent } from './claude-bridge.js'
import { getAllAutomations } from '../domains/automations/store.js'

/** Detect Trino authentication/credential errors in tool output */
export function isTrinoAuthError(result: string): boolean {
  if (!result) return false
  const lower = result.toLowerCase()
  return lower.includes('authentication error') ||
    lower.includes('authentication failed') ||
    lower.includes('passwordauthenticator') ||
    (lower.includes('kerberos') && lower.includes('failed')) ||
    (lower.includes('access denied') && lower.includes('trino'))
}

/**
 * Handle an agent message by forwarding it through the Claude Code bridge.
 * Each tool call from the agent becomes a graph node event sent to the client.
 */
export async function handleAgentMessage(ws: WebSocket, message: string, systemPrompt: string | undefined, bridge: ClaudeBridge) {
  const send = (data: object) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
    }
  }

  // Track tool calls — support parallel tools via a stack/map keyed by tool ID
  const activeTools: Map<string, { name: string; input: Record<string, unknown>; server: string; startTime: number; scaffolding?: boolean }> = new Map()
  let textBuffer = ''
  let parallelSiblingCount = 0 // Track how many tools started in one assistant turn
  let finished = false

  const finish = () => {
    if (finished) return
    finished = true
    clearTimeout(safetyTimeout)
    bridge.offEvent(handler)
  }

  const handler = (event: BridgeEvent) => {
    switch (event.type) {
      case 'init':
        // Claude session initialized — send available tools/MCP info
        send({
          type: 'agent_init',
          payload: {
            tools: event.data.tools,
            mcpServers: event.data.mcpServers,
          },
        })
        break

      case 'text':
        if (event.data.text) {
          textBuffer += event.data.text
          parallelSiblingCount = 0
          send({
            type: 'agent_text',
            payload: { text: event.data.text, full: textBuffer },
          })
        }
        // Forward token usage if present
        if (event.data.inputTokens || event.data.outputTokens) {
          send({
            type: 'agent_tokens',
            payload: {
              inputTokens: event.data.inputTokens || 0,
              outputTokens: event.data.outputTokens || 0,
            },
          })
        }
        break

      case 'tool_start': {
        const toolName = event.data.toolName || 'unknown'
        const toolInput = event.data.toolInput || {}
        const serverName = event.data.serverName || 'unknown'
        const toolId = event.data.toolId || `auto-${Date.now()}`

        activeTools.set(toolId, { name: toolName, input: toolInput, server: serverName, startTime: Date.now() })

        // Skip scaffolding tools that are Claude bootstrapping (not investigation steps)
        if (isScaffoldingTool(toolName, toolInput)) {
          activeTools.get(toolId)!.scaffolding = true
          break
        }

        parallelSiblingCount++

        const actionType = inferActionType(toolName, serverName, toolInput)
        const label = buildToolLabel(toolName, toolInput)
        const query = extractQuery(toolName, toolInput)

        // Report Trino-via-Bash as execute_trino_query so the frontend treats it as a SQL query
        const reportedToolName = (toolName === 'Bash' && extractTrinoFromBash(String(toolInput.command || '')))
          ? 'execute_trino_query'
          : toolName.replace(/^mcp__captain__/, '')

        send({
          type: 'agent_node_start',
          payload: {
            actionType,
            label,
            query,
            toolName: reportedToolName,
            sourceTool: actionType === 'query_execution' ? 'trino' : serverName,
            parameters: toolInput,
            reasoning: textBuffer.trim() || undefined,
            // Tell the frontend this is a parallel sibling (>1 tools in same turn)
            isParallelSibling: parallelSiblingCount > 1,
            toolId,
          },
        })

        textBuffer = ''
        break
      }

      case 'tool_end': {
        // Match with the active tool — prefer explicit toolId, then name match.
        // NEVER fall back to lastToolId — that causes scaffolding tool results
        // to steal the completion event from real investigation tools.
        let matchedId: string | null = null
        if (event.data.toolId && activeTools.has(event.data.toolId)) {
          matchedId = event.data.toolId
        } else if (event.data.toolName) {
          for (const [id, tool] of activeTools) {
            if (tool.name.includes(event.data.toolName)) {
              matchedId = id
              break
            }
          }
        }

        // No match found — this is likely a result for a tool we didn't track
        // (e.g., a scaffolding tool whose start was suppressed). Log and skip.
        if (!matchedId || !activeTools.has(matchedId)) {
          console.warn(`tool_end: no matching active tool for id=${event.data.toolId || '?'} name=${event.data.toolName || '?'} (${activeTools.size} active)`)
          break
        }

        const activeTool = activeTools.get(matchedId)!

        // Skip graph node completion for scaffolding tools
        if (activeTool.scaffolding) {
          activeTools.delete(matchedId)
          break
        }

        const durationMs = activeTool ? Date.now() - activeTool.startTime : 0
        const isError = !!event.data.error
        const result = event.data.toolResult || event.data.error || ''

        send({
          type: 'agent_node_complete',
          payload: {
            toolName: activeTool?.name?.replace(/^mcp__captain__/, '') || event.data.toolName || '',
            resultRaw: (activeTool?.name?.includes('trino') || (activeTool?.name === 'Bash' && extractTrinoFromBash(String(activeTool.input.command || '')))) ? cleanTrinoResult(result) : result,
            resultSummary: summarizeResult(result),
            durationMs,
            success: !isError,
            error: event.data.error,
            toolId: matchedId,
          },
        })

        // Detect Trino auth errors and notify the client
        if (activeTool?.name?.includes('trino') && isTrinoAuthError(result)) {
          send({
            type: 'agent_auth_required',
            payload: {
              toolName: 'execute_trino_query',
              failedQuery: String(activeTool.input.query || ''),
              error: result.slice(0, 300),
              toolId: matchedId,
            },
          })
        }

        activeTools.delete(matchedId)
        break
      }

      case 'result':
        // The result event contains the full final text, but all text was
        // already streamed to the client via agent_text events. Sending
        // agent_response here would duplicate the output. Skip it.
        break

      case 'error':
        send({
          type: 'agent_error',
          payload: { error: event.data.error },
        })
        break

      case 'done':
        send({
          type: 'agent_done',
          payload: { exitCode: event.data.exitCode },
        })
        finish()
        break
    }
  }

  bridge.onEvent(handler)

  // Safety timeout: if claude hangs for 5 minutes, clean up
  const safetyTimeout = setTimeout(() => {
    finish()
    bridge.abort()
    send({ type: 'agent_error', payload: { error: 'Agent timed out after 5 minutes' } })
    send({ type: 'agent_done', payload: { exitCode: -1 } })
  }, 5 * 60 * 1000)

  // PRD Section 11: Network retry with 3 attempts and exponential backoff
  let attempt = 0
  const maxRetries = 3
  while (attempt < maxRetries) {
    try {
      await bridge.send(message, systemPrompt)
      break // Success
    } catch (err) {
      attempt++
      if (attempt >= maxRetries) {
        send({ type: 'agent_error', payload: { error: `Failed after ${maxRetries} attempts: ${err}` } })
        send({ type: 'agent_done', payload: { exitCode: -1 } })
        break
      }
      // Exponential backoff: 1s, 2s, 4s
      const delay = 1000 * Math.pow(2, attempt - 1)
      send({ type: 'agent_text', payload: { text: `Retrying (attempt ${attempt + 1}/${maxRetries})...` } })
      await new Promise(r => setTimeout(r, delay))
    }
  }
  finish()
}

/** Scaffolding tools that are Claude bootstrapping, not investigation steps. */
function isScaffoldingTool(toolName: string, input: Record<string, unknown>): boolean {
  if (toolName === 'ToolSearch') return true
  // Read of skill/config files — not investigation queries
  if (toolName === 'Read') {
    const fp = String(input.file_path || '')
    if (/SKILL\.md|CLAUDE\.md|\.claude\/|\.linkedin\/|architecture\.md|test\.md|coding-pattern\.md|style\.md|package\.json|tsconfig|vite\.config|README/i.test(fp)) return true
    // Any read of source code files is scaffolding, not investigation
    if (/\.(tsx?|jsx?|css|json)$/.test(fp) && !/skills\//.test(fp)) return true
  }
  if (toolName === 'Glob') {
    const pat = String(input.pattern || '')
    if (/skills\//.test(pat) && /SKILL|\.md/.test(pat)) return true
    // Any glob of source code is scaffolding
    if (/\*\.(tsx?|jsx?|css)/.test(pat)) return true
  }
  // Bash commands that aren't investigation-related are scaffolding
  if (toolName === 'Bash') {
    const cmd = String(input.command || '')
    // Allow: commands that start with investigation tools OR contain Trino/curl API calls
    const trimmed = cmd.trim()
    const startsWithInvestigationTool = /^(ir |curl |python)/.test(trimmed)
    const containsTrinoCall = /api\/trino\/query|execute_trino_query/.test(trimmed)
    const containsCurlApi = /curl\s.*localhost:3100\/api/.test(trimmed)
    if (!startsWithInvestigationTool && !containsTrinoCall && !containsCurlApi) return true
  }
  return false
}

/** Cache of automation templates for label matching — uses getAllAutomations() */
let automationLabelCache: { name: string; table: string }[] | null = null
let automationLabelCacheTime = 0

function loadAutomationLabelCache() {
  if (automationLabelCache && Date.now() - automationLabelCacheTime < 60000) return automationLabelCache
  automationLabelCache = getAllAutomations()
    .filter(a => a.exec_type === 'trino_query' && a.exec_body)
    .map(a => {
      const fromMatch = a.exec_body.match(/FROM\s+(\S+)/i)
      return fromMatch ? { name: a.name, table: fromMatch[1].toLowerCase() } : null
    })
    .filter(Boolean) as { name: string; table: string }[]
  automationLabelCacheTime = Date.now()
  return automationLabelCache
}

function matchAutomationName(query: string): string | null {
  const cache = loadAutomationLabelCache()
  const ql = query.toLowerCase()
  for (const { name, table } of cache) {
    if (ql.includes(table)) return name
  }
  return null
}

/** Detect Trino queries wrapped in Bash curl calls and extract the SQL */
function extractTrinoFromBash(cmd: string): string | null {
  if (!/api\/trino\/query/.test(cmd)) return null
  // Try to extract the SQL from the JSON body: "query":"..." or "query": "..."
  const match = cmd.match(/"query"\s*:\s*"((?:[^"\\]|\\.)*)"/s)
    || cmd.match(/"query"\s*:\s*'((?:[^'\\]|\\.)*)'/s)
  if (match) return match[1].replace(/\\"/g, '"').replace(/\\n/g, '\n')
  // Try variable-based: -d "{\"query\":\"$SQL\"}" where SQL was assigned earlier
  const varMatch = cmd.match(/(?:^|\n)\s*(?:SQL|QUERY|sql|query)\s*=\s*["'](.+?)["']/s)
  if (varMatch) return varMatch[1]
  return 'Trino Query'
}

/**
 * Build a human-readable label from a tool call.
 * Handles both built-in Claude Code tools and MCP captain tools (mcp__captain__*).
 */
function buildToolLabel(toolName: string, input: Record<string, unknown>): string {
  // Strip MCP prefix for cleaner labels
  const clean = toolName.replace(/^mcp__captain__/, '')

  switch (clean) {
    case 'execute_trino_query': {
      const query = String(input.query || '')
      // Try to match against a known automation
      const autoName = matchAutomationName(query)
      if (autoName) return autoName

      const tableMatch = query.match(/FROM\s+(\S+)/i)
      const tableName = tableMatch ? tableMatch[1].replace(/tracking\.|tracking_column\.|data_derived\.|prod_foundation_tables\.|u_metrics\.|u_tds\./i, '') : ''
      // Extract what's being selected (GROUP BY dimension)
      const groupByMatch = query.match(/GROUP\s+BY\s+(.+?)(?:\s+(?:ORDER|HAVING|LIMIT)|$)/im)
      const selectHint = groupByMatch ? groupByMatch[1].split(',')[0].trim().replace(/\d+/, '').trim() : ''
      if (tableName && selectHint) return `${tableName}: ${selectHint.slice(0, 30)}`
      return tableName ? `Query: ${tableName}` : 'Trino Query'
    }
    case 'Bash': {
      const cmd = String(input.command || '')
      const trinoSql = extractTrinoFromBash(cmd)
      if (trinoSql) {
        const autoName = matchAutomationName(trinoSql)
        if (autoName) return autoName
        const tableMatch = trinoSql.match(/FROM\s+(\S+)/i)
        const tableName = tableMatch ? tableMatch[1].replace(/tracking\.|tracking_column\.|data_derived\.|prod_foundation_tables\.|u_metrics\.|u_tds\./i, '') : ''
        const groupByMatch = trinoSql.match(/GROUP\s+BY\s+(.+?)(?:\s+(?:ORDER|HAVING|LIMIT)|$)/im)
        const selectHint = groupByMatch ? groupByMatch[1].split(',')[0].trim().replace(/\d+/, '').trim() : ''
        if (tableName && selectHint) return `${tableName}: ${selectHint.slice(0, 30)}`
        return tableName ? `Query: ${tableName}` : 'Trino Query'
      }
      return `Bash: ${cmd.slice(0, 50)}${cmd.length > 50 ? '...' : ''}`
    }
    case 'Read':
      return `Read: ${String(input.file_path || '').split('/').pop() || 'file'}`
    case 'Glob':
      return `Glob: ${input.pattern || '*'}`
    case 'Grep':
      return `Grep: ${input.pattern || '...'}`
    case 'search_slack':
      return `Slack: ${String(input.query || '').slice(0, 40)}`
    case 'search_jira_issues':
      return `Jira: ${String(input.jql || input.query || '').slice(0, 40)}`
    case 'get_jira_issue':
      return `Jira: ${String(input.issue_key || input.key || '')}`
    case 'unified_context_search':
      return `Context: ${String(input.query || '').slice(0, 40)}`
    case 'create_google_docs_document':
      return `Create Doc: ${String(input.title || '').slice(0, 40)}`
    case 'write_to_google_docs_document':
      return 'Write to Doc'
    case 'read_google_docs_document':
      return 'Read Doc'
    case 'search_confluence_content':
      return `Confluence: ${String(input.query || '').slice(0, 40)}`
    case 'jarvis_codesearch':
      return `Code Search: ${String(input.query || '').slice(0, 40)}`
    case 'Skill':
      return `Skill: ${String(input.skill || input.name || '').slice(0, 40)}`
    default:
      return clean.replace(/_/g, ' ')
  }
}

/** Extract the primary query/command from a tool's input */
function extractQuery(toolName: string, input: Record<string, unknown>): string {
  const clean = toolName.replace(/^mcp__captain__/, '')
  switch (clean) {
    case 'execute_trino_query':
      return String(input.query || '')
    case 'Bash': {
      const bashCmd = String(input.command || '')
      const trinoFromBash = extractTrinoFromBash(bashCmd)
      return trinoFromBash || bashCmd
    }
    case 'Read':
      return String(input.file_path || '')
    case 'Glob':
      return String(input.pattern || '')
    case 'Grep':
      return String(input.pattern || '')
    case 'Skill':
      return String(input.skill || input.name || '')
    default:
      return JSON.stringify(input, null, 2)
  }
}

/** Determine action type from tool name and input */
function inferActionType(toolName: string, _serverName: string, input?: Record<string, unknown>): string {
  const clean = toolName.replace(/^mcp__captain__/, '')
  if (clean === 'execute_trino_query') return 'query_execution'
  if (clean === 'Bash' && input && extractTrinoFromBash(String(input.command || ''))) return 'query_execution'
  if (clean === 'Skill') return 'skill_invocation'
  if (['Read', 'Glob', 'Grep', 'unified_context_search', 'search_confluence_content', 'jarvis_codesearch'].includes(clean)) {
    return 'enrichment'
  }
  if (['create_google_docs_document', 'write_to_google_docs_document'].includes(clean)) {
    return 'recommendation' // Publishing/writing is a recommendation action
  }
  return 'mcp_tool_call'
}

/** Clean Trino result noise (SET SESSION output, empty lines at start) */
function cleanTrinoResult(result: string): string {
  return result
    .replace(/^SET SESSION.*\n?/gm, '') // Remove SET SESSION lines
    .replace(/^Query \d+ succeeded\.\n?/gm, '') // Remove "Query N succeeded"
    .replace(/^\s*\n/gm, '') // Remove blank lines at start
    .trim()
}

/** Generate a brief summary of a tool result */
function summarizeResult(result: string): string {
  if (!result) return 'No output'
  const trimmed = cleanTrinoResult(result)
  const lines = trimmed.split('\n').filter(l => l.trim())

  // Short results — return as-is
  if (lines.length <= 3) return trimmed.slice(0, 200)

  // Detect tabular output (common from Trino)
  const firstLine = lines[0]
  const tabCount = (firstLine.match(/\t/g) || []).length
  if (tabCount >= 1 && lines.length >= 2) {
    const dataRows = lines.length - 1
    const headers = firstLine.split('\t').map(h => h.trim())
    const firstRow = lines[1].split('\t').map(c => c.trim())

    // Build a meaningful summary from the first data row
    let topResult = ''
    if (headers.length > 0 && firstRow.length > 0) {
      // Show first column value + a numeric column if available
      const firstVal = firstRow[0]?.slice(0, 30) || ''
      const numCol = firstRow.findIndex((c, i) => i > 0 && /^\d+/.test(c))
      if (numCol >= 0) {
        topResult = ` — top: ${firstVal} (${headers[numCol]}: ${firstRow[numCol]})`
      } else {
        topResult = ` — top: ${firstVal}`
      }
    }

    const colList = headers.slice(0, 3).join(', ')
    return `${dataRows} rows (${colList}${headers.length > 3 ? '...' : ''})${topResult}`
  }

  // Detect 0 rows / empty results
  if (trimmed.includes('0 rows') || (lines.length === 1 && lines[0].includes('(0'))) {
    return 'Query returned 0 rows'
  }

  // Error output
  if (trimmed.toLowerCase().includes('error') || trimmed.toLowerCase().includes('exception')) {
    return `Error: ${lines[0].slice(0, 150)}`
  }

  return `${lines.length} lines of output. ${lines[0].slice(0, 100)}`
}
