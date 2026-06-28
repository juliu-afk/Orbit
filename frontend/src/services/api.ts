/** 统一 HTTP API 客户端。

 * P2-3: 消除 compose/dream 组件中分散的 fetch 调用,
 * 提供统一的错误处理和类型安全。
 */
const BASE = window.location.origin

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** POST JSON → 解析 {code, data, message} 响应。非 2xx 或 code≠0 抛 ApiError。 */
export async function apiPost<T = unknown>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    throw new ApiError(`HTTP ${resp.status}`, resp.status, -1)
  }
  const json = await resp.json()
  if (json.code !== 0) {
    throw new ApiError(json.message || '请求失败', resp.status, json.code ?? -1)
  }
  return json.data as T
}

/** GET JSON → 解析 {code, data, message} 响应。 */
export async function apiGet<T = unknown>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) {
    throw new ApiError(`HTTP ${resp.status}`, resp.status, -1)
  }
  const json = await resp.json()
  if (json.code !== 0) {
    throw new ApiError(json.message || '请求失败', resp.status, json.code ?? -1)
  }
  return json.data as T
}
