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
}

export type AttackerLogEntry = {
  time: string
  method: string
  path: string
  query: Record<string, unknown>
}

export type Mode = 'off' | 'on'
