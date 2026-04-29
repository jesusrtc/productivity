/**
 * Tests for tab isolation: snapshot/restore, edge normalization, session switching.
 * These protect against the most common regression: switching tabs blanks other investigations.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useSessionStore } from '../store/session'
import { useGraphStore } from '../store/graph'

// Reset stores before each test
beforeEach(() => {
  useSessionStore.setState({
    currentSession: null,
    sessionList: [],
    tabSnapshots: {},
    chatContext: null,
    readOnly: false,
  })
  useGraphStore.getState().clearGraph()
})

describe('Session Store - Tab Snapshots', () => {
  it('snapshotCurrentTab saves current session + graph state', () => {
    // Create a session with some nodes
    const session = useSessionStore.getState().newSession('Test A', '')
    useGraphStore.getState().addNode({
      node_id: 'n1', label: 'Node 1', action_type: 'query_execution',
      query: 'SELECT 1', status: 'completed', confidence: 0.5,
    } as any)

    // Snapshot
    useSessionStore.getState().snapshotCurrentTab()

    // Verify snapshot exists with correct data
    const snapshots = useSessionStore.getState().tabSnapshots
    expect(snapshots[session.id]).toBeDefined()
    expect(snapshots[session.id].session.id).toBe(session.id)
    expect(snapshots[session.id].session.nodes['n1']).toBeDefined()
  })

  it('restoreTab restores session + graph state', () => {
    // Create session A with nodes
    const sessionA = useSessionStore.getState().newSession('Test A', '')
    useGraphStore.getState().addNode({
      node_id: 'a1', label: 'Node A1', action_type: 'query_execution',
      query: 'SELECT 1', status: 'completed', confidence: 0.5,
    } as any)
    useSessionStore.getState().snapshotCurrentTab()

    // Switch to session B (clears graph)
    useSessionStore.getState().newSession('Test B', '')
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(0)

    // Restore A
    const restored = useSessionStore.getState().restoreTab(sessionA.id)
    expect(restored).toBe(true)
    expect(useSessionStore.getState().currentSession?.id).toBe(sessionA.id)
    expect(useGraphStore.getState().nodes['a1']).toBeDefined()
  })

  it('restoreTab returns false for unknown session', () => {
    const restored = useSessionStore.getState().restoreTab('nonexistent')
    expect(restored).toBe(false)
  })

  it('clearTabSnapshot removes snapshot', () => {
    const session = useSessionStore.getState().newSession('Test', '')
    useSessionStore.getState().snapshotCurrentTab()
    expect(useSessionStore.getState().tabSnapshots[session.id]).toBeDefined()

    useSessionStore.getState().clearTabSnapshot(session.id)
    expect(useSessionStore.getState().tabSnapshots[session.id]).toBeUndefined()
  })

  it('switching tabs preserves both sessions independently', () => {
    // Create A with node
    const sessionA = useSessionStore.getState().newSession('A', '')
    useGraphStore.getState().addNode({
      node_id: 'a1', label: 'A1', action_type: 'query_execution',
      query: 'Q1', status: 'completed', confidence: 0.8,
    } as any)
    useSessionStore.getState().snapshotCurrentTab()

    // Create B with different node
    const sessionB = useSessionStore.getState().newSession('B', '')
    useGraphStore.getState().addNode({
      node_id: 'b1', label: 'B1', action_type: 'enrichment',
      query: 'Q2', status: 'completed', confidence: 0.3,
    } as any)
    useSessionStore.getState().snapshotCurrentTab()

    // Restore A — should have a1 but NOT b1
    useSessionStore.getState().restoreTab(sessionA.id)
    expect(useGraphStore.getState().nodes['a1']).toBeDefined()
    expect(useGraphStore.getState().nodes['b1']).toBeUndefined()
    expect(useSessionStore.getState().currentSession?.name).toBe('A')

    // Restore B — should have b1 but NOT a1
    useSessionStore.getState().snapshotCurrentTab() // save A again
    useSessionStore.getState().restoreTab(sessionB.id)
    expect(useGraphStore.getState().nodes['b1']).toBeDefined()
    expect(useGraphStore.getState().nodes['a1']).toBeUndefined()
    expect(useSessionStore.getState().currentSession?.name).toBe('B')
  })
})

describe('Edge Normalization', () => {
  it('loadSession normalizes edges missing id and relation', () => {
    const session = {
      id: 'test-session',
      name: 'Test',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      starting_input: '',
      starting_input_type: 'none' as const,
      nodes: {
        n1: { node_id: 'n1', parent_ids: [], label: 'N1', status: 'completed', action_type: 'query_execution', query: '', parameters: {}, result_summary: '', result_raw: '', displays: [], confidence: 0, timestamp: new Date().toISOString(), duration_ms: 0, tags: [], reasoning: '', investigator_notes: '', confidence_reasoning: '', confidence_override: false, is_dead_end: false, subtree_collapsed: false, pinned: false, skill_name: null, tool_name: null, source_tool: null, ipynb_cell_ref: null, input_prompt: null, input_choices: null, children_ids: [] },
        n2: { node_id: 'n2', parent_ids: ['n1'], label: 'N2', status: 'completed', action_type: 'query_execution', query: '', parameters: {}, result_summary: '', result_raw: '', displays: [], confidence: 0, timestamp: new Date().toISOString(), duration_ms: 0, tags: [], reasoning: '', investigator_notes: '', confidence_reasoning: '', confidence_override: false, is_dead_end: false, subtree_collapsed: false, pinned: false, skill_name: null, tool_name: null, source_tool: null, ipynb_cell_ref: null, input_prompt: null, input_choices: null, children_ids: [] },
      },
      // Edges missing id and relation (like background agent produces)
      edges: [{ source: 'n1', target: 'n2' }] as any,
      messages: [],
      skills_used: [],
      tools_used: [],
      mcp_tools: [],
    }

    useSessionStore.getState().loadSession(session as any)

    const edges = useGraphStore.getState().edges
    expect(edges).toHaveLength(1)
    expect(edges[0].id).toBe('edge-n1-n2')
    expect(edges[0].relation).toBe('led_to')
  })

  it('loadSession filters edges referencing non-existent nodes', () => {
    const session = {
      id: 'test',
      name: 'Test',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      starting_input: '',
      starting_input_type: 'none' as const,
      nodes: { n1: { node_id: 'n1', parent_ids: [], label: 'N1', status: 'completed', action_type: 'query_execution', query: '', parameters: {}, result_summary: '', result_raw: '', displays: [], confidence: 0, timestamp: new Date().toISOString(), duration_ms: 0, tags: [], reasoning: '', investigator_notes: '', confidence_reasoning: '', confidence_override: false, is_dead_end: false, subtree_collapsed: false, pinned: false, skill_name: null, tool_name: null, source_tool: null, ipynb_cell_ref: null, input_prompt: null, input_choices: null, children_ids: [] } },
      edges: [
        { id: 'e1', source: 'n1', target: 'n2', relation: 'led_to' }, // n2 doesn't exist
        { id: 'e2', source: 'n1', target: 'n1', relation: 'led_to' }, // self-reference (valid nodes)
      ] as any,
      messages: [],
      skills_used: [],
      tools_used: [],
      mcp_tools: [],
    }

    useSessionStore.getState().loadSession(session as any)
    const edges = useGraphStore.getState().edges
    // Only the self-reference should survive (both source and target exist)
    expect(edges).toHaveLength(1)
    expect(edges[0].source).toBe('n1')
    expect(edges[0].target).toBe('n1')
  })
})
