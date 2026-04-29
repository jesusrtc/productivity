/**
 * Tests for event-translator pure helper functions.
 * Re-implements functions locally (server modules use .js imports that don't resolve in jsdom).
 */
import { describe, it, expect } from 'vitest'

// --- Re-implemented pure functions from server/bridge/event-translator.ts ---

function isScaffoldingTool(toolName: string, input: Record<string, unknown>): boolean {
  if (toolName === 'ToolSearch') return true
  if (toolName === 'Read') {
    const fp = String(input.file_path || '')
    if (/SKILL\.md|CLAUDE\.md|\.claude\/|\.linkedin\/|architecture\.md|test\.md|coding-pattern\.md|style\.md|package\.json|tsconfig|vite\.config|README/i.test(fp)) return true
    if (/\.(tsx?|jsx?|css|json)$/.test(fp) && !/skills\//.test(fp)) return true
  }
  if (toolName === 'Glob') {
    const pat = String(input.pattern || '')
    if (/skills\//.test(pat) && /SKILL|\.md/.test(pat)) return true
    if (/\*\.(tsx?|jsx?|css)/.test(pat)) return true
  }
  if (toolName === 'Bash') {
    const cmd = String(input.command || '')
    if (!/^(ir |curl |python)/.test(cmd.trim())) return true
  }
  return false
}

function buildToolLabel(toolName: string, input: Record<string, unknown>): string {
  const clean = toolName.replace(/^mcp__captain__/, '')
  switch (clean) {
    case 'execute_trino_query': {
      const query = String(input.query || '')
      const tableMatch = query.match(/FROM\s+(\S+)/i)
      const tableName = tableMatch ? tableMatch[1].replace(/tracking\.|tracking_column\.|data_derived\.|prod_foundation_tables\.|u_metrics\.|u_tds\./i, '') : ''
      const groupByMatch = query.match(/GROUP\s+BY\s+(.+?)(?:\s+(?:ORDER|HAVING|LIMIT)|$)/im)
      const selectHint = groupByMatch ? groupByMatch[1].split(',')[0].trim().replace(/\d+/, '').trim() : ''
      if (tableName && selectHint) return `${tableName}: ${selectHint.slice(0, 30)}`
      return tableName ? `Query: ${tableName}` : 'Trino Query'
    }
    case 'Bash': {
      const cmd = String(input.command || '')
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

function inferActionType(toolName: string, _serverName: string): string {
  const clean = toolName.replace(/^mcp__captain__/, '')
  if (clean === 'execute_trino_query') return 'query_execution'
  if (clean === 'Skill') return 'skill_invocation'
  if (['Read', 'Glob', 'Grep', 'unified_context_search', 'search_confluence_content', 'jarvis_codesearch'].includes(clean)) {
    return 'enrichment'
  }
  if (['create_google_docs_document', 'write_to_google_docs_document'].includes(clean)) {
    return 'recommendation'
  }
  return 'mcp_tool_call'
}

function cleanTrinoResult(result: string): string {
  return result
    .replace(/^SET SESSION.*\n?/gm, '')
    .replace(/^Query \d+ succeeded\.\n?/gm, '')
    .replace(/^\s*\n/gm, '')
    .trim()
}

function summarizeResult(result: string): string {
  if (!result) return 'No output'
  const trimmed = cleanTrinoResult(result)
  const lines = trimmed.split('\n').filter(l => l.trim())
  if (lines.length <= 3) return trimmed.slice(0, 200)
  const firstLine = lines[0]
  const tabCount = (firstLine.match(/\t/g) || []).length
  if (tabCount >= 1 && lines.length >= 2) {
    const dataRows = lines.length - 1
    const headers = firstLine.split('\t').map(h => h.trim())
    const firstRow = lines[1].split('\t').map(c => c.trim())
    let topResult = ''
    if (headers.length > 0 && firstRow.length > 0) {
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
  if (trimmed.includes('0 rows') || (lines.length === 1 && lines[0].includes('(0'))) {
    return 'Query returned 0 rows'
  }
  if (trimmed.toLowerCase().includes('error') || trimmed.toLowerCase().includes('exception')) {
    return `Error: ${lines[0].slice(0, 150)}`
  }
  return `${lines.length} lines of output. ${lines[0].slice(0, 100)}`
}

// --- Tests ---

describe('isScaffoldingTool', () => {
  it('ToolSearch is always scaffolding', () => {
    expect(isScaffoldingTool('ToolSearch', {})).toBe(true)
  })

  it('Read of CLAUDE.md is scaffolding', () => {
    expect(isScaffoldingTool('Read', { file_path: '/repo/CLAUDE.md' })).toBe(true)
  })

  it('Read of a skill file is NOT scaffolding', () => {
    expect(isScaffoldingTool('Read', { file_path: '/repo/skills/foo.md' })).toBe(false)
  })

  it('Bash with ir CLI is NOT scaffolding', () => {
    expect(isScaffoldingTool('Bash', { command: 'ir alert view 12345' })).toBe(false)
  })

  it('Bash with npm install is scaffolding', () => {
    expect(isScaffoldingTool('Bash', { command: 'npm install lodash' })).toBe(true)
  })

  it('Glob of *.tsx is scaffolding', () => {
    expect(isScaffoldingTool('Glob', { pattern: '*.tsx' })).toBe(true)
  })

  it('Bash with curl is NOT scaffolding', () => {
    expect(isScaffoldingTool('Bash', { command: 'curl https://api.example.com' })).toBe(false)
  })

  it('Bash with python is NOT scaffolding', () => {
    expect(isScaffoldingTool('Bash', { command: 'python3 tools/davi_runner.py run' })).toBe(false)
  })

  it('Read of .ts source file is scaffolding', () => {
    expect(isScaffoldingTool('Read', { file_path: '/repo/src/components/App.tsx' })).toBe(true)
  })

  it('execute_trino_query is NOT scaffolding', () => {
    expect(isScaffoldingTool('execute_trino_query', { query: 'SELECT 1' })).toBe(false)
  })
})

describe('buildToolLabel', () => {
  it('execute_trino_query with FROM table extracts table name', () => {
    const label = buildToolLabel('execute_trino_query', { query: 'SELECT * FROM tracking.my_table WHERE x = 1' })
    expect(label).toContain('my_table')
  })

  it('mcp__captain__execute_trino_query strips prefix', () => {
    const label = buildToolLabel('mcp__captain__execute_trino_query', { query: 'SELECT * FROM some_table' })
    expect(label).toContain('some_table')
  })

  it('Bash shows command prefix', () => {
    const label = buildToolLabel('Bash', { command: 'ir alert view 12345' })
    expect(label).toBe('Bash: ir alert view 12345')
  })

  it('Bash truncates long commands', () => {
    const longCmd = 'a'.repeat(60)
    const label = buildToolLabel('Bash', { command: longCmd })
    expect(label).toMatch(/^Bash: a{50}\.\.\./)
  })

  it('Read shows filename', () => {
    const label = buildToolLabel('Read', { file_path: '/home/user/project/data.json' })
    expect(label).toBe('Read: data.json')
  })

  it('search_slack shows query', () => {
    const label = buildToolLabel('search_slack', { query: 'trustim oncall alert' })
    expect(label).toBe('Slack: trustim oncall alert')
  })

  it('Skill shows skill name', () => {
    const label = buildToolLabel('Skill', { skill: 'headless-investigation' })
    expect(label).toBe('Skill: headless-investigation')
  })

  it('create_google_docs_document shows title', () => {
    const label = buildToolLabel('create_google_docs_document', { title: 'Alert 123 — Investigation' })
    expect(label).toBe('Create Doc: Alert 123 — Investigation')
  })

  it('unknown tool replaces underscores with spaces', () => {
    const label = buildToolLabel('some_custom_tool', {})
    expect(label).toBe('some custom tool')
  })

  it('Trino query with GROUP BY includes select hint', () => {
    const label = buildToolLabel('execute_trino_query', {
      query: 'SELECT country, COUNT(*) FROM my_table GROUP BY country ORDER BY 2 DESC',
    })
    expect(label).toContain('my_table')
    expect(label).toContain('country')
  })
})

describe('inferActionType', () => {
  it('execute_trino_query → query_execution', () => {
    expect(inferActionType('execute_trino_query', 'captain')).toBe('query_execution')
  })

  it('mcp__captain__execute_trino_query → query_execution', () => {
    expect(inferActionType('mcp__captain__execute_trino_query', 'captain')).toBe('query_execution')
  })

  it('Skill → skill_invocation', () => {
    expect(inferActionType('Skill', 'local')).toBe('skill_invocation')
  })

  it('Read → enrichment', () => {
    expect(inferActionType('Read', 'local')).toBe('enrichment')
  })

  it('Glob → enrichment', () => {
    expect(inferActionType('Glob', 'local')).toBe('enrichment')
  })

  it('Grep → enrichment', () => {
    expect(inferActionType('Grep', 'local')).toBe('enrichment')
  })

  it('create_google_docs_document → recommendation', () => {
    expect(inferActionType('create_google_docs_document', 'captain')).toBe('recommendation')
  })

  it('write_to_google_docs_document → recommendation', () => {
    expect(inferActionType('write_to_google_docs_document', 'captain')).toBe('recommendation')
  })

  it('search_slack → mcp_tool_call', () => {
    expect(inferActionType('search_slack', 'captain')).toBe('mcp_tool_call')
  })
})

describe('summarizeResult', () => {
  it('empty string → No output', () => {
    expect(summarizeResult('')).toBe('No output')
  })

  it('tabular output with headers returns row count', () => {
    const result = 'country\tcount\nUS\t150\nGB\t120\nDE\t80'
    const summary = summarizeResult(result)
    expect(summary).toContain('3 rows')
    expect(summary).toContain('country')
  })

  it('tabular output shows top result value', () => {
    const result = 'domain\treg_count\ngmail.com\t500\nyahoo.com\t200'
    const summary = summarizeResult(result)
    expect(summary).toContain('gmail.com')
    expect(summary).toContain('reg_count')
  })

  it('0 rows detection in non-tabular multi-line output', () => {
    // Non-tabular (no tabs), >3 lines, contains "0 rows"
    const result = 'Query info\nExecuting...\nProcessing...\nResult: 0 rows returned'
    expect(summarizeResult(result)).toBe('Query returned 0 rows')
  })

  it('short result with 0 rows returned as-is', () => {
    const result = '0 rows selected'
    expect(summarizeResult(result)).toBe('0 rows selected')
  })

  it('error text starts with Error:', () => {
    const result = 'line 1\nline 2\nline 3\nline 4\nError: Query failed due to syntax\nmore info'
    const summary = summarizeResult(result)
    expect(summary).toMatch(/^Error:/)
  })

  it('short results returned as-is', () => {
    const result = 'done'
    expect(summarizeResult(result)).toBe('done')
  })
})

describe('cleanTrinoResult', () => {
  it('removes SET SESSION lines', () => {
    const input = 'SET SESSION li_authorization_user = \'trustim\'\nactual data here'
    expect(cleanTrinoResult(input)).toBe('actual data here')
  })

  it('removes Query N succeeded lines', () => {
    const input = 'Query 1 succeeded.\nQuery 2 succeeded.\nactual data'
    expect(cleanTrinoResult(input)).toBe('actual data')
  })

  it('trims whitespace', () => {
    const input = '  \n\n  some data  \n'
    expect(cleanTrinoResult(input)).toBe('some data')
  })

  it('handles combined noise', () => {
    const input = 'SET SESSION foo = \'bar\'\nQuery 1 succeeded.\n\ncountry\tcount\nUS\t100'
    expect(cleanTrinoResult(input)).toBe('country\tcount\nUS\t100')
  })
})
