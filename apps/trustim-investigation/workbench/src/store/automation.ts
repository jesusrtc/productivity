import { create } from 'zustand'
import { automationsApi } from '../api'
import type { Automation, AutomationSummary, ExecutionResult } from '../types/automation'

interface AutomationFilters {
  category?: string
  exec_type?: string
  search?: string
}

interface AutomationState {
  automations: AutomationSummary[]
  loading: boolean
  filters: AutomationFilters

  fetchAutomations: () => Promise<void>
  fetchAutomation: (id: string) => Promise<Automation | null>
  createAutomation: (data: Omit<Automation, 'id' | 'created_at' | 'updated_at'>) => Promise<Automation | null>
  updateAutomation: (id: string, data: Partial<Automation>) => Promise<boolean>
  deleteAutomation: (id: string) => Promise<boolean>
  runAutomation: (id: string, inputs: Record<string, unknown>) => Promise<ExecutionResult | null>
  migrateSkills: () => Promise<{ migrated: number; errors: string[] }>
  setFilters: (filters: AutomationFilters) => void
}

export const useAutomationStore = create<AutomationState>((set, get) => ({
  automations: [],
  loading: false,
  filters: {},

  fetchAutomations: async () => {
    set({ loading: true })
    try {
      const data = await automationsApi.list(get().filters)
      set({ automations: Array.isArray(data) ? data : [], loading: false })
    } catch {
      set({ loading: false })
    }
  },

  fetchAutomation: async (id) => {
    try {
      return await automationsApi.get(id)
    } catch { return null }
  },

  createAutomation: async (data) => {
    try {
      const automation = await automationsApi.create(data)
      get().fetchAutomations()
      return automation
    } catch { return null }
  },

  updateAutomation: async (id, data) => {
    try {
      await automationsApi.update(id, data)
      get().fetchAutomations()
      return true
    } catch { return false }
  },

  deleteAutomation: async (id) => {
    try {
      await automationsApi.delete(id)
      get().fetchAutomations()
      return true
    } catch { return false }
  },

  runAutomation: async (id, inputs) => {
    try {
      return await automationsApi.run(id, inputs)
    } catch { return null }
  },

  migrateSkills: async () => {
    try {
      const result = await automationsApi.migrate()
      get().fetchAutomations()
      return result
    } catch { return { migrated: 0, errors: ['Network error'] } }
  },

  setFilters: (filters) => {
    set({ filters })
    get().fetchAutomations()
  },
}))
