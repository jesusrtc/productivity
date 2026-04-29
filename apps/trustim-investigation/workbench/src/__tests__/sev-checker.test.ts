/**
 * Tests for checkSevThresholds and formatSevAssessment from sev-checker.ts.
 * Parses WoW T7D percentages and checks against SEV thresholds.
 */
import { describe, it, expect } from 'vitest'
import { checkSevThresholds, formatSevAssessment, type SevAssessment } from '../utils/sev-checker'

describe('checkSevThresholds', () => {
  it('detects "wow_pct: 25.3" pattern', () => {
    const result = checkSevThresholds('wow_pct: 25.3', 'prevalence check')
    expect(result).toHaveLength(1)
    expect(result[0].wowPct).toBe(25.3)
  })

  it('prevalence at 41% → SEV-1', () => {
    const result = checkSevThresholds('wow_pct: 41.0', 'prevalence analysis')
    expect(result).toHaveLength(1)
    expect(result[0].sevLevel).toBe(1)
    expect(result[0].metric).toBe('prevalence')
    expect(result[0].threshold).toBe(40)
  })

  it('prevalence at 26% → SEV-2', () => {
    const result = checkSevThresholds('wow_pct: 26.0', 'prevalence analysis')
    expect(result).toHaveLength(1)
    expect(result[0].sevLevel).toBe(2)
    expect(result[0].threshold).toBe(25)
  })

  it('prevalence at 21% → SEV-3', () => {
    const result = checkSevThresholds('wow_pct: 21.0', 'prevalence analysis')
    expect(result).toHaveLength(1)
    expect(result[0].sevLevel).toBe(3)
    expect(result[0].threshold).toBe(20)
  })

  it('prevalence at 16% → SEV-4', () => {
    const result = checkSevThresholds('wow_pct: 16.0', 'prevalence analysis')
    expect(result).toHaveLength(1)
    expect(result[0].sevLevel).toBe(4)
    expect(result[0].threshold).toBe(15)
  })

  it('prevalence at 5% → null (below all thresholds)', () => {
    const result = checkSevThresholds('wow_pct: 5.0', 'prevalence analysis')
    expect(result).toHaveLength(1)
    expect(result[0].sevLevel).toBeNull()
    expect(result[0].threshold).toBeNull()
  })

  it('detects "WoW: +32%" pattern', () => {
    const result = checkSevThresholds('WoW: +32.0%', 'ato self report check')
    expect(result).toHaveLength(1)
    expect(result[0].wowPct).toBe(32)
    expect(result[0].sevLevel).toBe(2)
  })

  it('detects "T7D WoW: +45%" pattern', () => {
    const result = checkSevThresholds('T7D WoW: +45.0%', 'prevalence check')
    expect(result).toHaveLength(1)
    expect(result[0].wowPct).toBe(45)
    expect(result[0].sevLevel).toBe(1)
  })

  it('returns empty array for empty input', () => {
    expect(checkSevThresholds('', 'test')).toEqual([])
  })

  it('returns empty array for null-like input', () => {
    expect(checkSevThresholds(undefined as unknown as string, 'test')).toEqual([])
  })

  it('detects multiple WoW values and deduplicates', () => {
    const text = 'wow_pct: 25.3\nWoW: +25.3%'
    const result = checkSevThresholds(text, 'prevalence')
    // Same pct value should be deduplicated
    expect(result).toHaveLength(1)
    expect(result[0].wowPct).toBe(25.3)
  })

  it('detects multiple distinct WoW values', () => {
    const text = 'wow_pct: 25.3\nwow_pct: 42.0'
    const result = checkSevThresholds(text, 'prevalence')
    expect(result.length).toBeGreaterThanOrEqual(2)
    const pcts = result.map(a => a.wowPct)
    expect(pcts).toContain(25.3)
    expect(pcts).toContain(42)
  })

  it('sorts results by severity (SEV-1 first)', () => {
    const text = 'wow_pct: 16.0\nwow_pct: 42.0'
    const result = checkSevThresholds(text, 'prevalence')
    expect(result.length).toBeGreaterThanOrEqual(2)
    // SEV-1 (42%) should come before SEV-4 (16%)
    expect(result[0].sevLevel).toBe(1)
  })

  it('skips unreasonable values > 500', () => {
    const result = checkSevThresholds('wow_pct: 600.0', 'test')
    expect(result).toHaveLength(0)
  })

  it('skips zero values', () => {
    const result = checkSevThresholds('wow_pct: 0.0', 'test')
    expect(result).toHaveLength(0)
  })

  it('uses absolute value of negative percentages', () => {
    const result = checkSevThresholds('wow_pct: -30.0', 'prevalence')
    expect(result).toHaveLength(1)
    expect(result[0].wowPct).toBe(30)
    expect(result[0].sevLevel).toBe(2)
  })

  it('detects ATO self report metric', () => {
    const result = checkSevThresholds('wow_pct: 30.0', 'ATO self report WoW')
    expect(result[0].metric).toBe('ato self report')
  })

  it('detects ATO member report metric', () => {
    const result = checkSevThresholds('wow_pct: 30.0', 'ATO member report')
    expect(result[0].metric).toBe('ato member report')
  })

  it('detects FA member report metric', () => {
    const result = checkSevThresholds('wow_pct: 30.0', 'fake account member report')
    expect(result[0].metric).toBe('fa member report')
  })

  it('uses default thresholds for unknown metrics', () => {
    const result = checkSevThresholds('wow_pct: 30.0', 'some random metric')
    expect(result[0].metric).toBe('unknown metric')
    // Default thresholds: [40, 25, 15, 10] → 30% is SEV-2 (≥25)
    expect(result[0].sevLevel).toBe(2)
  })

  it('uses fa member report thresholds (lower than default)', () => {
    // FA member report: [35, 20, 15, 10]
    const result = checkSevThresholds('wow_pct: 22.0', 'fa member report analysis')
    expect(result[0].sevLevel).toBe(2) // 22 ≥ 20 → SEV-2
  })

  it('handles text with no WoW patterns', () => {
    const result = checkSevThresholds('SELECT * FROM table WHERE date > 2025-01-01', 'query')
    expect(result).toEqual([])
  })

  it('handles tabular data with date + percentage', () => {
    const text = '2026-03-01  some data  +35.2'
    const result = checkSevThresholds(text, 'prevalence')
    // Should detect tabular WoW pattern
    expect(result.length).toBeGreaterThanOrEqual(1)
    const pcts = result.map(a => a.wowPct)
    expect(pcts).toContain(35.2)
  })

  it('detects week-over-week pattern', () => {
    const result = checkSevThresholds('week-over-week: +28.5%', 'prevalence')
    expect(result).toHaveLength(1)
    expect(result[0].wowPct).toBe(28.5)
  })
})

