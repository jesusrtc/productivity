/**
 * Lightweight SQL syntax highlighting for notebook cells.
 * Returns HTML with colored spans for keywords, strings, numbers, and comments.
 */

const SQL_KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'AS', 'ON',
  'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'CROSS', 'FULL',
  'GROUP', 'BY', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET',
  'WITH', 'UNION', 'ALL', 'DISTINCT', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
  'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE',
  'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ROUND', 'NULLIF', 'COALESCE',
  'LIKE', 'BETWEEN', 'EXISTS', 'IS', 'NULL', 'TRUE', 'FALSE',
  'ASC', 'DESC', 'OVER', 'PARTITION', 'ROWS', 'PRECEDING', 'CURRENT', 'ROW',
  'LAG', 'LEAD', 'RANK', 'ROW_NUMBER', 'APPROX_PERCENTILE',
  'SESSION', 'CREATE', 'TABLE', 'DROP', 'ALTER',
  'CAST', 'SUBSTRING', 'TRIM', 'LOWER', 'UPPER', 'CONCAT',
  'DATE', 'TIMESTAMP', 'INTERVAL',
])

const FUNCTIONS = new Set([
  'split_part', 'element_at', 'contains', 'daysago', 'daysAgo',
  'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ROUND', 'NULLIF',
  'APPROX_PERCENTILE', 'LAG', 'LEAD', 'ROW_NUMBER', 'RANK',
])

export function highlightSQL(sql: string): string {
  // Escape HTML first
  const escaped = sql
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Tokenize: split into comments, strings, and code segments to avoid
  // regex replacements corrupting HTML inside already-wrapped spans.
  const tokens: { type: 'comment' | 'string' | 'code'; text: string }[] = []
  let remaining = escaped
  while (remaining.length > 0) {
    // Check for comment
    const commentIdx = remaining.indexOf('--')
    // Check for string
    const stringIdx = remaining.indexOf("'")
    const firstSpecial = Math.min(
      commentIdx >= 0 ? commentIdx : Infinity,
      stringIdx >= 0 ? stringIdx : Infinity,
    )
    if (firstSpecial === Infinity) {
      tokens.push({ type: 'code', text: remaining })
      break
    }
    // Push code before the special token
    if (firstSpecial > 0) {
      tokens.push({ type: 'code', text: remaining.slice(0, firstSpecial) })
    }
    if (firstSpecial === commentIdx) {
      const eol = remaining.indexOf('\n', commentIdx)
      const end = eol >= 0 ? eol : remaining.length
      tokens.push({ type: 'comment', text: remaining.slice(commentIdx, end) })
      remaining = remaining.slice(end)
    } else {
      const closeQuote = remaining.indexOf("'", stringIdx + 1)
      const end = closeQuote >= 0 ? closeQuote + 1 : remaining.length
      tokens.push({ type: 'string', text: remaining.slice(stringIdx, end) })
      remaining = remaining.slice(end)
    }
    continue
  }

  // Escape HTML in token text before wrapping in spans
  const e = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  // Highlight each token type independently
  return tokens.map(t => {
    if (t.type === 'comment') return '<span style="color:#6b7280;font-style:italic">' + e(t.text) + '</span>'
    if (t.type === 'string') return '<span style="color:#f59e0b">' + e(t.text) + '</span>'
    // Code: highlight keywords, functions, numbers
    return e(t.text)
      .replace(/\b(\d+(?:\.\d+)?)\b/g, '<span style="color:#06b6d4">$1</span>')
      .replace(/\b([A-Za-z_]+)\b/g, (m) => {
        if (SQL_KEYWORDS.has(m.toUpperCase())) return '<span style="color:#818cf8;font-weight:600">' + m + '</span>'
        if (FUNCTIONS.has(m)) return '<span style="color:#34d399">' + m + '</span>'
        return m
      })
  }).join('')
}
