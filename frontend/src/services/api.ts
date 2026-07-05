/** 统一 HTTP API 客户端。

 * P2-1: 添加请求超时（30s）和 AbortController 取消机制。
 */
const BASE = window.location.origin
const DEFAULT_TIMEOUT_MS = 30_000

export class ApiError extends Error {
  constructor(message: string, public status: number, public code: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
  try {
    const resp = await fetch(`${BASE}${path}`, { ...init, signal: controller.signal })
    if (!resp.ok) throw new ApiError(`HTTP ${resp.status}`, resp.status, -1)
    const json = await resp.json()
    if (json.code !== 0) throw new ApiError(json.message || '请求失败', resp.status, json.code ?? -1)
    return json.data as T
  } finally {
    clearTimeout(timer)
  }
}

export async function apiPost<T = unknown>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

export async function apiPut<T = unknown>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
