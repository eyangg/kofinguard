import { useEffect, useState } from 'react'
import { api } from '../api'
import type { EvalLatest, Mode } from '../types'

// 정량 평가 결과 (U-06). "일회성 시연이 아니라 반복 측정한 통계 근거"를 보여 준다.
export function EvalResults() {
  const [data, setData] = useState<EvalLatest | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.evalLatest().then(setData).catch(() => setError('평가 결과를 불러오지 못했습니다'))
  }, [])

  if (error) return <div className="eval"><p className="error">{error}</p></div>
  if (!data) return <div className="eval"><p className="empty">불러오는 중…</p></div>

  const measuredAt = data.attack?.measured_at ?? data.detector?.measured_at
  const model = data.attack?.env.model
  const n = data.attack?.n ?? data.attack?.rows[0]?.n

  return (
    <div className="eval">
      <div className="eval-intro">
        <h2>정량 평가 — 반복 측정 결과</h2>
        <p>
          채팅 탭의 한 번 시연과 달리, 여기는 같은 공격을 <b>여러 번 반복</b>하고
          정상 질문 <b>30개</b>를 훑어 측정한 <b>통계 근거</b>입니다.
        </p>
        <p>
          일회성 결과가 아니며, 아래 명령어로 누구나 재현할 수 있습니다.
        </p>
        <div className="eval-meta">
          {measuredAt && <span>측정 {fmtDate(measuredAt)}</span>}
          {model && <span>모델 {model}</span>}
          {n != null && <span>공격 반복 각 {n}회</span>}
          {data.detector && <span>탐지기 Guard {data.detector.env.guard_model}</span>}
        </div>
      </div>

      <Headline attack={data.attack} />
      <AttackTable attack={data.attack} />
      <DetectorTable detector={data.detector} />

      <p className="eval-note">
        재현: <code>python -m eval.run_attack_eval --n 5</code> · <code>python -m eval.run_detector_eval</code>.
        화면은 측정 결과 파일을 읽기만 합니다.
      </p>
    </div>
  )
}

const SCN_LABEL: Record<string, string> = {
  S1: 'S1 권한 사칭',
  S2: 'S2 문서 숨은 지시',
  S3: 'S3 프롬프트 유출',
}

// 공격이 무엇을 노리는지 한 줄 설명 (처음 보는 사람용)
const SCN_DESC: Record<string, string> = {
  S1: '남의 계좌 정보를 자기 것인 척 몰래 조회',
  S2: '첨부 문서에 숨긴 명령으로 답변에 악성 코드 심기',
  S3: '챗봇의 내부 지침(시스템 프롬프트)을 빼내기',
}

// 탐지기가 각 공격을 어떻게 판정했는지 (block/pass/reask → 쉬운 말)
const DETECT_LABEL: Record<string, string> = {
  block: '걸러냄',
  pass: '통과(못 걸러냄)',
  reask: '다시 물어봄',
}

function Headline({ attack }: { attack: EvalLatest['attack'] }) {
  if (!attack || attack.rows.length === 0) return null
  const off = attack.rows.filter((r) => r.mode === 'off')
  const on = attack.rows.filter((r) => r.mode === 'on')
  const avg = (rs: typeof off) => (rs.reduce((s, r) => s + r.rate, 0) / rs.length) * 100
  return (
    <div className="eval-headline">
      <div className="hl off">
        <span className="hl-num">{avg(off).toFixed(0)}%</span>
        <span className="hl-label">방어 OFF — 공격이 뚫린 비율</span>
      </div>
      <span className="hl-arrow">→</span>
      <div className="hl on">
        <span className="hl-num">{avg(on).toFixed(0)}%</span>
        <span className="hl-label">방어 ON — 공격이 뚫린 비율</span>
      </div>
    </div>
  )
}

