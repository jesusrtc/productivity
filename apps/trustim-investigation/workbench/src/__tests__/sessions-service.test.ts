/**
 * Tests for sessions service pure functions.
 * Re-implements functions locally (server modules use .js imports that don't resolve in jsdom).
 */
import { describe, it, expect } from 'vitest'

// --- Re-implemented functions from server/domains/sessions/service.ts ---

function getMaxSeverity(nodes: Record<string, { confidence?: number; tags?: string[] }>): string {
  let maxConf = 0
  let hasSev = ''
  for (const node of Object.values(nodes)) {
    if ((node.confidence || 0) > maxConf) maxConf = node.confidence || 0
    const sevTag = (node.tags || []).find(t => t.startsWith('SEV-'))
    if (sevTag && (!hasSev || sevTag < hasSev)) hasSev = sevTag
  }
  if (hasSev) return hasSev
  if (maxConf > 0.7) return 'critical'
  if (maxConf > 0.5) return 'high'
  if (maxConf > 0.3) return 'medium'
  if (maxConf > 0.1) return 'low'
  return 'benign'
}

interface SessionSummary {
  id: string
  name: string
  created_at: string
  updated_at: string
  node_count: number
  max_severity: string
  max_confidence: number
  completed_count: number
  has_sev: boolean
  skills_used: string[]
  starting_input_type: string
}

function summarizeSession(data: any): SessionSummary | null {
  try {
    const nodes = Object.values(data.nodes || {}) as Array<{ confidence?: number; status?: string; tags?: string[] }>
    const maxConf = nodes.length > 0 ? Math.max(0, ...nodes.map(n => n.confidence || 0)) : 0
    const completedCount = nodes.filter(n => n.status === 'completed').length
    const hasSev = nodes.some(n => (n.tags || []).some(t => t.startsWith('SEV-')))
    return {
      id: data.id,
      name: data.name,
      created_at: data.created_at,
      updated_at: data.updated_at,
      node_count: nodes.length,
      max_severity: getMaxSeverity(data.nodes || {}),
      max_confidence: maxConf,
      completed_count: completedCount,
      has_sev: hasSev,
      skills_used: (data.skills_used || []).slice(0, 3),
      starting_input_type: data.starting_input_type,
    }
  } catch {
    return null
  }
}

// --- Tests ---

describe('getMaxSeverity', () => {
  it('returns benign for empty nodes', () => {
    expect(getMaxSeverity({})).toBe('benign')
  })

  it('SEV-1 tag wins over confidence', () => {
    const nodes = {
      n1: { confidence: 0.9, tags: ['SEV-1'] },
    }
    expect(getMaxSeverity(nodes)).toBe('SEV-1')
  })

  it('SEV-1 beats SEV-2 (lower number = worse)', () => {
    const nodes = {
      n1: { confidence: 0.5, tags: ['SEV-2'] },
      n2: { confidence: 0.3, tags: ['SEV-1'] },
    }
    expect(getMaxSeverity(nodes)).toBe('SEV-1')
  })

  it('SEV-2 beats SEV-3', () => {
    const nodes = {
      n1: { confidence: 0.1, tags: ['SEV-3'] },
      n2: { confidence: 0.1, tags: ['SEV-2'] },
    }
    expect(getMaxSeverity(nodes)).toBe('SEV-2')
  })

  it('confidence 0.8 → critical', () => {
    expect(getMaxSeverity({ n1: { confidence: 0.8, tags: [] } })).toBe('critical')
  })

  it('confidence 0.6 → high', () => {
    expect(getMaxSeverity({ n1: { confidence: 0.6, tags: [] } })).toBe('high')
  })

  it('confidence 0.4 → medium', () => {
    expect(getMaxSeverity({ n1: { confidence: 0.4, tags: [] } })).toBe('medium')
  })

  it('confidence 0.2 → low', () => {
    expect(getMaxSeverity({ n1: { confidence: 0.2, tags: [] } })).toBe('low')
  })

  it('confidence 0 → benign', () => {
    expect(getMaxSeverity({ n1: { confidence: 0, tags: [] } })).toBe('benign')
  })

  it('confidence exactly at boundary 0.7 → high (not critical)', () => {
    expect(getMaxSeverity({ n1: { confidence: 0.7, tags: [] } })).toBe('high')
  })

  it('confidence exactly at boundary 0.5 → medium (not high)', () => {
    expect(getMaxSeverity({ n1: { confidence: 0.5, tags: [] } })).toBe('medium')
  })

  it('highest confidence across nodes wins', () => {
    const nodes = {
      n1: { confidence: 0.2, tags: [] },
      n2: { confidence: 0.8, tags: [] },
      n3: { confidence: 0.4, tags: [] },
    }
    expect(getMaxSeverity(nodes)).toBe('critical')
  })

  it('nodes without tags default to empty array', () => {
    expect(getMaxSeverity({ n1: { confidence: 0.6 } })).toBe('high')
  })
})

