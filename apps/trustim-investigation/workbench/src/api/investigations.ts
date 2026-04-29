import { api } from './client'

export interface BackgroundInvestigation {
  id: string
  sessionId: string
  prompt: string
  status: string
  nodeCount: number
  startedAt: string
  alertId?: string
  sessionName?: string
  [key: string]: unknown
}

export const investigationsApi = {
  list: () => api.get<BackgroundInvestigation[]>('/api/investigations'),
  get: (sessionId: string) =>
    api.get<BackgroundInvestigation>(`/api/investigations/${sessionId}`),
  start: (sessionId: string, prompt: string, alertId?: string, sessionName?: string) =>
    api.post<BackgroundInvestigation>('/api/investigations/start', {
      sessionId,
      prompt,
      alertId,
      sessionName,
    }),
  stop: (sessionId: string) =>
    api.delete<{ stopped: boolean }>(`/api/investigations/${sessionId}`),
  resume: (sessionId: string) =>
    api.post<{ resumed: boolean }>(`/api/investigations/${sessionId}/resume`),
}
