import { api } from './client'
import type { Skill, SkillInventory } from '../types/skill'
import type { McpToolStatus } from '../types/session'

export const miscApi = {
  listTemplates: () => api.get<any[]>('/api/templates'),
  createTemplate: (data: any) =>
    api.post<{ success: boolean; id: string }>('/api/templates', data),
  deleteTemplate: (id: string) =>
    api.delete<{ success: boolean }>(`/api/templates/${id}`),
  listQueries: () => api.get<any[]>('/api/queries'),
  exportAll: () => api.get<any>('/api/export/all'),
  exportJson: (data: any) =>
    api.post<any>('/api/export/json', data),
  seedDemo: () =>
    api.post<{ success: boolean; seeded: { alerts: number; playbooks: number } }>('/api/seed-demo'),
  listSkills: () => api.get<SkillInventory>('/api/skills'),
  getSkill: (name: string) => api.get<Skill & { content: string }>(`/api/skills/${name}`),
  listIocs: () => api.get<{ count: number; iocs: any[] }>('/api/iocs'),
  addIocs: (iocs: Array<{ type: string; value: string }>, sessionId: string) =>
    api.post<{ success: boolean; added: number; total: number }>('/api/iocs', { iocs, sessionId }),
  checkIoc: (value: string) =>
    api.get<{ found: boolean; matches: any[] }>(
      `/api/iocs/check?value=${encodeURIComponent(value)}`
    ),
  appendNotebook: (data: any) =>
    api.post<{ success: boolean; path: string; notebook: string }>('/api/notebook/append', data),
  mcpTools: () => api.get<McpToolStatus[]>('/api/mcp/tools'),
}
