import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import remarkGfm from 'remark-gfm'
import { ApiError, api } from '../api'
import type { ChatResponse, Mode } from '../types'
import { TracePanel } from './TracePanel'

// ON 보안 검사는 수십 초 걸려서, 기다리는 동안 단계별 진행 메시지를 돌린다.
// D-02(SmoothPPL)·D-03(Llama Guard)은 서버에서 병렬로 돌므로 한 단계로 묶어 보여 준다.
const BOAN_STEPS = [
  '입력 문장 정리 중…',
  'SmoothPPL · Llama Guard 동시 검사 중…',
  '답변에 숨은 코드 확인 중…',
  '마무리 중…',
]

function SecurityLoader() {
  const [i, setI] = useState(0)
  const [sec, setSec] = useState(0)
  useEffect(() => {
    const step = setInterval(() => setI((v) => (v + 1 < BOAN_STEPS.length ? v + 1 : v)), 2500)
    const clock = setInterval(() => setSec((s) => s + 1), 1000)
    return () => {
      clearInterval(step)
      clearInterval(clock)
    }
  }, [])
  return (
    <div className="msg bot loading boan">
      <span className="ring-spinner" aria-hidden="true">
        {Array.from({ length: 12 }).map((_, k) => (
          <i key={k} style={{ transform: `rotate(${k * 30}deg)`, animationDelay: `${(k - 12) / 12}s` }} />
        ))}
      </span>
      <div className="boan-body">
        <span className="boan-title">보안 검사 중 · {sec}초</span>
        <span className="boan-step">{BOAN_STEPS[i]}</span>
        <span className="boan-note">여러 탐지기를 동시에 돌리는 중이에요. 최초 실행은 모델을 메모리에 올리느라 더 걸릴 수 있어요.</span>
      </div>
    </div>
  )
}

export type PanelState = {
  loading: boolean
  user?: string
  attachment?: string // 첨부 파일명 (S2 청구서 등)
  result?: ChatResponse
  error?: string
}

export function ChatPanel({
  mode,
  state,
  onConfirmed,
  children,
}: {
  mode: Mode
  state: PanelState
  onConfirmed: () => void
  children?: React.ReactNode
}) {
  const isOff = mode === 'off'
  const empty = !state.user && !state.loading && !state.result && !state.error
  return (
    <section className={`panel ${mode}`}>
      <header>
        <span className={`badge ${mode}`}>{isOff ? '방어 OFF' : '방어 ON'}</span>
        <span className="desc">{isOff ? '보안 장치 없음 (취약)' : '다층 방어 적용'}</span>
      </header>

      <div className="messages">
        {state.user && (
          <div className="user-block">
            <div className="msg user">{state.user}</div>
            {state.attachment && (
              <div className="attach-chip">
                <span className="attach-icon" aria-hidden="true">📎</span>
                {state.attachment}
                <span className="attach-note">첨부됨</span>
              </div>
            )}
          </div>
        )}
        {state.loading &&
          (isOff ? (
            <div className="msg bot loading">
              <span className="spinner" aria-hidden="true" />
              답변 생성 중…
            </div>
          ) : (
            <SecurityLoader />
          ))}
        {state.error && <div className="msg error">오류: {state.error}</div>}
        {state.result && <BotReply mode={mode} result={state.result} onConfirmed={onConfirmed} />}
        {empty && !children && <div className="placeholder">메시지를 보내면 여기에 답변이 표시됩니다.</div>}
        {children}
      </div>
    </section>
  )
}

// 답변을 '표'와 '그 외 글' 블록으로 쪼갠다 → 안내 문장과 표가 따로 말풍선으로 나온다.
function splitReply(reply: string): string[] {
  const isTableLine = (l: string) => /^\s*\|/.test(l)
  const segments: string[] = []
  let buf: string[] = []
  let inTable = false
  const flush = () => {
    const text = buf.join('\n').trim()
    if (text) segments.push(text)
    buf = []
  }
  for (const line of reply.split('\n')) {
    const t = isTableLine(line)
    if (t !== inTable) {
      flush()
      inTable = t
    }
    buf.push(line)
  }
  flush()
  return segments.length > 0 ? segments : [reply]
}

function Markdown({ mode, text }: { mode: Mode; text: string }) {
  // OFF는 원본 HTML까지 렌더(S2 공격 재현), ON은 마크다운만(코드는 글자로만).
  return (
    <div className="reply">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={mode === 'off' ? [rehypeRaw] : []}>
        {text}
      </ReactMarkdown>
    </div>
  )
}

function BotReply({
  mode,
  result,
  onConfirmed,
}: {
  mode: Mode
  result: ChatResponse
  onConfirmed: () => void
}) {
  const segments = splitReply(result.reply)
  return (
    <>
      {segments.map((seg, i) => (
        <div className="msg bot" key={i}>
          <Markdown mode={mode} text={seg} />
        </div>
      ))}
      {(result.pending_transfer || result.trace.length > 0) && (
        <div className="msg bot">
          {result.pending_transfer && <PendingCard pending={result.pending_transfer} onConfirmed={onConfirmed} />}
          <TracePanel trace={result.trace} />
        </div>
      )}
    </>
  )
}

function PendingCard({
  pending,
  onConfirmed,
}: {
  pending: NonNullable<ChatResponse['pending_transfer']>
  onConfirmed: () => void
}) {
  async function confirm() {
    try {
      await api.confirmTransfer(pending.id)
      onConfirmed()
    } catch (err) {
      alert(err instanceof ApiError ? err.message : '송금 확인에 실패했습니다')
    }
  }
  return (
    <div className="pending">
      <strong>송금 대기</strong>
      <div>
        {pending.to_name} ({pending.to_account}) 앞 {pending.amount.toLocaleString()}원
      </div>
      <button type="button" onClick={confirm}>
        [확인] 눌러서 송금 실행
      </button>
      <p className="note">사람이 눌러야만 실행됩니다 (챗봇은 실행 불가)</p>
    </div>
  )
}
