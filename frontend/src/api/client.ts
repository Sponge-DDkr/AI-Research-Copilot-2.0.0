import type { ChatRequest, ChatResponse } from '../types'

const BASE_URL = '/api'

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '请求失败' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/** 发送聊天消息 */
export async function sendMessage(message: string): Promise<ChatResponse> {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify({ message } satisfies ChatRequest),
  })
}

/** 健康检查 */
export async function healthCheck(): Promise<{
  status: string
  model?: string
  message?: string
}> {
  return request('/chat/health')
}
