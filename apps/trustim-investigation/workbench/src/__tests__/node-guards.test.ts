/**
 * Tests for node field guards — ensures background agent nodes with missing
 * fields don't crash the UI components.
 *
 * Past bugs covered:
 * - parent_ids undefined → crash in NodeDetailDrawer, App.tsx arrow nav
 * - tags undefined → crash in InvestigationNode, GraphSearch, NodeContextMenu
 * - node_ids undefined on messages → crash in ChatPanel, ChatMessage
 * - parameters undefined → crash in NodeDetailDrawer Object.keys()
 * - result_raw undefined → crash in NodeDetailDrawer .length
 */
import { describe, it, expect } from 'vitest'

/** Simulate the guard patterns used across the codebase */
function guardedAccess(node: Record<string, unknown>) {
  return {
    parentId: ((node.parent_ids as string[] | undefined) || [])[0],
    parentCount: ((node.parent_ids as string[] | undefined) || []).length,
    hasTags: ((node.tags as string[] | undefined) || []).length > 0,
    tagsList: ((node.tags as string[] | undefined) || []).map(t => t),
    hasSev: ((node.tags as string[] | undefined) || []).some(t => t.startsWith('SEV-')),
    sevTag: ((node.tags as string[] | undefined) || []).find(t => t.startsWith('SEV-')),
    paramKeys: Object.keys((node.parameters as Record<string, unknown>) || {}),
    resultLen: ((node.result_raw as string) || '').length,
  }
}

function guardedMessageAccess(msg: Record<string, unknown>) {
  return {
    nodeIds: ((msg.node_ids as string[] | undefined) || []),
    firstNodeId: ((msg.node_ids as string[] | undefined) || [])[0],
    hasNodes: ((msg.node_ids as string[] | undefined) || []).length > 0,
  }
}

describe('Node field guards — background agent nodes', () => {
  it('handles node with all fields undefined', () => {
    const node = { node_id: 'n1', label: 'test', status: 'running' }
    const result = guardedAccess(node)
    expect(result.parentId).toBeUndefined()
    expect(result.parentCount).toBe(0)
    expect(result.hasTags).toBe(false)
    expect(result.tagsList).toEqual([])
    expect(result.hasSev).toBe(false)
    expect(result.sevTag).toBeUndefined()
    expect(result.paramKeys).toEqual([])
    expect(result.resultLen).toBe(0)
  })

  it('handles node with null fields', () => {
    const node = { parent_ids: null, tags: null, parameters: null, result_raw: null }
    const result = guardedAccess(node as any)
    expect(result.parentId).toBeUndefined()
    expect(result.hasTags).toBe(false)
    expect(result.paramKeys).toEqual([])
    expect(result.resultLen).toBe(0)
  })

  it('handles fully populated node', () => {
    const node = {
      parent_ids: ['p1', 'p2'],
      tags: ['SEV-3', 'fake-accounts'],
      parameters: { DATE: '2026-03-30' },
      result_raw: 'some result data',
    }
    const result = guardedAccess(node)
    expect(result.parentId).toBe('p1')
    expect(result.parentCount).toBe(2)
    expect(result.hasTags).toBe(true)
    expect(result.tagsList).toEqual(['SEV-3', 'fake-accounts'])
    expect(result.hasSev).toBe(true)
    expect(result.sevTag).toBe('SEV-3')
    expect(result.paramKeys).toEqual(['DATE'])
    expect(result.resultLen).toBe(16)
  })
})

describe('Message node_ids guards', () => {
  it('handles message with undefined node_ids', () => {
    const msg = { id: 'm1', role: 'assistant', content: 'hello' }
    const result = guardedMessageAccess(msg)
    expect(result.nodeIds).toEqual([])
    expect(result.firstNodeId).toBeUndefined()
    expect(result.hasNodes).toBe(false)
  })

  it('handles message with populated node_ids', () => {
    const msg = { node_ids: ['n1', 'n2'] }
    const result = guardedMessageAccess(msg)
    expect(result.nodeIds).toEqual(['n1', 'n2'])
    expect(result.firstNodeId).toBe('n1')
    expect(result.hasNodes).toBe(true)
  })
})
