/**
 * Undo/redo history for investigator actions (PRD Phase 14).
 *
 * Tracks reversible actions: threat_score overrides, note changes,
 * dead-end toggles. Each action stores enough data to undo and redo.
 */

import { create } from 'zustand'
import { useGraphStore } from './graph'

interface HistoryAction {
  type: 'override_confidence' | 'toggle_dead_end' | 'set_notes'
  nodeId: string
  before: unknown
  after: unknown
  /** Bug #4: Track the confidence_override flag state before the action */
  beforeOverride?: boolean
  timestamp: string
}

interface HistoryState {
  undoStack: HistoryAction[]
  redoStack: HistoryAction[]
  push: (action: HistoryAction) => void
  undo: () => void
  redo: () => void
  canUndo: boolean
  canRedo: boolean
}

export const useHistoryStore = create<HistoryState>((set, get) => ({
  undoStack: [],
  redoStack: [],
  canUndo: false,
  canRedo: false,

  push: (action) => {
    set((state) => ({
      undoStack: [...state.undoStack.slice(-50), action], // Keep last 50
      redoStack: [], // Clear redo on new action
      canUndo: true,
      canRedo: false,
    }))
  },

  undo: () => {
    const state = get()
    if (state.undoStack.length === 0) return

    const action = state.undoStack[state.undoStack.length - 1]
    const graph = useGraphStore.getState()

    // Apply the reverse
    switch (action.type) {
      case 'override_confidence':
        // Bug #4: Restore the actual override flag, not a guess based on value
        graph.updateNode(action.nodeId, { confidence: action.before as number, confidence_override: action.beforeOverride ?? false })
        break
      case 'toggle_dead_end':
        graph.updateNode(action.nodeId, { is_dead_end: action.before as boolean })
        break
      case 'set_notes':
        graph.setInvestigatorNotes(action.nodeId, action.before as string)
        break
    }

    set((state) => ({
      undoStack: state.undoStack.slice(0, -1),
      redoStack: [...state.redoStack, action],
      canUndo: state.undoStack.length > 1, // Correct: state is pre-update, after slice(-1) there's length-1 items
      canRedo: true,
    }))
  },

  redo: () => {
    const state = get()
    if (state.redoStack.length === 0) return

    const action = state.redoStack[state.redoStack.length - 1]
    const graph = useGraphStore.getState()

    // Re-apply the action
    switch (action.type) {
      case 'override_confidence':
        graph.updateNode(action.nodeId, { confidence: action.after as number, confidence_override: true })
        break
      case 'toggle_dead_end':
        graph.updateNode(action.nodeId, { is_dead_end: action.after as boolean })
        break
      case 'set_notes':
        graph.setInvestigatorNotes(action.nodeId, action.after as string)
        break
    }

    set((state) => ({
      redoStack: state.redoStack.slice(0, -1),
      undoStack: [...state.undoStack, action],
      canUndo: true,
      canRedo: state.redoStack.length > 1,
    }))
  },
}))
