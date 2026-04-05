/**
 * HTTP клиент для API запросов.
 * Все запросы проксируются через Vite: /api → localhost:8000/api
 */

const BASE_URL = '/api'

/** Получить JWT token из localStorage (Supabase сессия) */
function getAuthToken(): string | null {
  // Supabase хранит сессию как JSON
  const raw = localStorage.getItem('sb-auth-token')
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      return parsed.access_token ?? null
    } catch {
      return null
    }
  }
  return null
}

/** Базовый fetch с авторизацией и обработкой ошибок */
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getAuthToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> ?? {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, body.detail ?? response.statusText)
  }

  // 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`API Error ${status}: ${detail}`)
    this.name = 'ApiError'
  }
}
