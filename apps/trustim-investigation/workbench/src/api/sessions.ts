import { api } from './client'
import type { Session, SessionSummary } from '../types'

export const sessionsApi = {
  list: () => api.get<SessionSummary[]>('/api/sessions'),
  get: (id: string) => api.get<Session>(`/api/sessions/${id}`),
  save: (id: string, data: unknown) =>
    api.put<{ success: boolean }>(`/api/sessions/${id}`, data),
  delete: (id: string) =>
    api.delete<{ success: boolean }>(`/api/sessions/${id}`),
}
