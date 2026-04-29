import { api } from './client'

export interface SetupCheck {
  id: string
  label: string
  status: 'ok' | 'warning' | 'error' | 'checking'
  message: string
  required: boolean
  fix?: string
}

export interface SetupResult {
  ready: boolean
  checks: SetupCheck[]
  requiredPassing: number
  requiredTotal: number
}

export const setupApi = {
  check: () => api.get<SetupResult>('/api/setup/check'),
  recheck: () => api.post<SetupResult>('/api/setup/recheck'),
  bridgeStatus: () =>
    api.get<{ available: boolean; ready: boolean; message: string }>('/api/bridge/status'),
  bridgeConfig: () => api.get<{ maxTurns: number }>('/api/bridge/config'),
  setBridgeConfig: (maxTurns: number) =>
    api.post<{ maxTurns: number }>('/api/bridge/config', { maxTurns }),
}
