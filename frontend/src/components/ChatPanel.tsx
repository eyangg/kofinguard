import { marked } from 'marked'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
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
        <span className="boan-note">여러 탐지기를 동시에 돌리는 중이에요.</span>
        <span className="boan-note">최초 실행은 모델을 메모리에 올리느라 더 걸릴 수 있어요.</span>
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
  elapsedMs?: number // 전송~응답까지 걸린 시간 (방어 판단 근거에 표시)
}

export function ChatPanel({
  mode,
  turns,
  onConfirmed,
}: {
  mode: Mode
  turns: PanelState[]
  onConfirmed: () => void
}) {
  const isOff = mode === 'off'
  const scrollRef = useRef<HTMLDivElement>(null)
  // 새 턴이 쌓이거나 답변이 채워지면 항상 맨 아래(최신)로 스크롤한다.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns])
  return (
    <section className={`panel ${mode}`}>
      <header>
        <span className={`badge ${mode}`}>{isOff ? '방어 OFF' : '방어 ON'}</span>
        <span className="desc">{isOff ? '보안 장치 없음 (취약)' : '다층 방어 적용'}</span>
      </header>

      <div className="messages" ref={scrollRef}>
        {turns.map((state, i) => (
          <Turn key={i} mode={mode} state={state} onConfirmed={onConfirmed} />
        ))}
        {turns.length === 0 && (
          <div className="placeholder">메시지를 보내면 여기에 답변이 표시됩니다.</div>
        )}
      </div>
    </section>
  )
}

// 한 번의 주고받기(사용자 메시지 + 답변/로딩/오류)를 그린다. 여러 턴이 위로 쌓인다.
function Turn({ mode, state, onConfirmed }: { mode: Mode; state: PanelState; onConfirmed: () => void }) {
  const isOff = mode === 'off'
  return (
    <>
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
      {state.result && (
        <BotReply mode={mode} result={state.result} onConfirmed={onConfirmed} elapsedMs={state.elapsedMs} />
      )}
    </>
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

// 방어 OFF용 렌더. 모델 답변을 '실제 HTML'로 그려 S2 XSS를 재현한다.
// marked는 onerror 같은 비정형 속성이 든 태그를 escape(글자화)해 버려 실행이 안 되므로,
// 원본 HTML 태그(<img onerror=…> 등)만 잠시 빼뒀다가 marked 처리 후 되돌려 넣는다.
// 그러면 표 같은 마크다운은 그대로 렌더되고, 숨은 태그는 innerHTML에서 브라우저가 실행한다.
function offHtml(reply: string): string {
  const tags: string[] = []
  const held = reply.replace(/<[^>]+>/g, (m) => `@@RAW${tags.push(m) - 1}@@`)
  const rendered = marked.parse(held, { async: false }) as string
  return rendered.replace(/@@RAW(\d+)@@/g, (_m, i) => tags[Number(i)] ?? '')
}

function Markdown({ mode, text }: { mode: Mode; text: string }) {
  if (mode === 'off') {
    // 로그인 뒤에서만, 로컬/배포 CSP로 외부 유출이 격리된 상태에서만 쓴다.
    // 고객 화면엔 아무 티가 안 나고(공격의 본질), 실제 유출은 별도 '공격자 콘솔'에서 확인한다.
    return <div className="reply" dangerouslySetInnerHTML={{ __html: offHtml(text) }} />
  }
  // 방어 ON: 마크다운만 렌더하고 원본 HTML은 실행하지 않는다(코드는 글자로만 보인다).
  return (
    <div className="reply">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  )
}

function BotReply({
  mode,
  result,
  onConfirmed,
  elapsedMs,
}: {
  mode: Mode
  result: ChatResponse
  onConfirmed: () => void
  elapsedMs?: number
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
          <TracePanel trace={result.trace} elapsedMs={elapsedMs} />
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
