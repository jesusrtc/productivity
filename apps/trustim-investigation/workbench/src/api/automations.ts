import { api } from './client'
import type { Automation, AutomationSummary, ExecutionResult } from '../types/automation'

export const automationsApi = {
  list: (filters?: { category?: string; exec_type?: string; search?: string }) => {
    const params = new URLSearchParams()
    if (filters?.category) params.set('category', filters.category)
    if (filters?.exec_type) params.set('exec_type', filters.exec_type)
    if (filters?.search) params.set('search', filters.search)
    return api.get<AutomationSummary[]>(`/api/automations?${params}`)
  },
  get: (id: string) => api.get<Automation>(`/api/automations/${id}`),
  create: (data: Partial<Automation> & { name: string }) =>
    api.post<Automation>('/api/automations', data),
  update: (id: string, data: Partial<Automation>) =>
    api.put<Automation>(`/api/automations/${id}`, data),
  delete: (id: string) =>
    api.delete<{ success: boolean }>(`/api/automations/${id}`),
  run: (id: string, inputs: Record<string, unknown>) =>
    api.post<ExecutionResult>(`/api/automations/${id}/run`, { inputs }),
  migrate: () =>
    api.post<{ migrated: number; errors: string[] }>('/api/automations/migrate'),
}
