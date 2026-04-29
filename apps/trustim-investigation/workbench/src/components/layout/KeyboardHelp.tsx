interface Props {
  onClose: () => void
}

const SHORTCUTS = [
  { keys: 'Esc', action: 'Close detail drawer / deselect node' },
  { keys: 'Cmd+Shift+S', action: 'Toggle Skills browser' },
  { keys: 'Cmd+Shift+M', action: 'Toggle MCP status panel' },
  { keys: 'Cmd+K', action: 'Quick open (search sessions & actions)' },
  { keys: 'Cmd+Shift+L', action: 'Toggle Sessions list' },
  { keys: 'Cmd+Shift+K', action: 'Compare two investigations' },
  { keys: 'Cmd+Shift+F', action: 'Global search across all node results' },
  { keys: 'Cmd+Shift+I', action: 'Investigation checklist' },
  { keys: 'Cmd+Shift+P', action: 'Quick publish (copy audit report)' },
  { keys: 'Alt+1–5', action: 'Switch tabs (Home, Alerts, Automations, Playbooks, Settings)' },
  { keys: 'Cmd+.', action: 'Cycle view mode (graph → heatmap → timeline → log)' },
  { keys: 'Cmd+0', action: 'Fit graph to view' },
  { keys: 'Cmd+/', action: 'Focus chat input' },
  { keys: '?', action: 'Show this help (when input not focused)' },
]

const GRAPH_SHORTCUTS = [
  { keys: 'Click node', action: 'Select and open detail drawer' },
  { keys: 'Double-click', action: 'Set node as chat context for branching' },
  { keys: 'Shift+Click', action: 'Multi-select nodes for batch operations' },
  { keys: 'Right-click', action: 'Context menu (score, tags, collapse, dead end)' },
  { keys: 'Drag node', action: 'Manually reposition (preserved for session)' },
  { keys: 'Scroll', action: 'Zoom in/out' },
  { keys: 'Click + drag', action: 'Pan the graph' },
  { keys: 'Arrow L/R', action: 'Navigate between sibling nodes' },
  { keys: 'Arrow Up', action: 'Navigate to parent node' },
  { keys: 'Arrow Down', action: 'Navigate to first child node' },
  { keys: 'Enter', action: 'Quick branch from selected node' },
  { keys: 'N', action: 'Focus note input in detail drawer' },
  { keys: 'T', action: 'Toggle "important" tag on selected node' },
  { keys: 'P', action: 'Toggle pin on selected node' },
  { keys: 'Space', action: 'Close node detail drawer' },
  { keys: 'Delete', action: 'Toggle dead end on selected node' },
]

const CHAT_SHORTCUTS = [
  { keys: 'Enter', action: 'Send message' },
  { keys: 'Shift+Enter', action: 'New line' },
  { keys: '/skill-name', action: 'Invoke a skill by name' },
  { keys: '#note text', action: 'Add an annotation node to the graph' },
  { keys: 'Cmd+Z', action: 'Undo last investigator action' },
  { keys: 'Cmd+Shift+Z', action: 'Redo undone action' },
  { keys: 'Cmd+F', action: 'Search within node output (when drawer open)' },
]

export function KeyboardHelp({ onClose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="bg-surface-1 border border-surface-3 rounded-xl p-6 w-[460px] max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">Keyboard Shortcuts</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>

        <Section title="Global" shortcuts={SHORTCUTS} />
        <Section title="Graph Panel" shortcuts={GRAPH_SHORTCUTS} />
        <Section title="Chat Panel" shortcuts={CHAT_SHORTCUTS} />

        <p className="text-[10px] text-gray-500 mt-4 pt-4 border-t border-surface-3">
          Juniper v0.1 — Press ? to toggle this help
        </p>
      </div>
    </div>
  )
}

function Section({ title, shortcuts }: { title: string; shortcuts: { keys: string; action: string }[] }) {
  return (
    <div className="mb-4">
      <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">{title}</h3>
      <div className="space-y-1">
        {shortcuts.map((s, i) => (
          <div key={i} className="flex items-center gap-3 text-xs">
            <kbd className="bg-surface-3 text-gray-300 px-2 py-0.5 rounded font-mono text-[10px] min-w-[100px] text-center">
              {s.keys}
            </kbd>
            <span className="text-gray-400">{s.action}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
