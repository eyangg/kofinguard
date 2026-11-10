import type { Account, ChatResponse, EvalLatest, Me, Mode, Preset } from './types'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// 배포 시 프론트(Cloudflare)와 백엔드(Lightsail)는 다른 출처다. VITE_API_BASE로 백엔드 주소를 받고,
// 로컬 개발에서는 비워 두면 '' → '/api/...'가 Vite 프록시로 백엔드에 전달된다.
const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

// 사용자에게 보여줄 오류 문장. 백엔드가 JSON으로 detail을 주면 그 문구를 우선 쓰고(아래 errorFrom),
// 그렇지 않은 경우(네트워크 끊김, 프록시·정적 서버가 준 비-JSON 응답 등 인프라 오류)에만 이 문장으로 안내한다.
// status 0 = fetch 자체가 실패(네트워크).
function friendlyMessage(status: number): string {
  if (status === 0) return '서버에 연결할 수 없어요. 네트워크 상태를 확인하고 다시 시도해 주세요.'
  if (status === 401 || status === 403) return '로그인이 필요하거나 세션이 만료되었어요. 다시 로그인해 주세요.'
  if (status === 404 || status === 405) return '요청을 처리할 수 없어요. 페이지를 새로고침한 뒤 다시 시도해 주세요.'
  if (status === 429) return '요청이 잠시 많아요. 잠시 후 다시 시도해 주세요.'
  if (status >= 500) return '서버에 일시적인 문제가 있어요. 잠시 후 다시 시도해 주세요.'
  return '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.'
}

async function fetchJson(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch {
    throw new ApiError(0, friendlyMessage(0)) // 네트워크 실패도 ApiError로 통일해 화면에 문장으로 보인다
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  let detail = friendlyMessage(res.status)
  try {
    const body = (await res.json()) as { detail?: string }
    if (body.detail) detail = body.detail // 백엔드가 준 안내 문구가 있으면 그걸 우선
  } catch {
    /* 본문이 JSON이 아님(프록시·정적 서버 응답 등) → friendlyMessage 유지 */
  }
  return new ApiError(res.status, detail)
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetchJson(API_BASE + path, {
    ...options,
    credentials: 'include', // 교차 출처에서도 세션 쿠키를 보낸다 (백엔드는 SameSite=None 쿠키 사용)
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  })
  if (!res.ok) throw await errorFrom(res)
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
    const res = await fetchJson(API_BASE + '/api/attachments', { method: 'POST', body: form, credentials: 'include' })
    if (!res.ok) throw await errorFrom(res)
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
  evalLatest: () => req<EvalLatest>('/api/demo/eval'),
}

export { ApiError }
