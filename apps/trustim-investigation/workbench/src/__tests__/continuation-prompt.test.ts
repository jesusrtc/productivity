/**
 * Tests for buildContinuationPrompt from continuation-prompt.ts.
 * Builds context-aware continuation prompts for auto-investigate.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the graph store before importing the module under test
vi.mock('../store/graph', () => ({
  useGraphStore: {
    getState: vi.fn(() => ({ nodes: {} })),
  },
}))

// Mock cohort extraction to isolate prompt logic
vi.mock('../utils/cohort-extraction', () => ({
  extractCohort: vi.fn(() => ({
    memberIds: [],
    ips: [],
    domains: [],
    deviceHashes: [],
    emails: [],
  })),
  formatCohortForSQL: vi.fn((items: string[], _type: string) => items.join(', ')),
}))

import { buildContinuationPrompt } from '../utils/continuation-prompt'
import { useGraphStore } from '../store/graph'
import { extractCohort } from '../utils/cohort-extraction'

const makeParent = (overrides: Partial<Parameters<typeof buildContinuationPrompt>[0]> = {}) => ({
  label: 'Email domain analysis',
  query: "SELECT split_part(email, '@', 2) FROM tracking.registrationevent",
  result_summary: '527 registrations from ghksc.us domain',
  result_raw: 'ghksc.us: 527\nexample.xyz: 312',
  confidence: 0.45,
  action_type: 'trino_query',
  tags: ['email_domain'],
  ...overrides,
})

describe('buildContinuationPrompt', () => {
  beforeEach(() => {
    vi.mocked(useGraphStore.getState).mockReturnValue({ nodes: {} } as ReturnType<typeof useGraphStore.getState>)
    vi.mocked(extractCohort).mockReturnValue({
      memberIds: [],
      ips: [],
      domains: [],
      deviceHashes: [],
      emails: [],
    })
  })

  it('includes parent findings text', () => {
    const prompt = buildContinuationPrompt(makeParent())
    expect(prompt).toContain('527 registrations from ghksc.us domain')
    expect(prompt).toContain('Email domain analysis')
  })

  it('includes confidence percentage', () => {
    const prompt = buildContinuationPrompt(makeParent({ confidence: 0.45 }))
    expect(prompt).toContain('45%')
  })

  it('includes tags when present', () => {
    const prompt = buildContinuationPrompt(makeParent({ tags: ['email_domain', 'suspicious'] }))
    expect(prompt).toContain('email_domain')
    expect(prompt).toContain('suspicious')
  })

  it('includes SET SESSION instruction', () => {
    const prompt = buildContinuationPrompt(makeParent())
    expect(prompt).toContain('SET SESSION')
    expect(prompt).toContain('trustim')
  })

  it('references uncovered dimensions when some remain', () => {
    // nodes is empty → all 8 dimensions are uncovered
    const prompt = buildContinuationPrompt(makeParent())
    // Should reference investigation steps / dimensions
    expect(prompt).toContain('execute_trino_query')
  })

  it('when all dimensions covered and confidence > 0.6, focuses on impact', () => {
    // Mock nodes that cover all 8 dimensions
    vi.mocked(useGraphStore.getState).mockReturnValue({
      nodes: {
        n1: { label: 'Email analysis', query: "split_part(email, '@', 2)", tags: [] },
        n2: { label: 'IP breakdown', query: 'requestheader__ip', tags: [] },
        n3: { label: 'Device check', query: 'canvashash distribution', tags: [] },
        n4: { label: 'Challenge rates', query: 'captcha challenge events', tags: [] },
        n5: { label: 'Restrictions', query: 'dim_member_trust restriction', tags: [] },
        n6: { label: 'WoW analysis', query: 't7d wow_pct metrics', tags: [] },
        n7: { label: 'Impact', query: 'fact_experience impact', tags: [] },
        n8: { label: 'SEV check', query: '', tags: ['sev-1'] },
      },
    } as unknown as ReturnType<typeof useGraphStore.getState>)

    const prompt = buildContinuationPrompt(makeParent({ confidence: 0.75 }))
    expect(prompt).toContain('All investigation dimensions are covered')
    expect(prompt).toContain('impact')
  })

  it('when all dimensions covered and confidence ≤ 0.6, looks for patterns', () => {
    vi.mocked(useGraphStore.getState).mockReturnValue({
      nodes: {
        n1: { label: 'Email analysis', query: "split_part(email, '@', 2)", tags: [] },
        n2: { label: 'IP breakdown', query: 'requestheader__ip', tags: [] },
        n3: { label: 'Device check', query: 'canvashash distribution', tags: [] },
        n4: { label: 'Challenge rates', query: 'captcha challenge events', tags: [] },
        n5: { label: 'Restrictions', query: 'dim_member_trust restriction', tags: [] },
        n6: { label: 'WoW analysis', query: 't7d wow_pct metrics', tags: [] },
        n7: { label: 'Impact', query: 'fact_experience impact', tags: [] },
        n8: { label: 'SEV check', query: '', tags: ['sev-1'] },
      },
    } as unknown as ReturnType<typeof useGraphStore.getState>)

    const prompt = buildContinuationPrompt(makeParent({ confidence: 0.4 }))
    expect(prompt).toContain('cross-correlations')
  })

  it('includes cohort member IDs when extracted', () => {
    vi.mocked(extractCohort).mockReturnValue({
      memberIds: ['1234567', '9876543'],
      ips: [],
      domains: [],
      deviceHashes: [],
      emails: [],
    })
    const prompt = buildContinuationPrompt(makeParent())
    expect(prompt).toContain('Member IDs')
  })

  it('includes cohort IPs when extracted', () => {
    vi.mocked(extractCohort).mockReturnValue({
      memberIds: [],
      ips: ['185.220.101.34', '91.240.118.72'],
      domains: [],
      deviceHashes: [],
      emails: [],
    })
    const prompt = buildContinuationPrompt(makeParent())
    expect(prompt).toContain('185.220.101.34')
  })

  it('includes cohort domains when extracted', () => {
    vi.mocked(extractCohort).mockReturnValue({
      memberIds: [],
      ips: [],
      domains: ['ghksc.us', 'spam.xyz'],
      deviceHashes: [],
      emails: [],
    })
    const prompt = buildContinuationPrompt(makeParent())
    expect(prompt).toContain('ghksc.us')
  })

  it('uses result_summary as findings, falls back to label', () => {
    const prompt = buildContinuationPrompt(makeParent({ result_summary: '' }))
    // Should fall back to label
    expect(prompt).toContain('Email domain analysis')
  })

  it('suggests parallel investigation when 2+ dimensions uncovered', () => {
    // Empty nodes → all dimensions uncovered → should suggest parallel
    const prompt = buildContinuationPrompt(makeParent())
    expect(prompt).toContain('PARALLEL')
  })
})
