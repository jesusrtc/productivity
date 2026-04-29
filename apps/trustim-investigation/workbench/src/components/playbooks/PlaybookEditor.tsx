import { useState, useEffect, useCallback, useRef, memo, type DragEvent } from 'react'
import {
  ReactFlow, ReactFlowProvider, useNodesState, useEdgesState,
  Background, Controls, MiniMap, BackgroundVariant,
  Handle, Position, addEdge as rfAddEdge, useReactFlow,
  BaseEdge, EdgeLabelRenderer, getBezierPath,
  type Node, type Edge, type Connection, type NodeTypes, type NodeProps, type EdgeTypes, type EdgeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { usePlaybookStore } from '../../store/playbook'
import { useAutomationStore } from '../../store/automation'
import type { Playbook, PlaybookNode, PlaybookEdge } from '../../types/playbook'

interface Props {
  playbook?: Playbook
  onClose: () => void
}

// --- Custom node for playbook steps ---
const TYPE_STYLES: Record<string, { bg: string; border: string; badge: string; icon: string }> = {
  automation: { bg: 'bg-surface-2', border: 'border-surface-4', badge: 'bg-blue-900/30 text-blue-400', icon: '\u2699' },
  playbook:   { bg: 'bg-surface-2', border: 'border-surface-4', badge: 'bg-green-900/30 text-green-400', icon: '\u{1F4CB}' },
  condition:  { bg: 'bg-yellow-900/10', border: 'border-yellow-800/40', badge: 'bg-yellow-900/30 text-yellow-400', icon: '\u2753' },
  note:       { bg: 'bg-purple-900/10', border: 'border-purple-800/40', badge: 'bg-purple-900/30 text-purple-400', icon: '\u{1F4DD}' },
  prompt:     { bg: 'bg-cyan-900/10', border: 'border-cyan-800/40', badge: 'bg-cyan-900/30 text-cyan-400', icon: '\u{1F4AC}' },
}

const PlaybookStepNode = memo(({ id, data, selected }: NodeProps) => {
  const d = data as { label: string; refId: string; refType: string; inputCount: number; body?: string; onDelete?: (id: string) => void }
  const style = TYPE_STYLES[d.refType] || TYPE_STYLES.automation
  return (
    <div className={`relative px-3 py-2.5 rounded-lg border-2 min-w-[180px] max-w-[260px] transition-colors group ${
      selected ? 'border-accent-blue bg-accent-blue/10' : `${style.border} ${style.bg} hover:brightness-110`
    }`}>
      <Handle type="target" position={Position.Top} className="!w-3 !h-3 !bg-accent-blue !border-2 !border-surface-1" />
      <button
        className="absolute -top-2 -right-2 w-4 h-4 rounded-full bg-red-500/80 text-white text-[8px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500"
        onClick={(e) => { e.stopPropagation(); if (d.onDelete) d.onDelete(id) }}
        title="Remove step"
      >{'\u2715'}</button>
      <div className="flex items-center gap-1.5">
        <span className="text-[11px]">{style.icon}</span>
        <span className="text-[12px] text-gray-200 font-medium truncate">{d.label}</span>
      </div>
      <div className="flex items-center gap-1.5 mt-1">
        <span className={`text-[9px] px-1.5 py-0.5 rounded ${style.badge}`}>{d.refType}</span>
        {d.refType === 'automation' && <span className="text-[9px] text-gray-500 truncate">{d.refId}</span>}
      </div>
      {d.body && <div className="text-[9px] text-gray-400 mt-1 line-clamp-2 italic">{d.body}</div>}
      {d.inputCount > 0 && <div className="text-[9px] text-gray-600 mt-0.5">{d.inputCount} inputs</div>}
      <Handle type="source" position={Position.Bottom} className="!w-3 !h-3 !bg-accent-blue !border-2 !border-surface-1" />
    </div>
  )
})
PlaybookStepNode.displayName = 'PlaybookStepNode'

// --- Custom edge with delete button ---
const DeletableEdge = memo(({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, data }: EdgeProps) => {
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition })
  const onDelete = (data as any)?.onDelete as ((id: string) => void) | undefined
  return (
    <>
      <BaseEdge id={id} path={edgePath} style={{ stroke: '#4a4a5a', strokeWidth: 2 }} />
      <EdgeLabelRenderer>
        <div
          style={{ position: 'absolute', transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`, pointerEvents: 'all' }}
          className="flex items-center gap-1"
        >
          {label && <span className="text-[9px] text-accent-purple bg-surface-1/90 px-1.5 py-0.5 rounded">{String(label)}</span>}
          <button
            onClick={() => { if (onDelete) onDelete(id) }}
            className="w-4 h-4 rounded-full bg-red-500/70 text-white text-[8px] flex items-center justify-center hover:bg-red-500 transition-colors"
            title="Delete connection"
          >
            {'\u2715'}
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  )
})
DeletableEdge.displayName = 'DeletableEdge'

const nodeTypes: NodeTypes = { playbook_step: PlaybookStepNode as any }
const edgeTypes: EdgeTypes = { deletable: DeletableEdge as any }

// --- Convert between playbook format and ReactFlow format ---
function toRFNodes(pbNodes: PlaybookNode[], onDelete?: (id: string) => void): Node[] {
  return pbNodes.map(n => ({
    id: n.id,
    type: 'playbook_step',
    position: n.position || { x: 0, y: 0 },
    data: { label: n.label, refId: n.ref_id, refType: n.ref_type, body: n.body, inputCount: Object.keys(n.inputs).length + Object.keys(n.input_refs).length, onDelete },
  }))
}

function toRFEdges(pbEdges: PlaybookEdge[], onDelete?: (id: string) => void): Edge[] {
  return pbEdges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: 'deletable',
    label: e.label || undefined,
    data: { onDelete },
  }))
}

// --- Inner editor (needs ReactFlowProvider) ---
function EditorCanvas({ playbook, onClose }: Props) {
  const [name, setName] = useState(playbook?.name || '')
  const [description, setDescription] = useState(playbook?.description || '')
  const [category, setCategory] = useState(playbook?.category || '')
  const [pbNodes, setPbNodes] = useState<PlaybookNode[]>(playbook?.nodes || [])
  const [pbEdges, setPbEdges] = useState<PlaybookEdge[]>(playbook?.edges || [])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  const deleteNodeRef = useRef<(id: string) => void>(() => {})
  const deleteEdgeRef = useRef<(id: string) => void>(() => {})
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState(toRFNodes(pbNodes, (id) => deleteNodeRef.current(id)))
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState(toRFEdges(pbEdges, (id) => deleteEdgeRef.current(id)))
  const reactFlowInstance = useReactFlow()
  const wrapperRef = useRef<HTMLDivElement>(null)

  const automations = useAutomationStore((s) => s.automations)
  const fetchAutomations = useAutomationStore((s) => s.fetchAutomations)
  useEffect(() => { if (automations.length === 0) fetchAutomations() }, [])

  // Sync RF nodes back to playbook nodes on position changes
  const onNodeDragStop = useCallback((_: any, node: Node) => {
    setPbNodes(prev => prev.map(n => n.id === node.id ? { ...n, position: node.position } : n))
  }, [])

  // Handle new connections
  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return
    const edgeId = `edge-${connection.source}-${connection.target}`
    if (pbEdges.some(e => e.source === connection.source && e.target === connection.target)) return
    const newEdge: PlaybookEdge = { id: edgeId, source: connection.source, target: connection.target }
    setPbEdges(prev => [...prev, newEdge])
    setRfEdges(prev => rfAddEdge({ ...connection, id: edgeId, type: 'deletable', data: { onDelete: (eid: string) => deleteEdgeRef.current(eid) } }, prev))
  }, [pbEdges, setRfEdges])

  // Drop automation from sidebar
  const onDragOver = useCallback((e: DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }, [])
  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault()
    const autoId = e.dataTransfer.getData('automation/id')
    const autoName = e.dataTransfer.getData('automation/name')
    if (!autoId) return

    const position = reactFlowInstance.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    const id = `step-${Date.now()}-${Math.random().toString(36).slice(2, 4)}`
    const newPbNode: PlaybookNode = { id, ref_id: autoId, ref_type: 'automation', label: autoName, inputs: {}, input_refs: {}, position }
    setPbNodes(prev => [...prev, newPbNode])
    setRfNodes(prev => [...prev, { id, type: 'playbook_step', position, data: { label: autoName, refId: autoId, refType: 'automation', inputCount: 0, onDelete: (nid: string) => deleteNodeRef.current(nid) } }])
  }, [reactFlowInstance, setRfNodes])

  // Select node
  const onNodeClick = useCallback((_: any, node: Node) => { setSelectedNodeId(node.id) }, [])
  const onPaneClick = useCallback(() => { setSelectedNodeId(null) }, [])

  // Delete node
  const deleteNode = useCallback((id: string) => {
    setPbNodes(prev => prev.filter(n => n.id !== id))
    setPbEdges(prev => prev.filter(e => e.source !== id && e.target !== id))
    setRfNodes(prev => prev.filter(n => n.id !== id))
    setRfEdges(prev => prev.filter(e => e.source !== id && e.target !== id))
    if (selectedNodeId === id) setSelectedNodeId(null)
  }, [selectedNodeId, setRfNodes, setRfEdges])
  deleteNodeRef.current = deleteNode

  // Delete edge
  const deleteEdge = useCallback((id: string) => {
    setPbEdges(prev => prev.filter(e => e.id !== id))
    setRfEdges(prev => prev.filter(e => e.id !== id))
  }, [setRfEdges])
  deleteEdgeRef.current = deleteEdge

  // Add a logic block (condition/note/prompt)
  const addLogicBlock = useCallback((type: 'condition' | 'note' | 'prompt') => {
    const id = `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 4)}`
    const labels = { condition: 'If / Else', note: 'Note', prompt: 'LLM Prompt' }
    const bodies = { condition: 'If the previous step found suspicious activity, continue to the next step.', note: 'Analyst should review the results before proceeding.', prompt: 'Analyze the results and determine if this is a real threat or false positive.' }
    const position = { x: 200 + pbNodes.length * 30, y: 100 + pbNodes.length * 60 }
    const newNode: PlaybookNode = { id, ref_id: type, ref_type: type, label: labels[type], inputs: {}, input_refs: {}, body: bodies[type], position }
    setPbNodes(prev => [...prev, newNode])
    setRfNodes(prev => [...prev, { id, type: 'playbook_step', position, data: { label: labels[type], refId: type, refType: type, body: bodies[type], inputCount: 0, onDelete: (nid: string) => deleteNodeRef.current(nid) } }])
  }, [pbNodes.length, setRfNodes])

  // Save
  const handleSave = async () => {
    if (!name.trim()) return
    const data = { name: name.trim(), description: description.trim(), category: category.trim() || 'custom', nodes: pbNodes, edges: pbEdges, inputs: [], entry_node_ids: [] }
    if (playbook?.id) {
      await usePlaybookStore.getState().updatePlaybook(playbook.id, data)
    } else {
      await usePlaybookStore.getState().createPlaybook(data)
    }
    onClose()
  }

  const sel = pbNodes.find(n => n.id === selectedNodeId)

  return (
    <div className="fixed inset-0 bg-black/70 z-[110]" onClick={onClose}>
      <div className="absolute inset-3 bg-surface-1 border border-surface-3 rounded-xl flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-surface-3 flex-shrink-0">
          <div className="flex items-center gap-3">
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Playbook name"
              className="text-[15px] font-medium text-gray-200 bg-transparent border-b border-transparent hover:border-surface-4 focus:border-accent-blue px-1 focus:outline-none" />
            <input value={category} onChange={e => setCategory(e.target.value)} placeholder="category"
              className="text-[11px] text-gray-500 bg-transparent border-b border-transparent hover:border-surface-4 focus:border-accent-blue px-1 focus:outline-none w-24" />
            <span className="text-[10px] text-gray-600">{pbNodes.length} steps, {pbEdges.length} edges</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                import('dagre').then(dagre => {
                  const g = new dagre.graphlib.Graph()
                  g.setDefaultEdgeLabel(() => ({}))
                  g.setGraph({ rankdir: 'TB', ranksep: 80, nodesep: 60 })
                  pbNodes.forEach(n => g.setNode(n.id, { width: 200, height: 60 }))
                  pbEdges.forEach(e => g.setEdge(e.source, e.target))
                  dagre.layout(g)
                  const updated = pbNodes.map(n => {
                    const pos = g.node(n.id)
                    return { ...n, position: { x: pos.x - 100, y: pos.y - 30 } }
                  })
                  setPbNodes(updated)
                  setRfNodes(toRFNodes(updated, (id) => deleteNodeRef.current(id)))
                  setTimeout(() => reactFlowInstance.fitView(), 100)
                })
              }}
              disabled={pbNodes.length === 0}
              className="text-[12px] text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-md hover:bg-surface-3 disabled:opacity-50"
            >Auto Layout</button>
            <button onClick={onClose} className="text-[12px] text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-md">Cancel</button>
            <button onClick={handleSave} disabled={!name.trim() || pbNodes.length === 0}
              className="text-[12px] bg-accent-blue hover:bg-blue-600 text-white px-4 py-1.5 rounded-md disabled:opacity-50">
              {playbook ? 'Update' : 'Create'}
            </button>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left: Sidebar — logic blocks + automations */}
          <div className="w-[200px] border-r border-surface-3 overflow-y-auto p-3 flex-shrink-0">
            {/* Logic blocks */}
            <h4 className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Logic Blocks</h4>
            <div className="flex gap-1 mb-3 flex-wrap">
              <button onClick={() => addLogicBlock('condition')} className="text-[10px] bg-yellow-900/20 text-yellow-400 px-2 py-1 rounded hover:bg-yellow-900/30 transition-colors">If / Else</button>
              <button onClick={() => addLogicBlock('note')} className="text-[10px] bg-purple-900/20 text-purple-400 px-2 py-1 rounded hover:bg-purple-900/30 transition-colors">Note</button>
              <button onClick={() => addLogicBlock('prompt')} className="text-[10px] bg-cyan-900/20 text-cyan-400 px-2 py-1 rounded hover:bg-cyan-900/30 transition-colors">LLM Prompt</button>
            </div>
            {/* Automations */}
            <h4 className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Automations</h4>
            <p className="text-[9px] text-gray-600 mb-2">Drag onto canvas</p>
            <div className="space-y-0.5">
              {automations.map(a => (
                <div
                  key={a.id}
                  draggable
                  onDragStart={e => { e.dataTransfer.setData('automation/id', a.id); e.dataTransfer.setData('automation/name', a.name); e.dataTransfer.effectAllowed = 'move' }}
                  className="px-2 py-1.5 rounded text-[11px] text-gray-300 hover:bg-surface-3 cursor-grab active:cursor-grabbing transition-colors truncate"
                  title={a.description}
                >
                  {a.name}
                </div>
              ))}
            </div>
          </div>

          {/* Center: ReactFlow canvas */}
          <div ref={wrapperRef} className="flex-1" onDragOver={onDragOver} onDrop={onDrop}>
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={onNodeClick}
              onNodeDragStop={onNodeDragStop}
              onPaneClick={onPaneClick}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              fitView
              minZoom={0.3}
              maxZoom={2}
              proOptions={{ hideAttribution: true }}
              deleteKeyCode="Backspace"
            >
              <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="rgba(255,255,255,0.04)" />
              <Controls showInteractive={false} />
              <MiniMap
                nodeColor={() => '#3b82f6'}
                maskColor="rgba(0,0,0,0.6)"
                style={{ background: 'rgba(18,18,26,0.9)', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)' }}
              />
            </ReactFlow>
          </div>

          {/* Right: Node config panel */}
          {sel && (
            <div className="w-[220px] border-l border-surface-3 overflow-y-auto p-3 flex-shrink-0">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-[10px] text-gray-500 uppercase tracking-wider">Node Config</h4>
                <button onClick={() => deleteNode(sel.id)} className="text-[10px] text-red-400 hover:text-red-300">Delete</button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-[10px] text-gray-500 block mb-1">Label</label>
                  <input value={sel.label}
                    onChange={e => {
                      const val = e.target.value
                      setPbNodes(prev => prev.map(n => n.id === sel.id ? { ...n, label: val } : n))
                      setRfNodes(prev => prev.map(n => n.id === sel.id ? { ...n, data: { ...n.data, label: val } } : n))
                    }}
                    className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1 text-[11px] text-gray-200 focus:outline-none focus:border-accent-blue/50" />
                </div>
                {sel.ref_type === 'automation' && (
                <div>
                  <label className="text-[10px] text-gray-500 block mb-1">Automation</label>
                  <select value={sel.ref_id}
                    onChange={e => {
                      const val = e.target.value
                      setPbNodes(prev => prev.map(n => n.id === sel.id ? { ...n, ref_id: val } : n))
                      setRfNodes(prev => prev.map(n => n.id === sel.id ? { ...n, data: { ...n.data, refId: val } } : n))
                    }}
                    className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1 text-[11px] text-gray-300 focus:outline-none">
                    {automations.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </div>
                )}
                {(sel.ref_type === 'condition' || sel.ref_type === 'note' || sel.ref_type === 'prompt') && (
                <div>
                  <label className="text-[10px] text-gray-500 block mb-1">
                    {sel.ref_type === 'condition' ? 'Condition Text' : sel.ref_type === 'prompt' ? 'LLM Prompt' : 'Note'}
                  </label>
                  <textarea
                    value={sel.body || ''}
                    onChange={e => {
                      const val = e.target.value
                      setPbNodes(prev => prev.map(n => n.id === sel.id ? { ...n, body: val } : n))
                      setRfNodes(prev => prev.map(n => n.id === sel.id ? { ...n, data: { ...n.data, body: val } } : n))
                    }}
                    rows={5}
                    className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1.5 text-[11px] text-gray-200 focus:outline-none resize-none"
                    placeholder={sel.ref_type === 'condition' ? 'Describe the condition in plain text...' : sel.ref_type === 'prompt' ? 'Write the prompt for the LLM...' : 'Add notes for the analyst...'}
                  />
                </div>
                )}
                <div>
                  <label className="text-[10px] text-gray-500 block mb-1">Input Refs</label>
                  <textarea
                    value={JSON.stringify(sel.input_refs, null, 2)}
                    onChange={e => { try { const v = JSON.parse(e.target.value); setPbNodes(prev => prev.map(n => n.id === sel.id ? { ...n, input_refs: v } : n)) } catch {} }}
                    rows={3}
                    className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1 text-[10px] text-gray-300 font-mono focus:outline-none resize-none"
                    placeholder='{ "KEY": "{{node.field}}" }'
                  />
                </div>

                {/* Outgoing edges from this node */}
                {pbEdges.filter(e => e.source === sel.id).map(e => {
                  const target = pbNodes.find(n => n.id === e.target)?.label || e.target
                  return (
                    <div key={e.id} className="bg-surface-2/40 rounded p-2">
                      <div className="text-[10px] text-gray-500 mb-1">{'\u2192'} {target}</div>
                      <input
                        value={e.label || ''}
                        onChange={ev => {
                          const label = ev.target.value
                          setPbEdges(prev => prev.map(edge => edge.id === e.id ? { ...edge, label } : edge))
                          setRfEdges(prev => prev.map(edge => edge.id === e.id ? { ...edge, label } : edge))
                        }}
                        placeholder="Condition label"
                        className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1 text-[10px] text-gray-300 focus:outline-none"
                      />
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// --- Exported wrapper with ReactFlowProvider ---
export function PlaybookEditor({ playbook, onClose }: Props) {
  return (
    <ReactFlowProvider>
      <EditorCanvas playbook={playbook} onClose={onClose} />
    </ReactFlowProvider>
  )
}
