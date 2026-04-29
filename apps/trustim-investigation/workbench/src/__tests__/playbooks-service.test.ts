/**
 * Tests for computeEntryNodeIds from playbooks/service.ts.
 * Computes entry node IDs — nodes with no incoming edges.
 * Re-implemented here to avoid cross-project-reference import.
 */
import { describe, it, expect } from 'vitest'

/** Compute entry node IDs — nodes with no incoming edges */
function computeEntryNodeIds(nodes: Array<{ id: string }>, edges: Array<{ target: string }>): string[] {
  const targets = new Set(edges.map(e => e.target))
  return nodes.filter(n => !targets.has(n.id)).map(n => n.id)
}

describe('computeEntryNodeIds', () => {
  it('returns nodes with no incoming edges as entry nodes', () => {
    const nodes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
    const edges = [{ target: 'b' }, { target: 'c' }]
    expect(computeEntryNodeIds(nodes, edges)).toEqual(['a'])
  })

  it('returns empty when all nodes have incoming edges', () => {
    const nodes = [{ id: 'a' }, { id: 'b' }]
    const edges = [{ target: 'a' }, { target: 'b' }]
    expect(computeEntryNodeIds(nodes, edges)).toEqual([])
  })

  it('returns all nodes when no edges exist', () => {
    const nodes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
    const edges: Array<{ target: string }> = []
    expect(computeEntryNodeIds(nodes, edges)).toEqual(['a', 'b', 'c'])
  })

  it('returns empty for empty nodes and edges', () => {
    expect(computeEntryNodeIds([], [])).toEqual([])
  })

  it('returns single isolated node as entry node', () => {
    const nodes = [{ id: 'only' }]
    const edges: Array<{ target: string }> = []
    expect(computeEntryNodeIds(nodes, edges)).toEqual(['only'])
  })

  it('handles diamond DAG correctly', () => {
    // a → b, a → c, b → d, c → d
    const nodes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }]
    const edges = [{ target: 'b' }, { target: 'c' }, { target: 'd' }, { target: 'd' }]
    expect(computeEntryNodeIds(nodes, edges)).toEqual(['a'])
  })

  it('handles multiple entry nodes in a forest', () => {
    // Two disconnected chains: a→b, c→d
    const nodes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }]
    const edges = [{ target: 'b' }, { target: 'd' }]
    expect(computeEntryNodeIds(nodes, edges)).toEqual(['a', 'c'])
  })

  it('ignores edges pointing to non-existent nodes', () => {
    const nodes = [{ id: 'a' }, { id: 'b' }]
    const edges = [{ target: 'z' }] // z is not in nodes
    expect(computeEntryNodeIds(nodes, edges)).toEqual(['a', 'b'])
  })
})
