import { create } from 'zustand'
import { alertsApi } from '../api'
import type { Alert, AlertSummary, AlertFilters, AlertStatus, AlertIOC } from '../types/alert'

interface AlertState {
  alerts: AlertSummary[]
  selectedAlertId: string | null
  filters: AlertFilters
  loading: boolean
  /** Sync status for InResponse integration */
  syncStatus: { lastSync: string | null; syncing: boolean; error: string | null }

  // Fetch
  fetchAlerts: () => Promise<void>
  fetchAlert: (id: string) => Promise<Alert | null>

  // CRUD
  createAlert: (data: Partial<Alert> & { title: string }) => Promise<Alert | null>
  updateAlert: (id: string, updates: Partial<Alert>) => Promise<boolean>
  deleteAlert: (id: string) => Promise<boolean>

  // Lifecycle
  transitionStatus: (id: string, status: AlertStatus) => Promise<boolean>
  linkSession: (alertId: string, sessionId: string) => Promise<boolean>

  // Cross-alert context
  fetchRelated: (alertId: string) => Promise<AlertSummary[]>

  // Sync
  triggerSync: () => Promise<void>

  // UI
  selectAlert: (id: string | null) => void
  setFilters: (filters: Partial<AlertFilters>) => void
  clearFilters: () => void
}

export const useAlertStore = create<AlertState>((set, get) => ({
  alerts: [],
  selectedAlertId: null,
  filters: {},
  loading: false,
  syncStatus: { lastSync: null, syncing: false, error: null },

  fetchAlerts: async () => {
    set({ loading: true })
    try {
      const data = await alertsApi.list(get().filters)
      set({ alerts: Array.isArray(data) ? data : [], loading: false })
    } catch {
      set({ loading: false })
    }
  },

  fetchAlert: async (id) => {
    try {
      return await alertsApi.get(id)
    } catch {
      return null
    }
  },

  createAlert: async (data) => {
    try {
      const alert = await alertsApi.create(data)
      if (alert?.id) {
        get().fetchAlerts()
        return alert
      }
      return null
    } catch {
      return null
    }
  },

  updateAlert: async (id, updates) => {
    try {
      await alertsApi.update(id, updates)
      get().fetchAlerts()
      return true
    } catch {
      return false
    }
  },

  deleteAlert: async (id) => {
    try {
      await alertsApi.delete(id)
      set(s => ({ alerts: s.alerts.filter(a => a.id !== id) }))
      return true
    } catch {
      return false
    }
  },

  transitionStatus: async (id, status) => {
    return get().updateAlert(id, {
      status,
      ...(status === 'resolved' ? { resolved_at: new Date().toISOString() } : {}),
    })
  },

  linkSession: async (alertId, sessionId) => {
    const alert = await get().fetchAlert(alertId)
    if (!alert) return false
    const sessionIds = alert.session_ids.includes(sessionId)
      ? alert.session_ids
      : [...alert.session_ids, sessionId]
    return get().updateAlert(alertId, { session_ids: sessionIds })
  },

  fetchRelated: async (alertId) => {
    try {
      const data = await alertsApi.related(alertId)
      return Array.isArray(data) ? data : []
    } catch {
      return []
    }
  },

  triggerSync: async () => {
    set(s => ({ syncStatus: { ...s.syncStatus, syncing: true, error: null } }))
    try {
      await alertsApi.sync(7)
      set({ syncStatus: { lastSync: new Date().toISOString(), syncing: false, error: null } })
      get().fetchAlerts()
    } catch {
      set(s => ({ syncStatus: { ...s.syncStatus, syncing: false, error: 'Sync failed' } }))
    }
  },

  selectAlert: (id) => set({ selectedAlertId: id }),

  setFilters: (filters) => {
    set(s => ({ filters: { ...s.filters, ...filters } }))
    get().fetchAlerts()
  },

  clearFilters: () => {
    set({ filters: {} })
    get().fetchAlerts()
  },
}))
