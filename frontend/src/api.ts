import type {
  Account,
  AttackerLogEntry,
  ChatResponse,
  EvalLatest,
  Me,
  Mode,
  Preset,
} from './types'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* 본문이 JSON이 아닐 수 있다 */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export const api = {
  login: (login_id: string, password: string) =>
    req<Me>('/api/auth/login', { method: 'POST', body: JSON.stringify({ login_id, password }) }),
  logout: () => req<{ status: string }>('/api/auth/logout', { method: 'POST' }),
  me: () => req<Me>('/api/me'),
  account: () => req<Account>('/api/accounts/me'),
  presets: () => req<Preset[]>('/api/demo/presets'),
  presetAttachment: (preset_id: string) =>
    req<{ attachment_id: number; filename: string }>('/api/demo/attachment', {
      method: 'POST',
      body: JSON.stringify({ preset_id }),
    }),
  uploadAttachment: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    // FormData는 Content-Type을 브라우저가 경계값과 함께 자동 설정하므로 직접 지정하지 않는다.
    const res = await fetch('/api/attachments', { method: 'POST', body: form })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = (await res.json()) as { detail?: string }
        if (body.detail) detail = body.detail
      } catch {
        /* JSON 아님 */
      }
      throw new ApiError(res.status, detail)
    }
    return (await res.json()) as { id: number; filename: string }
  },
  chat: (mode: Mode, message: string, attachment_id?: number) =>
    req<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ mode, message, attachment_id: attachment_id ?? null }),
    }),
  suggestions: (last_user: string, last_reply: string) =>
    req<{ suggestions: string[] }>('/api/suggestions', {
      method: 'POST',
      body: JSON.stringify({ last_user, last_reply }),
    }),
  confirmTransfer: (id: number) =>
    req<{ balance_after: number }>(`/api/transfers/${id}/confirm`, { method: 'POST' }),
  attackerLog: () => req<AttackerLogEntry[]>('/api/demo/attacker-log'),
  evalLatest: () => req<EvalLatest>('/api/demo/eval'),
}

export { ApiError }
