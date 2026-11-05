export type Me = {
  id: string
  login_id: string
  name: string
  email: string
  phone: string
}

export type Account = { account_no: string; balance: number }

export type TraceEvent = {
  layer: string
  action: string
  detail: Record<string, unknown>
}

export type PendingTransfer = {
  id: number
  to_account: string
  to_name: string
  amount: number
}

export type ChatResponse = {
  reply: string
  trace: TraceEvent[]
  pending_transfer: PendingTransfer | null
}

export type Preset = {
  id: string
  label: string
  message: string
  has_attachment: boolean
  pinned: boolean // true=고정 공격 버튼(S1·S2), false=추천에 섞는 추가 공격
}

export type Mode = 'off' | 'on'

export type EvalLatest = {
  detector: {
    measured_at?: string
    env: { guard_model?: string; ppl_threshold?: number; num_samples?: number; cpu?: string }
    metrics: {
      normal_total: number
      normal_pass: number
      normal_blocked: number
      normal_reask: number
      false_positive_rate: number
      avg_sec: number
      attacks: Record<string, string>
    }
    // 공격 문장별 측정값 (판정 이유 표시용)
    attacks?: { label: string; action: string; mean_ppl?: number; guard_safe?: boolean | null }[]
  } | null
  attack: {
    measured_at?: string
    n?: number
    env: { model?: string; guard_model?: string }
    rows: { scenario: string; mode: Mode; n: number; breaches: number; rate: number }[]
  } | null
  // 탐지기 끄고 핵심 방어만 (run_attack_eval --core-only).
  // actions = 방어가 한 일('D-08 HTML 태그 인코딩' 등) → 그 일이 있었던 회차 수, quiet = 방어가 끼어들 일이 없었던 회차 수
  attack_core?: {
    measured_at?: string
    n?: number
    rows: {
      scenario: string
      mode: Mode
      n: number
      breaches: number
      rate: number
      actions?: Record<string, number>
      quiet?: number
    }[]
  } | null
}
