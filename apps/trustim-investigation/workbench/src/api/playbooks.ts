import { api } from './client'
import type { Playbook, PlaybookExecution } from '../types/playbook'

export const playbooksApi = {
  list: () => api.get<Playbook[]>('/api/playbooks'),
  get: (id: string) => api.get<Playbook>(`/api/playbooks/${id}`),
  create: (data: Partial<Playbook> & { name: string }) =>
    api.post<Playbook>('/api/playbooks', data),
  update: (id: string, data: Partial<Playbook>) =>
    api.put<Playbook>(`/api/playbooks/${id}`, data),
  delete: (id: string) =>
    api.delete<{ success: boolean }>(`/api/playbooks/${id}`),
  run: (id: string, inputs: Record<string, unknown>, sessionId: string) =>
    api.post<PlaybookExecution>(`/api/playbooks/${id}/run`, { inputs, sessionId }),
  listExecutions: () =>
    api.get<PlaybookExecution[]>('/api/playbook-executions'),
  getExecution: (id: string) =>
    api.get<PlaybookExecution>(`/api/playbook-executions/${id}`),
  cancelExecution: (id: string) =>
    api.post<{ success: boolean }>(`/api/playbook-executions/${id}/cancel`),
}
