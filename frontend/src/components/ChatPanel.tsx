import { ApiError, api } from '../api'
import type { ChatResponse, Mode } from '../types'
import { TracePanel } from './TracePanel'

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
        {state.loading && (
          <div className="msg bot loading">
            <span className="spinner" aria-hidden="true" />
            {isOff ? '답변 생성 중…' : '보안 검사 중… (SmoothPPL·Llama Guard, 수십 초 걸릴 수 있어요)'}
          </div>
        )}
        {state.error && <div className="msg error">오류: {state.error}</div>}
        {state.result && <BotReply mode={mode} result={state.result} onConfirmed={onConfirmed} />}
        {empty && !children && <div className="placeholder">메시지를 보내면 여기에 답변이 표시됩니다.</div>}
        {children}
      </div>
    </section>
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
  return (
    <div className="msg bot">
      {mode === 'off' ? (
        // OFF 화면은 답변을 HTML로 그린다 — S2 공격 재현용. 127.0.0.1 로컬 시연 전용이라 의도적이다.
        <div className="reply" dangerouslySetInnerHTML={{ __html: result.reply }} />
      ) : (
        // ON 화면은 답변을 글자로만 그린다 (실행 안 됨).
        <div className="reply">{result.reply}</div>
      )}
      {result.pending_transfer && <PendingCard pending={result.pending_transfer} onConfirmed={onConfirmed} />}
      <TracePanel trace={result.trace} />
    </div>
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
