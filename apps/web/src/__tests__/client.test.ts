/**
 * Тесты HTTP клиента: JWT injection, error handling, 204 response.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

// Мок localStorage
const store: Record<string, string> = {}
const localStorageMock = {
  getItem: vi.fn((key: string) => store[key] ?? null),
  setItem: vi.fn((key: string, value: string) => { store[key] = value }),
  removeItem: vi.fn((key: string) => { delete store[key] }),
  clear: vi.fn(() => { Object.keys(store).forEach((k) => delete store[k]) }),
  get length() { return Object.keys(store).length },
  key: vi.fn((_: number) => null),
}
vi.stubGlobal('localStorage', localStorageMock)

// Мок fetch
const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

// Импортируем ПОСЛЕ stubGlobal
const { apiFetch, ApiError } = await import('../api/client')

beforeEach(() => {
  fetchMock.mockReset()
  localStorageMock.clear()
  localStorageMock.getItem.mockImplementation((key: string) => store[key] ?? null)
})

describe('apiFetch', () => {
  it('отправляет запрос с Content-Type json', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ data: 'ok' }),
    })

    await apiFetch('/test')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      }),
    )
  })

  it('добавляет Authorization header при наличии sb-auth-token', async () => {
    localStorage.setItem('sb-auth-token', JSON.stringify({ access_token: 'test-jwt-123' }))

    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({}),
    })

    await apiFetch('/test')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer test-jwt-123',
        }),
      }),
    )
  })

  it('не добавляет Authorization если токена нет', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({}),
    })

    await apiFetch('/test')
    const headers = fetchMock.mock.calls[0][1].headers
    expect(headers.Authorization).toBeUndefined()
  })

  it('обрабатывает невалидный JSON в localStorage', async () => {
    localStorage.setItem('sb-auth-token', 'not-json')

    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({}),
    })

    await apiFetch('/test')
    const headers = fetchMock.mock.calls[0][1].headers
    expect(headers.Authorization).toBeUndefined()
  })

  it('выбрасывает ApiError при ошибке сервера', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      json: async () => ({ detail: 'Нет доступа' }),
    })

    await expect(apiFetch('/test')).rejects.toThrow(ApiError)

    try {
      await apiFetch('/test')
    } catch (err) {
      // Уже thrown выше, нужен отдельный вызов
    }
  })

  it('ApiError содержит status и detail', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ detail: 'Документ не найден' }),
    })

    try {
      await apiFetch('/documents/123')
      expect.unreachable('Должен был выбросить ошибку')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      const apiErr = err as InstanceType<typeof ApiError>
      expect(apiErr.status).toBe(404)
      expect(apiErr.detail).toBe('Документ не найден')
    }
  })

  it('возвращает undefined для 204 No Content', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error('No body')
      },
    })

    const result = await apiFetch('/test')
    expect(result).toBeUndefined()
  })

  it('парсит JSON-ответ', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ documents: [], meta: { total: 0 } }),
    })

    const result = await apiFetch<{ documents: unknown[]; meta: { total: number } }>('/documents/')
    expect(result.documents).toEqual([])
    expect(result.meta.total).toBe(0)
  })
})
