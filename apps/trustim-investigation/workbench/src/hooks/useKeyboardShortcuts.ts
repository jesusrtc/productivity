import { useEffect, useRef } from 'react'
import { useGraphStore } from '../store/graph'
import { useSessionStore } from '../store/session'

type OverlayId = 'skills' | 'mcp' | 'help' | 'stats' | 'sessions' | 'compare' | 'quickOpen' | 'globalSearch' | 'guide' | 'templates' | 'checklist' | 'iocBrowser' | 'alerts' | null

interface KeyboardShortcutDeps {
  toggleOverlay: (id: OverlayId) => void
  setActiveOverlay: (id: OverlayId) => void
  switchPage: (page: string) => void
}

export function useKeyboardShortcuts({ toggleOverlay, setActiveOverlay, switchPage }: KeyboardShortcutDeps) {
  const overlayRef = useRef<OverlayId>(null)
  // Keep overlayRef in sync — caller must pass activeOverlay
  const syncOverlayRef = (overlay: OverlayId) => { overlayRef.current = overlay }

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      // Escape = close active overlay, then deselect node, then clear chat context
      if (e.key === 'Escape') {
        if (overlayRef.current) { setActiveOverlay(null); return }
        if (useGraphStore.getState().selectedNodeId) { useGraphStore.getState().selectNode(null); return }
        if (useSessionStore.getState().chatContext) { useSessionStore.getState().setChatContext(null); return }
      }
      // Cmd/Ctrl+Z = Undo, Cmd/Ctrl+Shift+Z = Redo
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        if (!(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
          e.preventDefault()
          import('../store/history').then(({ useHistoryStore }) => useHistoryStore.getState().undo())
        }
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && e.shiftKey) {
        if (!(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
          e.preventDefault()
          import('../store/history').then(({ useHistoryStore }) => useHistoryStore.getState().redo())
        }
      }
      // Cmd+0 = Fit graph to view
      if ((e.metaKey || e.ctrlKey) && e.key === '0') {
        e.preventDefault()
        window.dispatchEvent(new Event('fitGraphToView'))
      }
      // Cmd/Ctrl+Shift+E = Export
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'E') {
        e.preventDefault()
      }
      // Cmd/Ctrl+Shift+S = Skills
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'S') {
        e.preventDefault()
        toggleOverlay('skills')
      }
      // Cmd/Ctrl+Shift+L = Session list
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'L') {
        e.preventDefault()
        toggleOverlay('sessions')
      }
      // Cmd/Ctrl+Shift+M = MCP Status
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'M') {
        e.preventDefault()
        toggleOverlay('mcp')
      }
      // Alt+1-5 = Switch tabs (Home, Alerts, Automations, Playbooks, Settings)
      if (e.altKey && !e.metaKey && !e.ctrlKey && !e.shiftKey && e.key >= '1' && e.key <= '5') {
        e.preventDefault()
        const pages = ['home', 'alerts', 'automations', 'playbooks', 'settings'] as const
        switchPage(pages[parseInt(e.key) - 1])
      }
      // Cmd/Ctrl+Shift+I = Investigation checklist
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'I') {
        e.preventDefault()
        toggleOverlay('checklist')
      }
      // Cmd/Ctrl+Shift+F = Global search across node results
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'F') {
        e.preventDefault()
        toggleOverlay('globalSearch')
      }
      // Cmd/Ctrl+Shift+P = Quick publish (copy audit report)
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'P') {
        e.preventDefault()
        import('../utils/export').then(({ generateAuditReport }) => {
          import('../store/session').then(({ useSessionStore }) => {
            const data = useSessionStore.getState().getSessionData()
            if (data) {
              navigator.clipboard.writeText(generateAuditReport(data))
                .then(() => import('../store/toast').then(({ useToastStore }) =>
                  useToastStore.getState().addToast('Audit report copied to clipboard', 'success', 3000)
                ))
                .catch(() => import('../store/toast').then(({ useToastStore }) =>
                  useToastStore.getState().addToast('Failed to copy — clipboard access denied', 'error', 4000)
                ))
            }
          })
        })
      }
      // Cmd+. = Cycle view mode (graph → heatmap → timeline → log)
      if ((e.metaKey || e.ctrlKey) && e.key === '.') {
        e.preventDefault()
        const modes = ['graph', 'heatmap', 'timeline', 'log'] as const
        const current = useGraphStore.getState().viewMode
        const idx = modes.indexOf(current)
        useGraphStore.getState().setViewMode(modes[(idx + 1) % modes.length])
      }
      // Cmd/Ctrl+K = Quick open
      if ((e.metaKey || e.ctrlKey) && e.key === 'k' && !e.shiftKey) {
        e.preventDefault()
        toggleOverlay('quickOpen')
      }
      // Cmd/Ctrl+Shift+K = Compare sessions
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'K') {
        e.preventDefault()
        toggleOverlay('compare')
      }
      // Cmd+/ = Focus chat input
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault()
        const textarea = document.querySelector('textarea') as HTMLTextAreaElement
        if (textarea) textarea.focus()
      }
      // ? = Keyboard help (when not typing)
      if (e.key === '?' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        toggleOverlay('help')
      }
      // Space = toggle selected node detail (quick preview, like Finder)
      if (e.key === ' ' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const graph = useGraphStore.getState()
        if (graph.selectedNodeId) {
          e.preventDefault()
          graph.selectNode(null)
        }
      }
      // N = focus the note input in the node detail drawer
      if (e.key === 'n' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const graph = useGraphStore.getState()
        if (graph.selectedNodeId) {
          setTimeout(() => {
            const noteInput = document.querySelector('[data-note-input]') as HTMLInputElement
            if (noteInput) noteInput.focus()
          }, 50)
        }
      }
      // T = quick-tag selected node with "important"
      if (e.key === 't' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const graph = useGraphStore.getState()
        if (graph.selectedNodeId) {
          const node = graph.nodes[graph.selectedNodeId]
          if ((node?.tags || []).includes('important')) {
            graph.removeTag(graph.selectedNodeId, 'important')
          } else {
            graph.addTag(graph.selectedNodeId, 'important')
          }
        }
      }
      // P = toggle pin on selected node
      if (e.key === 'p' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const graph = useGraphStore.getState()
        if (graph.selectedNodeId) {
          graph.togglePin(graph.selectedNodeId)
        }
      }
      // Delete/Backspace = toggle dead end on selected node
      if ((e.key === 'Delete' || e.key === 'Backspace') && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const graph = useGraphStore.getState()
        if (graph.selectedNodeId) {
          graph.markDeadEnd(graph.selectedNodeId)
        }
      }
      // Enter = quick branch from selected node (when not in input)
      if (e.key === 'Enter' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const graph = useGraphStore.getState()
        const selected = graph.selectedNodeId
        if (selected) {
          const node = graph.nodes[selected]
          if (node && node.status === 'completed') {
            useSessionStore.getState().setChatContext({
              nodeId: node.node_id,
              label: node.label || node.action_type,
              query: node.query,
              result_summary: node.result_summary,
              result_raw: node.result_raw,
            })
            graph.selectNode(null)
            setTimeout(() => {
              const textarea = document.querySelector('textarea') as HTMLTextAreaElement
              if (textarea) textarea.focus()
            }, 100)
          }
        }
      }
      // Arrow keys to navigate between sibling nodes in the graph
      if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown') &&
          !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const graph = useGraphStore.getState()
        const selected = graph.selectedNodeId
        if (!selected) return
        const node = graph.nodes[selected]
        if (!node) return

        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          const parentId = (node.parent_ids || [])[0]
          if (!parentId) return
          const siblings = graph.edges
            .filter(edge => edge.source === parentId)
            .map(edge => edge.target)
          const idx = siblings.indexOf(selected)
          const next = e.key === 'ArrowRight'
            ? siblings[(idx + 1) % siblings.length]
            : siblings[(idx - 1 + siblings.length) % siblings.length]
          if (next) graph.selectNode(next)
        } else if (e.key === 'ArrowUp') {
          if ((node.parent_ids || [])[0]) graph.selectNode((node.parent_ids || [])[0])
        } else if (e.key === 'ArrowDown') {
          const children = graph.edges.filter(edge => edge.source === selected).map(edge => edge.target)
          if (children[0]) graph.selectNode(children[0])
        }
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [])

  return { syncOverlayRef }
}
