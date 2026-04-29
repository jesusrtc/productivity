import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock fetch globally
const mockFetch = vi.fn()

// Mock the toast store
const mockAddToast = vi.fn()
vi.mock('../store/toast', () => ({
  useToastStore: {
    getState: () => ({ addToast: mockAddToast }),
  },
}))

// Must import AFTER mocks are set up
import { api, ApiError } from '../api/client'

beforeEach(() => {
  globalThis.fetch = mockFetch
  mockFetch.mockReset()
  mockAddToast.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('api.get', () => {
  it('returns parsed JSON on 200', async () => {
    const data = { id: '1', name: 'test' }
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
    })

    const result = await api.get('/api/sessions')

    expect(mockFetch).toHaveBeenCalledWith('/api/sessions', {
      headers: { 'Content-Type': 'application/json' },
    })
    expect(result).toEqual(data)
  })
})

describe('api.post', () => {
  it('sends JSON body with Content-Type', async () => {
    const body = { title: 'New Alert' }
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: '1' }),
    })

    await api.post('/api/alerts', body)

    expect(mockFetch).toHaveBeenCalledWith('/api/alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  })

  it('omits body when no body provided', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })

    await api.post('/api/alerts/sync')

    expect(mockFetch).toHaveBeenCalledWith('/api/alerts/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: undefined,
    })
  })
})

describe('api.delete', () => {
  it('sends DELETE method', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    })

    await api.delete('/api/sessions/abc')

    expect(mockFetch).toHaveBeenCalledWith('/api/sessions/abc', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
    })
  })
})

describe('api.patch', () => {
  it('sends PATCH method with body', async () => {
    const body = { status: 'resolved' }
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: '1' }),
    })

    await api.patch('/api/alerts/1', body)

    expect(mockFetch).toHaveBeenCalledWith('/api/alerts/1', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  })
})

describe('error handling', () => {
  it('throws ApiError on 500 and shows toast', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: () => Promise.resolve('server down'),
    })

    await expect(api.get('/api/sessions')).rejects.toThrow(ApiError)

    try {
      await api.get('/api/sessions')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(500)
      expect((e as ApiError).message).toBe('server down')
    }

    expect(mockAddToast).toHaveBeenCalledWith(
      'API error: server down',
      'error',
      5000
    )
  })

  it('throws ApiError on 404 without toast', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      text: () => Promise.resolve('not found'),
    })

    await expect(api.get('/api/sessions/missing')).rejects.toThrow(ApiError)

    try {
      await api.get('/api/sessions/missing')
    } catch (e) {
      expect((e as ApiError).status).toBe(404)
    }

    expect(mockAddToast).not.toHaveBeenCalled()
  })
})
