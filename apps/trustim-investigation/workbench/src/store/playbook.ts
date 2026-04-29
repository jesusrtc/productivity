import { create } from 'zustand'
import { playbooksApi } from '../api'
import type { Playbook, PlaybookExecution } from '../types/playbook'

interface PlaybookState {
  playbooks: Playbook[]
  loading: boolean
  activeExecution: PlaybookExecution | null

  fetchPlaybooks: () => Promise<void>
  fetchPlaybook: (id: string) => Promise<Playbook | null>
  createPlaybook: (data: Omit<Playbook, 'id' | 'created_at' | 'updated_at' | 'version'>) => Promise<Playbook | null>
  updatePlaybook: (id: string, data: Partial<Playbook>) => Promise<boolean>
  deletePlaybook: (id: string) => Promise<boolean>
  runPlaybook: (id: string, inputs: Record<string, unknown>, sessionId: string) => Promise<PlaybookExecution | null>
  cancelExecution: (execId: string) => Promise<boolean>
  pollExecution: (execId: string) => Promise<PlaybookExecution | null>
}

export const usePlaybookStore = create<PlaybookState>((set, get) => ({
  playbooks: [],
  loading: false,
  activeExecution: null,

  fetchPlaybooks: async () => {
    set({ loading: true })
    try {
      const data = await playbooksApi.list()
      set({ playbooks: Array.isArray(data) ? data : [], loading: false })
    } catch {
      set({ loading: false })
    }
  },

  fetchPlaybook: async (id) => {
    try {
      return await playbooksApi.get(id)
    } catch { return null }
  },

  createPlaybook: async (data) => {
    try {
      const pb = await playbooksApi.create(data)
      get().fetchPlaybooks()
      return pb
    } catch { return null }
  },

  updatePlaybook: async (id, data) => {
    try {
      await playbooksApi.update(id, data)
      get().fetchPlaybooks()
      return true
    } catch { return false }
  },

  deletePlaybook: async (id) => {
    try {
      await playbooksApi.delete(id)
      get().fetchPlaybooks()
      return true
    } catch { return false }
  },

  runPlaybook: async (id, inputs, sessionId) => {
    try {
      const exec = await playbooksApi.run(id, inputs, sessionId)
      set({ activeExecution: exec })
      return exec
    } catch { return null }
  },

  cancelExecution: async (execId) => {
    try {
      await playbooksApi.cancelExecution(execId)
      set({ activeExecution: null })
      return true
    } catch { return false }
  },

  pollExecution: async (execId) => {
    try {
      const exec = await playbooksApi.getExecution(execId)
      set({ activeExecution: exec })
      return exec
    } catch { return null }
  },
}))
