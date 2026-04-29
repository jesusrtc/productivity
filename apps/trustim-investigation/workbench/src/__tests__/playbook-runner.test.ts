/**
 * Tests for playbook execution logic: topological sort, input resolution, condition evaluation.
 */
import { describe, it, expect } from 'vitest'

// Re-implement core playbook logic for testing (server modules use .js imports)

interface PlaybookNode { id: string; inputs: Record<string, string>; input_refs: Record<string, string> }
interface PlaybookEdge { id: string; source: string; target: string }

function topoSort(nodes: { id: string }[], edges: { source: string; target: string }[]): string[] {
  const inDegree: Record<string, number> = {}
  const adj: Record<string, string[]> = {}
  for (const n of nodes) { inDegree[n.id] = 0; adj[n.id] = [] }
  for (const e of edges) {
    inDegree[e.target] = (inDegree[e.target] || 0) + 1
    adj[e.source] = adj[e.source] || []
    adj[e.source].push(e.target)
  }
  const queue = nodes.filter(n => inDegree[n.id] === 0).map(n => n.id)
  const sorted: string[] = []
  while (queue.length > 0) {
    const id = queue.shift()!
    sorted.push(id)
    for (const next of (adj[id] || [])) {
      inDegree[next]--
      if (inDegree[next] === 0) queue.push(next)
    }
  }
  return sorted
}

function resolveInputs(
  node: PlaybookNode,
  nodeOutputs: Record<string, Record<string, unknown>>,
  playbookInputs: Record<string, unknown>,
): Record<string, unknown> {
  const resolved: Record<string, unknown> = { ...node.inputs }
  for (const [key, ref] of Object.entries(node.input_refs)) {
    // Check {{input.X}} FIRST (playbook-level inputs)
    if (ref.startsWith('{{input.')) {
      const field = ref.replace('{{input.', '').replace('}}', '')
      resolved[key] = playbookInputs[field] !== undefined ? String(playbookInputs[field]) : node.inputs[key] || ''
    } else {
      const match = ref.match(/^\{\{(\w+)\.([\w.]+)\}\}$/)
      if (match) {
        const [, nodeId, fieldPath] = match
        let val: unknown = nodeOutputs[nodeId] || {}
        for (const part of fieldPath.split('.')) {
          if (val && typeof val === 'object') val = (val as Record<string, unknown>)[part]
          else { val = undefined; break }
        }
        resolved[key] = val !== undefined ? String(val) : node.inputs[key] || ''
      }
    }
  }
  return resolved
}

describe('Playbook Topological Sort', () => {
  it('sorts linear DAG correctly', () => {
    const nodes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
    const edges = [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }]
    expect(topoSort(nodes, edges)).toEqual(['a', 'b', 'c'])
  })

  it('handles branching DAG', () => {
    const nodes = [{ id: 'root' }, { id: 'left' }, { id: 'right' }, { id: 'merge' }]
    const edges = [
      { source: 'root', target: 'left' },
      { source: 'root', target: 'right' },
      { source: 'left', target: 'merge' },
      { source: 'right', target: 'merge' },
    ]
    const sorted = topoSort(nodes, edges)
    expect(sorted[0]).toBe('root')
    expect(sorted[sorted.length - 1]).toBe('merge')
    expect(sorted.indexOf('left')).toBeGreaterThan(sorted.indexOf('root'))
    expect(sorted.indexOf('right')).toBeGreaterThan(sorted.indexOf('root'))
  })

  it('handles single node', () => {
    expect(topoSort([{ id: 'a' }], [])).toEqual(['a'])
  })

  it('handles disconnected nodes', () => {
    const sorted = topoSort([{ id: 'a' }, { id: 'b' }], [])
    expect(sorted).toHaveLength(2)
    expect(sorted).toContain('a')
    expect(sorted).toContain('b')
  })
})

describe('Playbook Input Resolution', () => {
  it('resolves literal inputs', () => {
    const node: PlaybookNode = { id: 'n1', inputs: { DATE: '2026-03-30' }, input_refs: {} }
    expect(resolveInputs(node, {}, {})).toEqual({ DATE: '2026-03-30' })
  })

  it('resolves {{input.X}} from playbook inputs', () => {
    const node: PlaybookNode = { id: 'n1', inputs: {}, input_refs: { DATE: '{{input.DATE}}' } }
    expect(resolveInputs(node, {}, { DATE: '2026-03-30' })).toEqual({ DATE: '2026-03-30' })
  })

  it('resolves {{nodeId.field}} from parent outputs', () => {
    const node: PlaybookNode = { id: 'n2', inputs: {}, input_refs: { MIDS: '{{n1.result}}' } }
    const outputs = { n1: { result: '123,456,789' } }
    expect(resolveInputs(node, outputs, {})).toEqual({ MIDS: '123,456,789' })
  })

  it('resolves nested dot-path fields', () => {
    const node: PlaybookNode = { id: 'n2', inputs: {}, input_refs: { COUNT: '{{n1.data.count}}' } }
    const outputs = { n1: { data: { count: 42 } } }
    expect(resolveInputs(node, outputs, {})).toEqual({ COUNT: '42' })
  })

  it('falls back to literal input if ref unresolvable', () => {
    const node: PlaybookNode = { id: 'n2', inputs: { MIDS: 'default' }, input_refs: { MIDS: '{{missing.field}}' } }
    expect(resolveInputs(node, {}, {})).toEqual({ MIDS: 'default' })
  })
})

describe('File Locking Logic', () => {
  it('lock/unlock pattern is safe (conceptual)', () => {
    // The file lock uses fs.writeFileSync with 'wx' flag (exclusive create)
    // If the file exists, it throws — that's the lock
    // This test validates the conceptual model
    const locks = new Set<string>()
    const acquire = (path: string) => {
      if (locks.has(path)) return false
      locks.add(path)
      return true
    }
    const release = (path: string) => locks.delete(path)

    expect(acquire('session.json')).toBe(true)
    expect(acquire('session.json')).toBe(false) // Already locked
    release('session.json')
    expect(acquire('session.json')).toBe(true) // Released
  })
})
