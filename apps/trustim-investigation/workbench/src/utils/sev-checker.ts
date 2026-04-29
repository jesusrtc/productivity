/**
 * Automated SEV threshold checking based on the sev-assessment skill.
 * Parses WoW T7D percentages from investigation results and checks
 * them against the official TrustIM SEV thresholds.
 */

export interface SevAssessment {
  metric: string
  wowPct: number
  sevLevel: number | null // 1-4, or null if below all thresholds
  threshold: number | null
  raw: string // The matched text
}

/**
 * SEV thresholds from the sev-assessment skill (Table 1 + Table 2).
 * Format: [SEV1, SEV2, SEV3, SEV4] — each is a minimum WoW % for that SEV.
 */
const TRUE_NORTH_THRESHOLDS: Record<string, [number, number, number, number]> = {
  'prevalence': [40, 25, 20, 15],
  'ato self report': [40, 25, 20, 15],
  'ato member report': [40, 25, 20, 15],
  'fa member report': [35, 20, 15, 10],
  'private content report': [35, 20, 15, 10],
  'public content report': [35, 20, 15, 10],
}

// Generic fallback for metrics not in the table
const DEFAULT_THRESHOLDS: [number, number, number, number] = [40, 25, 15, 10]

/**
 * Parse WoW percentages from result text and check against SEV thresholds.
 * Returns all detected SEV assessments sorted by severity.
 */
export function checkSevThresholds(resultRaw: string, nodeLabel: string): SevAssessment[] {
  if (!resultRaw) return []
  const assessments: SevAssessment[] = []

  // Match patterns like "wow_pct: 25.3" or "WoW: +32%" or "T7D WoW >25%"
  const wowPatterns = [
    /wow[_\s]*pct[:\s]*([+-]?\d+(?:\.\d+)?)/gi,
    /wow[:\s]*([+-]?\d+(?:\.\d+))%/gi,
    /t7d[_\s]*wow[:\s]*([+-]?\d+(?:\.\d+))%/gi,
    /week[- ]over[- ]week[:\s]*([+-]?\d+(?:\.\d+))%/gi,
  ]

  const seenPcts = new Set<number>()

  for (const pattern of wowPatterns) {
    let match
    while ((match = pattern.exec(resultRaw)) !== null) {
      const pct = Math.abs(parseFloat(match[1]))
      if (seenPcts.has(pct) || pct === 0 || pct > 500) continue // Skip duplicates and unreasonable values
      seenPcts.add(pct)

      // Determine which metric this is based on context
      const metric = detectMetric(resultRaw, nodeLabel, match.index)
      const thresholds = getThresholds(metric)
      const sevLevel = computeSev(pct, thresholds)

      assessments.push({
        metric,
        wowPct: pct,
        sevLevel,
        threshold: sevLevel ? thresholds[sevLevel - 1] : null,
        raw: match[0],
      })
    }
  }

  // Also check for explicit WoW values in tabular data (common in Trino results)
  const tabularWow = resultRaw.match(/(\d{4}-\d{2}-\d{2}).*?([+-]?\d{2,3}\.\d)$/gm)
  if (tabularWow) {
    for (const line of tabularWow.slice(-3)) { // Only check last 3 rows (most recent)
      const numMatch = line.match(/([+-]?\d{2,3}\.\d)\s*$/)
      if (numMatch) {
        const pct = Math.abs(parseFloat(numMatch[1]))
        if (!seenPcts.has(pct) && pct > 5 && pct < 500) {
          seenPcts.add(pct)
          const metric = detectMetric(resultRaw, nodeLabel, 0)
          const thresholds = getThresholds(metric)
          const sevLevel = computeSev(pct, thresholds)
          assessments.push({
            metric,
            wowPct: pct,
            sevLevel,
            threshold: sevLevel ? thresholds[sevLevel - 1] : null,
            raw: line.trim().slice(0, 60),
          })
        }
      }
    }
  }

  return assessments.sort((a, b) => (a.sevLevel || 5) - (b.sevLevel || 5))
}

function detectMetric(text: string, label: string, _matchIdx: number): string {
  const combined = (text + ' ' + label).toLowerCase()
  if (combined.includes('ato') && combined.includes('self')) return 'ato self report'
  if (combined.includes('ato') && combined.includes('member')) return 'ato member report'
  if (combined.includes('fake') || combined.includes('fa member')) return 'fa member report'
  if (combined.includes('prevalence')) return 'prevalence'
  if (combined.includes('private content')) return 'private content report'
  if (combined.includes('public content')) return 'public content report'
  return 'unknown metric'
}

function getThresholds(metric: string): [number, number, number, number] {
  return TRUE_NORTH_THRESHOLDS[metric] || DEFAULT_THRESHOLDS
}

function computeSev(pct: number, thresholds: [number, number, number, number]): number | null {
  if (pct >= thresholds[0]) return 1
  if (pct >= thresholds[1]) return 2
  if (pct >= thresholds[2]) return 3
  if (pct >= thresholds[3]) return 4
  return null
}

/**
 * Format a SEV assessment as a human-readable string.
 */
export function formatSevAssessment(assessment: SevAssessment): string {
  if (assessment.sevLevel) {
    return `SEV-${assessment.sevLevel}: ${assessment.metric} WoW +${assessment.wowPct.toFixed(1)}% (threshold: >${assessment.threshold}%)`
  }
  return `No SEV: ${assessment.metric} WoW +${assessment.wowPct.toFixed(1)}% (below SEV-4 threshold)`
}
