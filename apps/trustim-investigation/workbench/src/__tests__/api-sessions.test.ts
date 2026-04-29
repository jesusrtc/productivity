import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetch = vi.fn()
vi.mock('../store/toast', () => ({
  useToastStore: { getState: () => ({ addToast: vi.fn() }) },
}))

import { sessionsApi } from '../api/sessions'

beforeEach(() => {
  globalThis.fetch = mockFetch
  mockFetch.mockReset()
  mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve([]) })
})

describe('sessionsApi', () => {
  it('list() calls GET /api/sessions', async () => {
    await sessionsApi.list()

    expect(mockFetch).toHaveBeenCalledWith('/api/sessions', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('get(id) calls GET /api/sessions/:id', async () => {
    await sessionsApi.get('abc')

    expect(mockFetch).toHaveBeenCalledWith('/api/sessions/abc', {
      headers: { 'Content-Type': 'application/json' },
    })
  })

  it('save(id, data) calls PUT /api/sessions/:id with JSON body', async () => {
    const data = { name: 'test session' }
    await sessionsApi.save('abc', data)

    expect(mockFetch).toHaveBeenCalledWith('/api/sessions/abc', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
  })

  it('delete(id) calls DELETE /api/sessions/:id', async () => {
    await sessionsApi.delete('abc')

    expect(mockFetch).toHaveBeenCalledWith('/api/sessions/abc', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
    })
  })
})
