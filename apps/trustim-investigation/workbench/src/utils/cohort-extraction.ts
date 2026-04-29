/**
 * Cohort Extraction — Parses investigation results to extract actionable entities
 * (member IDs, IPs, domains, device hashes) that can be used in follow-up queries.
 */

export interface ExtractedCohort {
  memberIds: string[]
  ips: string[]
  domains: string[]
  deviceHashes: string[]
  emails: string[]
}

/**
 * Extract cohort entities from node result text.
 * Filters out common false positives (dates, small numbers, known safe domains).
 */
export function extractCohort(resultRaw: string): ExtractedCohort {
  if (!resultRaw) return { memberIds: [], ips: [], domains: [], deviceHashes: [], emails: [] }

  const memberIds = new Set<string>()
  const ips = new Set<string>()
  const domains = new Set<string>()
  const deviceHashes = new Set<string>()
  const emails = new Set<string>()

  // Member IDs: 7-12 digit numbers that don't look like dates or counts
  const midMatches = resultRaw.match(/\b\d{7,12}\b/g) || []
  for (const mid of midMatches) {
    // Skip dates (2024..., 2025..., 2026...), small counts, and hex-like
    if (/^20[2-3]\d/.test(mid)) continue
    if (parseInt(mid) < 1000000) continue
    memberIds.add(mid)
  }

  // IPs: standard IPv4
  const ipMatches = resultRaw.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || []
  for (const ip of ipMatches) {
    // Skip loopback and broadcast
    if (ip === '0.0.0.0' || ip === '127.0.0.1' || ip === '255.255.255.255') continue
    ips.add(ip)
  }

  // Email domains (from split_part results or @domain patterns)
  const domainMatches = resultRaw.match(/\b[a-z0-9][-a-z0-9]*\.[a-z]{2,10}\b/gi) || []
  const safeDomains = new Set(['linkedin.com', 'google.com', 'github.com', 'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'apple.com', 'microsoft.com'])
  for (const d of domainMatches) {
    const lower = d.toLowerCase()
    if (safeDomains.has(lower)) continue
    if (lower.length < 5) continue // Skip very short
    domains.add(lower)
  }

  // Device hashes (canvas hash, bcookie, 0x prefixed)
  const hashMatches = resultRaw.match(/0x[a-f0-9]{6,}/gi) || []
  for (const h of hashMatches) {
    deviceHashes.add(h)
  }

  // Full emails
  const emailMatches = resultRaw.match(/\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b/g) || []
  for (const e of emailMatches) {
    emails.add(e.toLowerCase())
  }

  return {
    memberIds: [...memberIds].slice(0, 100),
    ips: [...ips].slice(0, 50),
    domains: [...domains].slice(0, 50),
    deviceHashes: [...deviceHashes].slice(0, 20),
    emails: [...emails].slice(0, 50),
  }
}

/** Format a cohort as a comma-separated SQL-safe string for use in IN clauses */
export function formatCohortForSQL(items: string[], type: 'number' | 'string' = 'string'): string {
  if (items.length === 0) return ''
  if (type === 'number') return items.join(', ')
  return items.map(i => `'${i}'`).join(', ')
}

/** Generate follow-up query suggestions based on extracted cohort */
export function suggestCohortQueries(cohort: ExtractedCohort): { label: string; prompt: string }[] {
  const suggestions: { label: string; prompt: string }[] = []

  if (cohort.memberIds.length > 0) {
    const mids = cohort.memberIds.slice(0, 10).join(', ')
    suggestions.push({
      label: `Check restrictions for ${cohort.memberIds.length} members`,
      prompt: `Check restriction status for member IDs: ${mids}${cohort.memberIds.length > 10 ? ` (+${cohort.memberIds.length - 10} more)` : ''}`,
    })
    suggestions.push({
      label: `Profile completion for cohort`,
      prompt: `Analyze profile completion and activity for member IDs: ${mids}`,
    })
  }

  if (cohort.ips.length > 0) {
    const topIps = cohort.ips.slice(0, 5).join(', ')
    suggestions.push({
      label: `IP org lookup for ${cohort.ips.length} IPs`,
      prompt: `Look up ASN and organization for IPs: ${topIps}. Are these datacenter, residential, or VPN?`,
    })
  }

  if (cohort.domains.length > 0) {
    suggestions.push({
      label: `Domain risk for ${cohort.domains.length} domains`,
      prompt: `Check email domain risk for: ${cohort.domains.slice(0, 10).join(', ')}. Are these disposable email providers?`,
    })
  }

  if (cohort.deviceHashes.length > 0) {
    suggestions.push({
      label: `Device hash fanout`,
      prompt: `Check how many accounts share these device hashes: ${cohort.deviceHashes.slice(0, 5).join(', ')}`,
    })
  }

  return suggestions
}