function AttackTable({ attack }: { attack: EvalLatest['attack'] }) {
  if (!attack) return <Section title="공격이 실제로 막히는가"><Empty /></Section>
  const rate = (s: string, m: Mode) => attack.rows.find((r) => r.scenario === s && r.mode === m)
  const scenarios = [...new Set(attack.rows.map((r) => r.scenario))]
  const n = attack.n ?? attack.rows[0]?.n ?? 0
  return (
    <Section title="공격이 실제로 막히는가 — 방어 끄고 / 켜고 비교">
      <p className="sec-lead">
        같은 공격을 각각 <b>{n}번</b>씩 보내서, 실제로 피해가 난 횟수를 셌습니다. 낮을수록 안전해요.
      </p>
      <table>
        <thead>
          <tr>
            <th>어떤 공격인지</th>
            <th>방어 OFF (보호 없음)</th>
            <th>방어 ON (방어 켬)</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((s) => {
            const off = rate(s, 'off')
            const on = rate(s, 'on')
            return (
              <tr key={s}>
                <td>
                  <span className="scn-name">{SCN_LABEL[s] ?? s}</span>
                  <span className="scn-desc">{SCN_DESC[s]}</span>
                </td>
                <td className="bad">{off ? `${off.n}번 중 ${off.breaches}번 뚫림` : '—'}</td>
                <td className="good">{on ? `${on.n}번 중 ${on.breaches}번 뚫림` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="cap">
        ‘뚫림’은 챗봇이 뭐라고 답했는지가 아니라, 실제 서버 기록·잔액이 바뀌었는지로 판정했습니다.
        OFF는 전부 뚫리고 ON은 하나도 안 뚫리는 게 이 프로젝트의 결론입니다.
      </p>
    </Section>
  )
}

function DetectorTable({ detector }: { detector: EvalLatest['detector'] }) {
  if (!detector) return <Section title="입력을 미리 거르는 탐지기"><Empty /></Section>
  const m = detector.metrics
  const misread = m.normal_blocked + m.normal_reask
  return (
    <Section title="입력을 미리 거르는 탐지기 — 보조 방어">
      <p className="sec-lead">
        위 방어와 별개로, 위험해 보이는 문장을 챗봇에 닿기 전에 미리 걸러 내는 1차 필터입니다.
        진짜로 막는 건 서버 쪽이고, 이건 거들어 주는 보조 장치예요.
      </p>
      <table>
        <tbody>
          <tr>
            <th>정상 질문을 공격으로 오해한 횟수</th>
            <td className="bad">일상 질문 {m.normal_total}개 중 {misread}개 ({(m.false_positive_rate * 100).toFixed(0)}%)</td>
          </tr>
          <tr>
            <th>정상 질문 처리 결과</th>
            <td>그냥 통과 {m.normal_pass}개 · 막아 버림 {m.normal_blocked}개 · 다시 물어봄 {m.normal_reask}개</td>
          </tr>
          <tr>
            <th>검사 한 번에 걸린 평균 시간</th>
            <td>{m.avg_sec}초</td>
          </tr>
          <tr>
            <th>공격을 걸러냈는지</th>
            <td>{Object.entries(m.attacks).map(([k, v]) => `${SCN_LABEL[k] ?? k} → ${DETECT_LABEL[v] ?? v}`).join(' · ')}</td>
          </tr>
        </tbody>
      </table>
      <p className="cap">
        S3(프롬프트 유출)는 문장만 보면 평범해서 이 탐지기를 그냥 통과해요<br />
        → 대신 서버 방어가 답변 단계에서 막습니다.
        정상 질문을 가끔 오해한다는 건 “탐지기 하나로는 부족하니 여러 겹 방어가 필요하다”는 걸 보여 줍니다.
      </p>
    </Section>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="eval-section">
      <h2>{title}</h2>
      {children}
    </div>
  )
}

function Empty() {
  return <p className="empty">아직 측정하지 않았습니다. 위 명령어로 평가를 돌려 주세요.</p>
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })
}
