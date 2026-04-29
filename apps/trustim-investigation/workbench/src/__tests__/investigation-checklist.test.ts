/**
 * Tests for getUncoveredDimensions from investigation-checklist.ts.
 * Checks which investigation dimensions haven't been covered by existing nodes.
 */
import { describe, it, expect } from 'vitest'
import { getUncoveredDimensions } from '../utils/investigation-checklist'

// Must match labels from data/investigation-dimensions.ts
const ALL_DIMENSIONS = [
  'email domains',
  'IP analysis',
  'device fingerprints',
  'challenge rates',
  'restrictions',
  'WoW metrics',
  'DIHE impact',
  'SEV assessment',
]

describe('getUncoveredDimensions', () => {
  it('returns all 8 dimensions for empty nodes', () => {
    expect(getUncoveredDimensions({})).toEqual(ALL_DIMENSIONS)
  })

  it('marks email domains as covered when query contains split_part', () => {
    const nodes = {
      n1: { label: 'Email analysis', query: "SELECT split_part(email, '@', 2) FROM ...", tags: [] },
    }
    const uncovered = getUncoveredDimensions(nodes)
    expect(uncovered).not.toContain('email domains')
    expect(uncovered).toHaveLength(7)
  })

  it('marks IP analysis as covered when query contains requestheader__ip', () => {
    const nodes = {
      n1: { label: 'IP breakdown', query: 'SELECT requestheader__ip, COUNT(*) FROM ...', tags: [] },
    }
    const uncovered = getUncoveredDimensions(nodes)
    expect(uncovered).not.toContain('IP analysis')
    expect(uncovered).toHaveLength(7)
  })

  it('returns empty array when all 8 dimensions are covered', () => {
    const nodes: Record<string, { label: string; query: string; tags: string[] }> = {
      n1: { label: 'Email analysis', query: "split_part(email, '@', 2)", tags: [] },
      n2: { label: 'IP breakdown', query: 'requestheader__ip', tags: [] },
      n3: { label: 'Device check', query: 'canvashash distribution', tags: [] },
      n4: { label: 'Challenge rates', query: 'captcha challenge events', tags: [] },
      n5: { label: 'Restrictions', query: 'dim_member_trust restriction', tags: [] },
      n6: { label: 'WoW analysis', query: 't7d wow_pct metrics', tags: [] },
      n7: { label: 'Impact', query: 'fact_experience impact', tags: [] },
      n8: { label: 'SEV check', query: '', tags: ['sev-1'] },
    }
    expect(getUncoveredDimensions(nodes)).toEqual([])
  })

  it('returns 5 uncovered when 3 of 8 are covered', () => {
    const nodes = {
      n1: { label: 'Email', query: "split_part(email, '@', 2)", tags: [] },
      n2: { label: 'IP', query: 'requestheader__ip counts', tags: [] },
      n3: { label: 'Fingerprints', query: 'canvashash webglrenderer', tags: [] },
    }
    const uncovered = getUncoveredDimensions(nodes)
    expect(uncovered).toHaveLength(5)
    expect(uncovered).not.toContain('email domains')
    expect(uncovered).not.toContain('IP analysis')
    expect(uncovered).not.toContain('device fingerprints')
    expect(uncovered).toContain('challenge rates')
    expect(uncovered).toContain('restrictions')
    expect(uncovered).toContain('WoW metrics')
    expect(uncovered).toContain('DIHE impact')
    expect(uncovered).toContain('SEV assessment')
  })

  it('matches keywords in tags as well as query and label', () => {
    const nodes = {
      n1: { label: 'Check', query: '', tags: ['sev-2', 'impact'] },
    }
    const uncovered = getUncoveredDimensions(nodes)
    expect(uncovered).not.toContain('SEV assessment')
    expect(uncovered).not.toContain('DIHE impact')
  })

  it('handles nodes with missing tags gracefully', () => {
    const nodes = {
      n1: { label: 'IP check', query: 'asn lookup', tags: undefined as unknown as string[] },
    }
    const uncovered = getUncoveredDimensions(nodes)
    expect(uncovered).not.toContain('IP analysis')
  })
})
