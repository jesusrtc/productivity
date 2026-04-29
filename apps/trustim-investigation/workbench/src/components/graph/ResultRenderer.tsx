import { useState, useMemo } from 'react'

interface Props {
  raw: string
  summary?: string
}

/**
 * Structured result rendering (R19).
 * Detects result format and renders appropriately:
 * - Tables for TSV/CSV data
 * - Collapsible JSON tree for JSON responses
 * - Formatted text for natural language
 */
export function ResultRenderer({ raw, summary }: Props) {
  if (!raw) {
    return <p className="text-xs text-gray-500 italic">No results</p>
  }

  const detected = useMemo(() => detectFormat(raw), [raw])

  return (
    <div>
      {summary && <p className="text-sm text-gray-300 mb-2">{summary}</p>}
      {detected.type === 'json' ? (
        <JsonTree data={detected.parsed} />
      ) : detected.type === 'table' ? (
        <DataTable headers={detected.headers} rows={detected.rows} />
      ) : (
        <pre className="bg-surface-0 rounded-lg p-3 text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap font-mono border border-surface-3 max-h-[300px] overflow-y-auto">
          {raw}
        </pre>
      )}
    </div>
  )
}

// ----- Format Detection -----

type DetectedFormat =
  | { type: 'json'; parsed: unknown }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'text' }

function detectFormat(raw: string): DetectedFormat {
  const trimmed = raw.trim()

  // Try JSON
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed)
      return { type: 'json', parsed }
    } catch {
      // Not valid JSON, continue
    }
  }

  // Try TSV/CSV table (at least 2 rows with consistent delimiters)
  // Strip Trino row count footer like "(15 rows)" or "15 rows"
  const cleaned = trimmed.replace(/\n\s*\(?\d+ rows?\)?\s*$/, '')
  const lines = cleaned.split('\n').filter((l) => l.trim())
  if (lines.length >= 2) {
    const tabCounts = lines.map((l) => (l.match(/\t/g) || []).length)
    const pipeCounts = lines.map((l) => (l.match(/\|/g) || []).length)
    const commaCounts = lines.map((l) => (l.match(/,/g) || []).length)

    // Check for consistent tab-separated
    if (tabCounts[0] >= 1 && tabCounts.every((c) => c === tabCounts[0])) {
      const headers = lines[0].split('\t').map((h) => h.trim())
      const rows = lines.slice(1).map((l) => l.split('\t').map((c) => c.trim()))
      return { type: 'table', headers, rows }
    }

    // Check for pipe-separated (markdown tables)
    if (pipeCounts[0] >= 2 && pipeCounts.every((c) => Math.abs(c - pipeCounts[0]) <= 1)) {
      const parseRow = (l: string) =>
        l.split('|').map((c) => c.trim()).filter((c) => c && !c.match(/^[-:]+$/))
      const headers = parseRow(lines[0])
      // Skip separator line if present
      const startRow = lines[1]?.match(/^[\s|:-]+$/) ? 2 : 1
      const rows = lines.slice(startRow).map(parseRow).filter((r) => r.length > 0)
      if (headers.length >= 2 && rows.length >= 1) {
        return { type: 'table', headers, rows }
      }
    }

    // Check for Trino CLI format with dashes separator line
    if (lines.length >= 3 && lines[1]?.match(/^[-+|]+$/)) {
      const parseRow = (l: string) =>
        l.split('|').map((c) => c.trim()).filter(Boolean)
      const headers = parseRow(lines[0])
      const rows = lines.slice(2).map(parseRow).filter((r) => r.length > 0 && !r[0].match(/^\d+ rows?$/))
      if (headers.length >= 2 && rows.length >= 1) {
        return { type: 'table', headers, rows }
      }
    }

    // Check for consistent comma-separated (but not prose with commas)
    if (commaCounts[0] >= 2 && commaCounts.every((c) => c === commaCounts[0]) && lines.length >= 3) {
      const headers = lines[0].split(',').map((h) => h.trim().replace(/^"|"$/g, ''))
      const rows = lines.slice(1).map((l) =>
        l.split(',').map((c) => c.trim().replace(/^"|"$/g, ''))
      )
      return { type: 'table', headers, rows }
    }
  }

  return { type: 'text' }
}

// ----- Data Table Component -----

function DataTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortAsc, setSortAsc] = useState(true)
  const [filter, setFilter] = useState('')

  const filteredRows = useMemo(() => {
    let result = rows
    if (filter) {
      const lower = filter.toLowerCase()
      result = result.filter((row) => row.some((cell) => cell.toLowerCase().includes(lower)))
    }
    if (sortCol !== null) {
      result = [...result].sort((a, b) => {
        const va = a[sortCol] || ''
        const vb = b[sortCol] || ''
        // Try numeric sort
        const na = parseFloat(va)
        const nb = parseFloat(vb)
        if (!isNaN(na) && !isNaN(nb)) {
          return sortAsc ? na - nb : nb - na
        }
        return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va)
      })
    }
    return result
  }, [rows, sortCol, sortAsc, filter])

  const handleSort = (colIdx: number) => {
    if (sortCol === colIdx) {
      setSortAsc(!sortAsc)
    } else {
      setSortCol(colIdx)
      setSortAsc(true)
    }
  }

  return (
    <div className="bg-surface-0 rounded-lg border border-surface-3 overflow-hidden">
      {/* Filter input */}
      <div className="px-2 py-1 border-b border-surface-3">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter rows..."
          className="w-full bg-transparent text-[10px] text-gray-300 placeholder-gray-500 focus:outline-none"
        />
      </div>
      {/* Table */}
      <div className="overflow-auto max-h-[280px]">
        <table className="w-full text-xs">
          <thead className="bg-surface-2 sticky top-0">
            <tr>
              {headers.map((h, i) => (
                <th
                  key={i}
                  onClick={() => handleSort(i)}
                  className="px-2 py-1.5 text-left text-gray-400 font-medium cursor-pointer hover:text-gray-200 whitespace-nowrap"
                >
                  {h}
                  {sortCol === i && (
                    <span className="ml-1 text-accent-blue">{sortAsc ? '\u2191' : '\u2193'}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-3">
            {filteredRows.map((row, ri) => (
              <tr key={ri} className="hover:bg-surface-2/50">
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    className="px-2 py-1 text-gray-300 whitespace-nowrap max-w-[200px] truncate cursor-pointer hover:bg-accent-blue/10 transition-colors"
                    title={`${cell}\n(click: copy | double-click: investigate)`}
                    onClick={() => navigator.clipboard.writeText(cell)}
                    onDoubleClick={(e) => {
                      e.stopPropagation()
                      // Dispatch event to investigate this value
                      window.dispatchEvent(new CustomEvent('investigateValue', {
                        detail: { value: cell, column: headers[ci] || '' }
                      }))
                    }}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-2 py-1 border-t border-surface-3 text-[10px] text-gray-500">
        {filteredRows.length} of {rows.length} rows
      </div>
    </div>
  )
}

// ----- JSON Tree Component -----

function JsonTree({ data }: { data: unknown }) {
  return (
    <div className="bg-surface-0 rounded-lg border border-surface-3 p-3 max-h-[300px] overflow-auto">
      <JsonNode value={data} depth={0} path="" />
    </div>
  )
}

function JsonNode({ value, depth, path }: { value: unknown; depth: number; path: string }) {
  const [collapsed, setCollapsed] = useState(depth > 2)

  if (value === null) return <span className="text-gray-500 text-xs">null</span>
  if (typeof value === 'boolean') return <span className="text-accent-cyan text-xs">{String(value)}</span>
  if (typeof value === 'number') return <span className="text-yellow-400 text-xs">{value}</span>
  if (typeof value === 'string') {
    if (value.length > 100) {
      return <span className="text-green-400 text-xs">"{value.slice(0, 100)}..."</span>
    }
    return <span className="text-green-400 text-xs">"{value}"</span>
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-gray-500 text-xs">[]</span>
    return (
      <span className="text-xs">
        <button onClick={() => setCollapsed(!collapsed)} className="text-gray-400 hover:text-gray-200">
          {collapsed ? '\u25B6' : '\u25BC'} [{value.length}]
        </button>
        {!collapsed && (
          <div className="ml-3 border-l border-surface-4 pl-2">
            {value.map((item, i) => (
              <div key={i}>
                <span className="text-gray-500">{i}: </span>
                <JsonNode value={item} depth={depth + 1} path={`${path}[${i}]`} />
              </div>
            ))}
          </div>
        )}
      </span>
    )
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) return <span className="text-gray-500 text-xs">{'{}'}</span>
    return (
      <span className="text-xs">
        <button onClick={() => setCollapsed(!collapsed)} className="text-gray-400 hover:text-gray-200">
          {collapsed ? '\u25B6' : '\u25BC'} {'{'}
          {collapsed && <span className="text-gray-500">{entries.length} keys</span>}
          {collapsed && '}'}
        </button>
        {!collapsed && (
          <div className="ml-3 border-l border-surface-4 pl-2">
            {entries.map(([key, val]) => (
              <div key={key}>
                <span className="text-accent-purple">{key}</span>
                <span className="text-gray-500">: </span>
                <JsonNode value={val} depth={depth + 1} path={`${path}.${key}`} />
              </div>
            ))}
          </div>
        )}
        {!collapsed && <span>{'}'}</span>}
      </span>
    )
  }

  return <span className="text-gray-400 text-xs">{String(value)}</span>
}
