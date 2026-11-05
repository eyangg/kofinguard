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

// idle = 검사할 일이 없었음 (통과와 구분해 회색 점선으로 보인다)
type Tone = 'ok' | 'warn' | 'block' | 'idle'

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

// showSource=true일 때만 [사용자 메시지]/[첨부 문서] 태그를 붙인다.
// (메시지만 검사하는 경우엔 전부 메시지라 태그가 군더더기여서 숨긴다. S2처럼 문서도 함께 검사할 때만 구분용으로 표시.)
function describe(e: TraceEvent, showSource: boolean): Row {
  const d = e.detail
  const name = LAYER_NAME[e.layer] ?? e.layer
  const src = sourceLabel(d)
  const tag = showSource && src ? `[${src}] ` : ''

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

function describeFinal(e: TraceEvent, info: Record<string, SrcInfo>, showSource: boolean): Shown {
  const src = sourceLabel(e.detail)
  const tag = showSource && src ? `[${src}] ` : ''
  const c = info[str(e.detail['source']) || 'message'] ?? {}
  const mean = c.mean != null ? Math.round(c.mean).toLocaleString() : '—'
  // D-01은 판정에 쓰지 않고 전처리(표준형 정리)만 한다. 변형이 있었을 때만 덧붙인다.
  const pre = c.changed ? ' 입력은 D-01에서 표준형으로 정리한 뒤 검사했어요.' : ''

  // 결정 규칙(router.py): D-03 '위험'이면 점수와 무관하게 차단 → '안전'이면 D-02 점수로 통과/다시묻기.
  // D-02 점수는 '문장이 자연스러운지'만 재고 위험성은 못 가리므로, 위험 판정은 D-03가 맡는다.
  const tone: Record<string, Tone> = { pass: 'ok', block: 'block', reask: 'warn', unavailable: 'block' }
  let text: string
  switch (e.action) {
    case 'block':
      text = `AI 안전필터(D-03)가 '위험'으로 판정해서 바로 차단했어요. SmoothPPL 점수(D-02)는 문장이 자연스러운지만 재고 위험한지는 못 가리기 때문에, 안전필터가 '위험'이라고 하면 점수와 상관없이 막아요.${pre}`
      break
    case 'reask':
      text = `AI 안전필터(D-03)는 '안전'인데 SmoothPPL 점수(D-02) ${mean}가 기준(5,000)을 넘었어요. 점수가 높다는 건 '위험'이 아니라 '알아보기 어려운 문장'이라는 뜻이라, 차단하지 않고 '다시 묻기'로 재입력을 요청했어요.${pre}`
      break
    case 'pass':
      text = `AI 안전필터(D-03)가 '안전'이고 SmoothPPL 점수(D-02) ${mean}도 기준(5,000) 이하예요. 둘 다 정상이라 통과시켜 챗봇에게 전달했어요.${pre}`
      break
    default: // unavailable
      text = `검사를 끝까지 못 해서(${c.err || '모델 오류'}) 안전을 확인하지 못했어요. 확인이 안 되면 통과시키지 않고 처리를 멈춰요.`
  }
  return { layer: 'D-04', name: LAYER_NAME['D-04'], tone: tone[e.action] ?? 'ok', text: `${tag}${text}` }
}

// 입력은 통과했는데 핵심 방어(D-05~D-09) 기록이 없으면, 챗봇이 조회·송금 툴을 안 부르고 답한 것이다
// (예: 남의 번호 요청을 챗봇이 스스로 거절). 핵심 방어가 빠진 게 아니라 검사할 일이 없었다는 걸 보여 준다.
const CORE_LAYERS = ['D-05', 'D-06', 'D-07', 'D-08', 'D-09']

function coreIdleRow(trace: TraceEvent[]): Shown | null {
  const finals = trace.filter((e) => e.layer === 'D-04')
  if (finals.length === 0 || finals.some((e) => e.action !== 'pass')) return null
  if (trace.some((e) => CORE_LAYERS.includes(e.layer))) return null
  return {
    layer: 'D-05~09',
    name: '핵심 방어 (서버) · 검사할 일 없음',
    tone: 'idle',
    text: '챗봇이 조회·송금 기능을 쓰지 않고 바로 답해서, 서버가 검사하거나 고칠 것이 없었어요. 챗봇이 조회·송금을 시도했다면 D-05·D-06이 로그인한 본인 기준으로 다시 검사해요.',
  }
}

function finalLine(rows: Shown[]): string {
  if (rows.some((r) => r.layer === 'D-04' && r.tone === 'block')) return '입력 차단됨'
  if (rows.some((r) => r.tone === 'block')) return '서버가 막음'
  if (rows.some((r) => r.layer === 'D-04' && r.tone === 'warn')) return '다시 묻기'
  return '정상 처리'
}

// 방어 장치가 단계별로 어떻게 판단했는지 쉬운 말로 보여 준다 (U-03). 방어 ON 답변에만 나온다.
export function TracePanel({ trace, elapsedMs }: { trace: TraceEvent[]; elapsedMs?: number }) {
  if (trace.length === 0) return null
  const info = gatherInfo(trace)
  // 첨부 문서도 함께 검사했을 때만 [사용자 메시지]/[첨부 문서] 구분 태그를 보인다.
  const showSource = trace.some((e) => str(e.detail['source']) === 'document')
  const rows = trace
    .map((e) => (e.layer === 'D-04' ? describeFinal(e, info, showSource) : describe(e, showSource)))
    .filter((r): r is Shown => r !== null)
  const idle = coreIdleRow(trace)
  if (idle) rows.push(idle)
  if (rows.length === 0) return null
  const took = elapsedMs != null ? `${(elapsedMs / 1000).toFixed(1)}초` : null
  return (
    <details className="trace" open>
      <summary>
        방어 판단 근거{' '}
        <span className="trace-final">
          · {finalLine(rows)}
          {took ? ` · ${took} 걸림` : ''}
        </span>
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
