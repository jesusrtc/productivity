import type { InvestigationNode } from '../types'

export interface DetectedPattern {
  type: 'ip_clustering' | 'geo_concentration' | 'temporal_burst' | 'device_reuse' | 'domain_family' | 'high_volume_entity'
  description: string
  confidence: number
  evidence: string[]
  nodeIds: string[]
}

/**
 * Analyze investigation nodes to detect common abuse patterns.
 * Runs across all completed nodes and looks for cross-cutting signals.
 */
export function detectPatterns(nodes: Record<string, InvestigationNode>): DetectedPattern[] {
  const patterns: DetectedPattern[] = []
  const completed = Object.values(nodes).filter(n => n.status === 'completed' && n.result_raw)

  if (completed.length < 2) return patterns

  // Collect IPs across all nodes
  const ipMap = new Map<string, string[]>() // ip -> nodeIds
  const domainMap = new Map<string, string[]>() // domain -> nodeIds
  const countryMap = new Map<string, string[]>() // country -> nodeIds

  for (const node of completed) {
    const raw = node.result_raw || ''

    // IPs
    const ips = raw.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || []
    for (const ip of new Set(ips)) {
      if (!ipMap.has(ip)) ipMap.set(ip, [])
      ipMap.get(ip)!.push(node.node_id)
    }

    // Domains (from email domain analysis)
    const domains = raw.match(/\b[a-z0-9][-a-z0-9]*\.(xyz|icu|top|us|ru|cn|tk|ml|club|online|site)\b/gi) || []
    for (const d of new Set(domains)) {
      const key = d.toLowerCase()
      if (!domainMap.has(key)) domainMap.set(key, [])
      domainMap.get(key)!.push(node.node_id)
    }

    // Country codes (common in investigation results)
    const countries = raw.match(/\b(GBR|USA|IND|CHN|RUS|BRA|NGA|IDN|PAK|VNM|PHL|TUR|IRN|DEU|FRA)\b/g) || []
    for (const c of new Set(countries)) {
      if (!countryMap.has(c)) countryMap.set(c, [])
      countryMap.get(c)!.push(node.node_id)
    }
  }

  // Pattern: IP appearing across multiple investigation branches
  const crossBranchIps = [...ipMap.entries()]
    .filter(([, nodeIds]) => new Set(nodeIds).size >= 2)
    .slice(0, 5)

  if (crossBranchIps.length > 0) {
    patterns.push({
      type: 'ip_clustering',
      description: `${crossBranchIps.length} IP(s) found across multiple investigation steps`,
      confidence: Math.min(0.9, 0.5 + crossBranchIps.length * 0.1),
      evidence: crossBranchIps.map(([ip, nids]) => `${ip} (in ${new Set(nids).size} nodes)`),
      nodeIds: [...new Set(crossBranchIps.flatMap(([, nids]) => nids))],
    })
  }

  // Pattern: Disposable domain concentration
  if (domainMap.size >= 3) {
    // Group by TLD
    const tldCounts = new Map<string, number>()
    for (const domain of domainMap.keys()) {
      const tld = domain.split('.').pop() || ''
      tldCounts.set(tld, (tldCounts.get(tld) || 0) + 1)
    }
    const suspiciousTlds = [...tldCounts.entries()].filter(([, c]) => c >= 2)
    if (suspiciousTlds.length > 0) {
      patterns.push({
        type: 'domain_family',
        description: `Disposable domain clustering: ${domainMap.size} suspicious domains across ${suspiciousTlds.map(([t]) => `.${t}`).join(', ')} TLDs`,
        confidence: Math.min(0.85, 0.4 + domainMap.size * 0.05),
        evidence: [...domainMap.keys()].slice(0, 10),
        nodeIds: [...new Set([...domainMap.values()].flat())],
      })
    }
  }

  // Pattern: Geographic concentration
  const topCountry = [...countryMap.entries()].sort((a, b) => b[1].length - a[1].length)[0]
  if (topCountry && topCountry[1].length >= 3) {
    patterns.push({
      type: 'geo_concentration',
      description: `Geographic concentration: ${topCountry[0]} appears in ${topCountry[1].length} investigation steps`,
      confidence: 0.5,
      evidence: [`${topCountry[0]}: ${topCountry[1].length} nodes`],
      nodeIds: topCountry[1],
    })
  }

  // Pattern: High-volume entities (high counts in results)
  for (const node of completed) {
    const raw = node.result_raw || ''
    const countMatch = raw.match(/(\d{4,})\s*(registrations?|accounts?|members?|logins?|attempts|denials?)/i)
    if (countMatch && parseInt(countMatch[1]) > 500) {
      patterns.push({
        type: 'high_volume_entity',
        description: `High volume: ${countMatch[1]} ${countMatch[2]} detected in "${node.label}"`,
        confidence: Math.min(0.9, 0.5 + parseInt(countMatch[1]) / 10000),
        evidence: [`${countMatch[1]} ${countMatch[2]}`],
        nodeIds: [node.node_id],
      })
    }
  }

  // Pattern: Device reuse (SwiftShader, shared canvas hash)
  const deviceSignals = completed.filter(n => {
    const raw = (n.result_raw || '').toLowerCase()
    return raw.includes('swiftshader') || raw.includes('canvas_hash') || raw.includes('canvashash')
  })
  if (deviceSignals.length > 0) {
    patterns.push({
      type: 'device_reuse',
      description: `Device fingerprint reuse detected in ${deviceSignals.length} step(s) — possible automation`,
      confidence: 0.8,
      evidence: deviceSignals.map(n => n.label),
      nodeIds: deviceSignals.map(n => n.node_id),
    })
  }

  return patterns.sort((a, b) => b.confidence - a.confidence)
}
