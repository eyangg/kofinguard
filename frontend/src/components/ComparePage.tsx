import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api'
import type { Preset } from '../types'
import { ChatPanel, type PanelState } from './ChatPanel'

const EMPTY: PanelState = { loading: false }

type View = 'both' | 'off' | 'on'

export function ComparePage({ balance, onBalanceChange }: { balance: number | null; onBalanceChange: () => void }) {
  const [presets, setPresets] = useState<Preset[]>([])
  const [input, setInput] = useState('')
  const [off, setOff] = useState<PanelState>(EMPTY)
  const [on, setOn] = useState<PanelState>(EMPTY)
  const [sending, setSending] = useState(false)
  const [view, setView] = useState<View>('both')
  // 칩으로 채운 공격 문장. 입력을 그대로 보내면 그 프리셋의 첨부(S2 청구서)도 같이 보낸다.
  const [armed, setArmed] = useState<{ id: string; message: string } | null>(null)
  // 마지막 답변 뒤 LLM이 제안한 다음 질문(정상 후속). 공격 칩은 항상 따로 고정으로 보인다.
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [featuredAttackId, setFeaturedAttackId] = useState<string | null>(null) // 추천에 섞을 공격 1개
  const [dropAttach, setDropAttach] = useState(false) // ✕로 공격 첨부(청구서)를 취소했는지
  const [uploaded, setUploaded] = useState<{ id: number; filename: string } | null>(null) // 사용자가 직접 올린 파일
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.presets().then(setPresets).catch(() => setPresets([]))
  }, [])

  async function sendBoth(message: string, presetId?: string, skipAttach = false) {
    if (!message.trim() || sending) return
    setSending(true)
    setSuggestions([]) // 새 전송이 시작되면 이전 추천은 숨긴다

    let attachmentId: number | undefined
    let attachment: string | undefined
    try {
      if (uploaded) {
        // 사용자가 직접 올린 파일이 있으면 그걸 우선 첨부한다.
        attachmentId = uploaded.id
        attachment = uploaded.filename
      } else if (presetId && !skipAttach) {
        const preset = presets.find((p) => p.id === presetId)
        if (preset?.has_attachment) {
          const res = await api.presetAttachment(presetId)
          attachmentId = res.attachment_id
          attachment = res.filename
        }
      }
    } catch {
      /* 첨부 준비 실패해도 메시지는 보낸다 */
    }

    setOff({ loading: true, user: message, attachment })
    setOn({ loading: true, user: message, attachment })

    // OFF와 ON에 같은 입력을 보낸다. 한쪽이 실패해도 다른 쪽은 보여 준다.
    const [offRes, onRes] = await Promise.all([
      api
        .chat('off', message, attachmentId)
        .then((result) => (setOff({ loading: false, user: message, attachment, result }), result))
        .catch((err) => (setOff({ loading: false, user: message, attachment, error: msg(err) }), null)),
      api
        .chat('on', message, attachmentId)
        .then((result) => (setOn({ loading: false, user: message, attachment, result }), result))
        .catch((err) => (setOn({ loading: false, user: message, attachment, error: msg(err) }), null)),
    ])
    onBalanceChange()
    setUploaded(null) // 보낸 뒤 올린 파일 첨부는 비운다
    setSending(false)

    // 다음에 보낼 만한 질문을 한 번만 생성한다(ON 답변 기준, 없으면 OFF). 실패하면 칩 없이 넘어간다.
    const reply = onRes?.reply ?? offRes?.reply
    if (reply) {
      api
        .suggestions(message, reply)
        .then((r) => {
          // 일반 추천 2개만 두고, 추가 공격(pinned=false) 1개를 섞어 '3개 중 1개는 공격'이 되게 한다.
          setSuggestions(r.suggestions.slice(0, 2))
          const extras = presets.filter((p) => !p.pinned)
          if (extras.length > 0) setFeaturedAttackId(extras[Math.floor(Math.random() * extras.length)].id)
        })
        .catch(() => setSuggestions([]))
    }
  }

  function fillFromChip(p: Preset) {
    setInput(p.message)
    setArmed({ id: p.id, message: p.message })
    setDropAttach(false)
  }

  function changeInput(value: string) {
    setInput(value)
    if (armed && value !== armed.message) {
      setArmed(null) // 직접 고치면 프리셋 연결 해제
      setDropAttach(false)
    }
  }

  function submit() {
    if (!input.trim() || sending) return
    const presetId = armed && input.trim() === armed.message ? armed.id : undefined
    void sendBoth(input, presetId, dropAttach)
    setInput('')
    setArmed(null)
    setDropAttach(false)
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // 같은 파일 다시 선택 가능하게 초기화
    if (!file) return
    try {
      const res = await api.uploadAttachment(file)
      setUploaded({ id: res.id, filename: res.filename })
    } catch (err) {
      alert(err instanceof ApiError ? err.message : '파일 업로드에 실패했습니다')
    }
  }

  // S1·S2 고정 칩은 항상, 추천이 뜨면 그 묶음에 공격 1개를 더 끼워넣는다(추천 3개 = 공격 1 + 일반 2)
  const featured = suggestions.length > 0 && featuredAttackId ? presets.find((p) => p.id === featuredAttackId) : undefined

  // 지금 채워진 공격이 첨부(청구서 PDF)를 함께 보내는지
  const armedPreset = armed ? presets.find((p) => p.id === armed.id) : undefined
  const presetAttach = Boolean(armedPreset?.has_attachment) && !dropAttach && !uploaded

  return (
    <div className="compare">
      <div className="toolbar">
        <div className="viewtabs">
          <button type="button" className={view === 'both' ? 'on' : ''} onClick={() => setView('both')}>
            나란히 보기
          </button>
          <button type="button" className={view === 'off' ? 'on' : ''} onClick={() => setView('off')}>
            방어 OFF만
          </button>
          <button type="button" className={view === 'on' ? 'on' : ''} onClick={() => setView('on')}>
            방어 ON만
          </button>
        </div>
        <div className="balance">내 잔액: {balance === null ? '—' : `${balance.toLocaleString()}원`}</div>
      </div>

      <div className={`panels view-${view}`}>
        {view !== 'on' && <ChatPanel mode="off" state={off} onConfirmed={onBalanceChange} />}
        {view !== 'off' && <ChatPanel mode="on" state={on} onConfirmed={onBalanceChange} />}
      </div>

      <form
        className="composer-box"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <div className="box-chips">
          {/* S1·S2 고정 공격 칩 (항상) */}
          {presets.filter((p) => p.pinned).map((p) => (
            <button
              key={p.id}
              type="button"
              className="chip-attack"
              disabled={sending}
              onClick={() => fillFromChip(p)}
            >
              <span className="chip-kind attack">공격</span>
              {p.label}
            </button>
          ))}
          {/* 추천 묶음: 공격 1개 + 일반 2개 */}
          {featured && (
            <button
              type="button"
              className="chip-attack"
              disabled={sending}
              onClick={() => fillFromChip(featured)}
            >
              <span className="chip-kind attack">공격</span>
              {featured.label}
            </button>
          )}
          {suggestions.map((s, i) => (
            <button key={i} type="button" className="chip-reply" disabled={sending} onClick={() => void sendBoth(s)}>
              <span className="chip-kind reply">일반</span>
              {s}
            </button>
          ))}
        </div>

        <textarea
          value={input}
          onChange={(e) => changeInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          rows={2}
          placeholder="메시지를 입력해 양쪽에 보내기 (예: 내 잔액 알려줘). Enter 전송, Shift+Enter 줄바꿈"
          disabled={sending}
        />

        <div className="box-bottom">
          <button
            type="button"
            className="file-btn"
            onClick={() => fileRef.current?.click()}
            disabled={sending}
            title="PDF·txt 파일 첨부 (1MB 이하)"
          >
            📎 파일 첨부
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt"
            onChange={onPickFile}
            style={{ display: 'none' }}
          />
          {uploaded ? (
            <div className="attach-pill">
              <span className="attach-icon" aria-hidden="true">📎</span>
              {uploaded.filename}
              <button type="button" className="attach-x" onClick={() => setUploaded(null)} aria-label="첨부 취소">
                ✕
              </button>
            </div>
          ) : presetAttach ? (
            <div className="attach-pill">
              <span className="attach-icon" aria-hidden="true">📎</span>
              invoice.pdf
              <button type="button" className="attach-x" onClick={() => setDropAttach(true)} aria-label="첨부 취소">
                ✕
              </button>
            </div>
          ) : null}
          <button type="submit" className="send-btn" disabled={sending || !input.trim()}>
            보내기
          </button>
        </div>
      </form>
    </div>
  )
}

function msg(err: unknown): string {
  return err instanceof ApiError ? err.message : '요청 실패'
}