describe('formatSevAssessment', () => {
  it('produces readable string with SEV level', () => {
    const assessment: SevAssessment = {
      metric: 'prevalence',
      wowPct: 42.5,
      sevLevel: 1,
      threshold: 40,
      raw: 'wow_pct: 42.5',
    }
    const formatted = formatSevAssessment(assessment)
    expect(formatted).toContain('SEV-1')
    expect(formatted).toContain('prevalence')
    expect(formatted).toContain('42.5')
    expect(formatted).toContain('>40%')
  })

  it('handles null SEV (below thresholds)', () => {
    const assessment: SevAssessment = {
      metric: 'prevalence',
      wowPct: 5.0,
      sevLevel: null,
      threshold: null,
      raw: 'wow_pct: 5.0',
    }
    const formatted = formatSevAssessment(assessment)
    expect(formatted).toContain('No SEV')
    expect(formatted).toContain('prevalence')
    expect(formatted).toContain('5.0')
    expect(formatted).toContain('below SEV-4')
  })

  it('formats different SEV levels correctly', () => {
    const sev3: SevAssessment = {
      metric: 'ato self report',
      wowPct: 21.0,
      sevLevel: 3,
      threshold: 20,
      raw: 'wow_pct: 21.0',
    }
    const formatted = formatSevAssessment(sev3)
    expect(formatted).toBe('SEV-3: ato self report WoW +21.0% (threshold: >20%)')
  })
})
