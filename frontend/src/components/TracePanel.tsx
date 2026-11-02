import type { TraceEvent } from '../types'

const LAYER_NAME: Record<string, string> = {
  'D-01': '문장 정리',
  'D-02': 'SmoothPPL (문장 자연스러움)',
  'D-03': 'AI 안전필터 (Llama Guard)',
  'D-04': '최종 결정',
  'D-05': '서버 권한 검사',
  'D-06': '서버 규칙·송금',
  'D-07': '문서 격리',
  'D-08': '답변 안전 처리',
  'D-09': '시스템 프롬프트 유출 차단',
}

type Tone = 'ok' | 'warn' | 'block'

type Row = { layer: string; name: string; text: string; tone: Tone } | null

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}
function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}
function sourceLabel(d: Record<string, unknown>): string {
  const s = str(d['source'])
  return s === 'document' ? '첨부 문서' : s === 'message' ? '사용자 메시지' : ''
}

function describe(e: TraceEvent): Row {
  const d = e.detail
  const name = LAYER_NAME[e.layer] ?? e.layer
  const src = sourceLabel(d)
  const tag = src ? `[${src}] ` : ''

  switch (e.layer) {
    case 'D-01': {
      // 실제로 정리된 변형이 없으면(정상 문장) 근거에서 생략한다.
      if (d['changed'] !== true) return null
      const norm = str(d['normalized'])
      return { layer: e.layer, name, tone: 'ok', text: `${tag}자모·특수문자를 표준형으로 정리했어요${norm ? `: "${norm}"` : ''}` }
    }
    case 'D-02': {
      const mean = num(d['mean_ppl'])
      if (mean === null) return { layer: e.layer, name, tone: 'ok', text: `${tag}SmoothPPL로 문장 자연스러움을 쟀어요.` }
      const normal = mean <= 5000
      return {
        layer: e.layer,
        name,
        tone: 'ok',
        text: `${tag}SmoothPPL 점수 ${Math.round(mean).toLocaleString()} — 기준(5,000) ${normal ? '이하라 정상 범위' : '초과(알아보기 어려운 문장)'}예요. 이 점수만으로는 막지 않아요.`,
      }
    }
    case 'D-03': {
      // Llama Guard의 세부 분류는 신뢰도가 낮아 보여 주지 않고, 안전/위험만 표시한다.
      if (str(d['error'])) return { layer: e.layer, name, tone: 'block', text: `${tag}판정 불가 — ${str(d['error'])}` }
      if (d['guard_safe'] === false)
        return { layer: e.layer, name, tone: 'block', text: `${tag}AI 안전필터가 '위험'으로 판정했어요` }
      return { layer: e.layer, name, tone: 'ok', text: `${tag}AI 안전필터 판정: 안전` }
    }
    case 'D-04':
      return null // D-04는 앞 단계를 종합해 따로 처리한다(describeFinal)
    case 'D-05':
    case 'D-06':
    case 'D-07': {
      const allowed = d['allowed'] !== false
      const reason = str(d['reason'])
      return {
        layer: e.layer,
        name,
        tone: allowed ? 'ok' : 'block',
        text: reason || (allowed ? '서버가 정상 처리했어요' : '서버가 거부했어요'),
      }
    }
    case 'D-08': {
      const changes = Array.isArray(d['changes']) ? (d['changes'] as string[]) : []
      return {
        layer: e.layer,
        name,
        tone: 'ok',
        text: changes.length ? `답변에서 바꾼 것: ${changes.join(', ')}` : '답변을 안전하게 처리했어요',
      }
    }
    case 'D-09':
      return { layer: e.layer, name, tone: 'block', text: '답변에 내부 지침이 새어 차단했어요 (시스템 프롬프트 유출)' }
    default:
      return { layer: e.layer, name, tone: 'ok', text: e.action }
  }
}

type Shown = Exclude<Row, null>

// 같은 입력(message/document)의 D-01~D-03 값을 모아 D-04 요약에 쓴다.
type SrcInfo = { changed?: boolean; mean?: number; safe?: boolean; unsafe?: boolean; err?: string }

function gatherInfo(trace: TraceEvent[]): Record<string, SrcInfo> {
  const info: Record<string, SrcInfo> = {}
  for (const e of trace) {
    const s = str(e.detail['source']) || 'message'
    const cur = (info[s] ??= {})
    if (e.layer === 'D-01') cur.changed = e.detail['changed'] === true
    if (e.layer === 'D-02') cur.mean = num(e.detail['mean_ppl']) ?? undefined
    if (e.layer === 'D-03') {
      cur.safe = e.detail['guard_safe'] === true
      cur.unsafe = e.detail['guard_safe'] === false
      cur.err = str(e.detail['error'])
    }
  }
  return info
}

function describeFinal(e: TraceEvent, info: Record<string, SrcInfo>): Shown {
  const src = sourceLabel(e.detail)
  const tag = src ? `[${src}] ` : ''
  const c = info[str(e.detail['source']) || 'message'] ?? {}

  // D-01·D-02·D-03이 각각 무엇을 근거로 했는지 짧게
  const parts: string[] = []
  if (c.changed) parts.push('D-01 변형 정리함')
  if (c.mean != null) parts.push(`D-02 점수 ${Math.round(c.mean).toLocaleString()}(${c.mean <= 5000 ? '정상' : '높음'})`)
  if (c.err) parts.push('D-03 판정 불가')
  else if (c.unsafe) parts.push("D-03 안전필터 '위험'")
  else if (c.safe) parts.push("D-03 안전필터 '안전'")
  const basis = parts.join(' · ')

  const decision: Record<string, { word: string; tone: Tone }> = {
    pass: { word: '통과 (챗봇에게 전달)', tone: 'ok' },
    block: { word: '차단 (챗봇을 부르지 않음)', tone: 'block' },
    reask: { word: '다시 묻기 (재입력 요청)', tone: 'warn' },
    unavailable: { word: '처리 안 함 (검사 불가)', tone: 'block' },
  }
  const dec = decision[e.action] ?? { word: e.action, tone: 'ok' as Tone }
  return {
    layer: 'D-04',
    name: LAYER_NAME['D-04'],
    tone: dec.tone,
    text: `${tag}${basis ? basis + ' → ' : ''}${dec.word}`,
  }
}

function finalLine(rows: Shown[]): string {
  if (rows.some((r) => r.layer === 'D-04' && r.tone === 'block')) return '입력 차단됨'
  if (rows.some((r) => r.tone === 'block')) return '서버가 막음'
  if (rows.some((r) => r.layer === 'D-04' && r.tone === 'warn')) return '다시 묻기'
  return '정상 처리'
}

// 방어 장치가 단계별로 어떻게 판단했는지 쉬운 말로 보여 준다 (U-03). 방어 ON 답변에만 나온다.
export function TracePanel({ trace }: { trace: TraceEvent[] }) {
  if (trace.length === 0) return null
  const info = gatherInfo(trace)
  const rows = trace
    .map((e) => (e.layer === 'D-04' ? describeFinal(e, info) : describe(e)))
    .filter((r): r is Shown => r !== null)
  if (rows.length === 0) return null
  return (
    <details className="trace" open>
      <summary>
        방어가 어떻게 판단했나 <span className="trace-final">· {finalLine(rows)}</span>
      </summary>
      <ol>
        {rows.map((r, i) => (
          <li key={i} className={`t-${r.tone}`}>
            <span className="t-layer">{r.layer}</span>
            <div className="t-body">
              <span className="t-name">{r.name}</span>
              <span className="t-text">{r.text}</span>
            </div>
          </li>
        ))}
      </ol>
    </details>
  )
}