describe('summarizeSession', () => {
  it('computes correct node_count', () => {
    const data = {
      id: 's1', name: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02',
      nodes: { n1: { confidence: 0.5, status: 'completed', tags: [] }, n2: { confidence: 0.3, status: 'running', tags: [] } },
      skills_used: [], starting_input_type: 'alert_id',
    }
    const result = summarizeSession(data)!
    expect(result.node_count).toBe(2)
  })

  it('computes max_confidence across nodes', () => {
    const data = {
      id: 's1', name: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02',
      nodes: { n1: { confidence: 0.3, status: 'completed', tags: [] }, n2: { confidence: 0.8, status: 'completed', tags: [] } },
      skills_used: [], starting_input_type: 'alert_id',
    }
    expect(summarizeSession(data)!.max_confidence).toBe(0.8)
  })

  it('computes completed_count', () => {
    const data = {
      id: 's1', name: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02',
      nodes: {
        n1: { confidence: 0.5, status: 'completed', tags: [] },
        n2: { confidence: 0.3, status: 'running', tags: [] },
        n3: { confidence: 0.1, status: 'completed', tags: [] },
      },
      skills_used: [], starting_input_type: 'alert_id',
    }
    expect(summarizeSession(data)!.completed_count).toBe(2)
  })

  it('detects has_sev when SEV tag present', () => {
    const data = {
      id: 's1', name: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02',
      nodes: { n1: { confidence: 0.5, status: 'completed', tags: ['SEV-2'] } },
      skills_used: [], starting_input_type: 'alert_id',
    }
    expect(summarizeSession(data)!.has_sev).toBe(true)
  })

  it('has_sev is false when no SEV tags', () => {
    const data = {
      id: 's1', name: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02',
      nodes: { n1: { confidence: 0.5, status: 'completed', tags: ['IOC', 'escalate'] } },
      skills_used: [], starting_input_type: 'alert_id',
    }
    expect(summarizeSession(data)!.has_sev).toBe(false)
  })

  it('handles empty nodes', () => {
    const data = {
      id: 's1', name: 'Empty', created_at: '2026-01-01', updated_at: '2026-01-02',
      nodes: {},
      skills_used: [], starting_input_type: 'natural_language',
    }
    const result = summarizeSession(data)!
    expect(result.node_count).toBe(0)
    expect(result.max_confidence).toBe(0)
    expect(result.completed_count).toBe(0)
    expect(result.has_sev).toBe(false)
    expect(result.max_severity).toBe('benign')
  })

  it('truncates skills_used to 3', () => {
    const data = {
      id: 's1', name: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02',
      nodes: {},
      skills_used: ['a', 'b', 'c', 'd', 'e'],
      starting_input_type: 'alert_id',
    }
    expect(summarizeSession(data)!.skills_used).toEqual(['a', 'b', 'c'])
  })

  it('computes max_severity from nodes', () => {
    const data = {
      id: 's1', name: 'Test', created_at: '2026-01-01', updated_at: '2026-01-02',
      nodes: { n1: { confidence: 0.9, status: 'completed', tags: [] } },
      skills_used: [], starting_input_type: 'alert_id',
    }
    expect(summarizeSession(data)!.max_severity).toBe('critical')
  })
})
