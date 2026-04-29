/**
 * Tests for edge normalization — background agent edges missing id/relation.
 *
 * Past bug: ReactFlow couldn't render edges from background agents because
 * they only had {source, target} without id or relation fields.
 */
import { describe, it, expect } from 'vitest'

/** Replicate normalizeEdges from session store */
function normalizeEdges(edges: any[], nodeIds: Set<string>): any[] {
  return (edges || [])
    .filter((e: { source: string; target: string }) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((e: any) => ({
      id: e.id || `edge-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      relation: e.relation || 'led_to',
    }))
}

describe('Edge Normalization', () => {
  it('adds missing id and relation', () => {
    const edges = [{ source: 'a', target: 'b' }]
    const result = normalizeEdges(edges, new Set(['a', 'b']))
    expect(result[0].id).toBe('edge-a-b')
    expect(result[0].relation).toBe('led_to')
  })

  it('preserves existing id and relation', () => {
    const edges = [{ id: 'my-edge', source: 'a', target: 'b', relation: 'supports' }]
    const result = normalizeEdges(edges, new Set(['a', 'b']))
    expect(result[0].id).toBe('my-edge')
    expect(result[0].relation).toBe('supports')
  })

  it('filters edges with missing source node', () => {
    const edges = [{ source: 'missing', target: 'b' }]
    const result = normalizeEdges(edges, new Set(['a', 'b']))
    expect(result).toHaveLength(0)
  })

  it('filters edges with missing target node', () => {
    const edges = [{ source: 'a', target: 'missing' }]
    const result = normalizeEdges(edges, new Set(['a', 'b']))
    expect(result).toHaveLength(0)
  })

  it('handles null/undefined edges array', () => {
    expect(normalizeEdges(null as any, new Set())).toEqual([])
    expect(normalizeEdges(undefined as any, new Set())).toEqual([])
  })

  it('handles empty edges array', () => {
    expect(normalizeEdges([], new Set(['a']))).toEqual([])
  })
})
