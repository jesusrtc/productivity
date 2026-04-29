import { api } from './client'
import type { Alert, AlertSummary, AlertFilters } from '../types/alert'

/** Build URL search params from filters */
export function buildFilterParams(filters: AlertFilters): string {
  const params = new URLSearchParams()
  if (filters.status?.length) params.set('status', filters.status.join(','))
  if (filters.severity?.length) params.set('severity', filters.severity.join(','))
  if (filters.source?.length) params.set('source', filters.source.join(','))
  if (filters.alert_type) params.set('alert_type', filters.alert_type)
  if (filters.assignee) params.set('assignee', filters.assignee)
  if (filters.search) params.set('search', filters.search)
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  return params.toString()
}

export const alertsApi = {
  list: (filters?: AlertFilters) =>
    api.get<AlertSummary[]>(`/api/alerts${filters ? '?' + buildFilterParams(filters) : ''}`),
  get: (id: string) => api.get<Alert>(`/api/alerts/${id}`),
  create: (data: Partial<Alert> & { title: string }) =>
    api.post<Alert>('/api/alerts', data),
  update: (id: string, data: Partial<Alert>) =>
    api.patch<Alert>(`/api/alerts/${id}`, data),
  delete: (id: string) =>
    api.delete<{ success: boolean }>(`/api/alerts/${id}`),
  related: (id: string) =>
    api.get<AlertSummary[]>(`/api/alerts/${id}/related`),
  sync: (lookbackDays?: number) =>
    api.post<{ imported: number; errors: string[] }>('/api/alerts/sync', {
      lookbackDays: lookbackDays || 7,
    }),
  syncStatus: () =>
    api.get<{ lastSync: string | null; syncing: boolean; error: string | null }>(
      '/api/alerts/sync/status'
    ),
}
