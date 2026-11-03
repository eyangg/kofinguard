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
          채팅 탭의 한 번 시연과 달리, 여기는 같은 공격을 <b>여러 번 반복</b>하고 정상 질문 <b>30개</b>를 훑어
          측정한 <b>통계 근거</b>입니다. 일회성 결과가 아니며, 아래 명령어로 누구나 재현할 수 있습니다.
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
  if (!attack) return <Section title="E-03 · 공격 성공률"><Empty /></Section>
  const rate = (s: string, m: Mode) => attack.rows.find((r) => r.scenario === s && r.mode === m)
  const scenarios = [...new Set(attack.rows.map((r) => r.scenario))]
  const n = attack.n ?? attack.rows[0]?.n ?? 0
  return (
    <Section title={`E-03 · 공격 성공률 — 각 공격 ${n}회 반복, OFF vs ON`}>
      <table>
        <thead>
          <tr>
            <th>공격</th>
            <th>방어 OFF (뚫린 비율)</th>
            <th>방어 ON (뚫린 비율)</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((s) => {
            const off = rate(s, 'off')
            const on = rate(s, 'on')
            return (
              <tr key={s}>
                <td>{SCN_LABEL[s] ?? s}</td>
                <td className="bad">{off ? `${(off.rate * 100).toFixed(0)}% (${off.breaches}/${off.n})` : '—'}</td>
                <td className="good">{on ? `${(on.rate * 100).toFixed(0)}% (${on.breaches}/${on.n})` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="cap">OFF는 높을수록 취약, ON은 낮을수록 안전. 공격 성공 판정은 서버 기록·답변으로 합니다.</p>
    </Section>
  )
}

function DetectorTable({ detector }: { detector: EvalLatest['detector'] }) {
  if (!detector) return <Section title="E-02 · 탐지기 운영 지표"><Empty /></Section>
  const m = detector.metrics
  return (
    <Section title="E-02 · 탐지기 운영 지표 (졸프 파이프라인, 보조)">
      <table>
        <tbody>
          <tr><th>정상 질문 오탐률</th><td className="bad">{(m.false_positive_rate * 100).toFixed(0)}% ({m.normal_blocked + m.normal_reask}/{m.normal_total})</td></tr>
          <tr><th>정상 통과 / 차단 / 다시 묻기</th><td>{m.normal_pass} / {m.normal_blocked} / {m.normal_reask}</td></tr>
          <tr><th>평균 판정 시간</th><td>{m.avg_sec}초</td></tr>
          <tr><th>공격 입력 판정</th><td>{Object.entries(m.attacks).map(([k, v]) => `${k}: ${v}`).join(' · ')}</td></tr>
        </tbody>
      </table>
      <p className="cap">
        기준값 {detector.env.ppl_threshold} · 표본 {detector.env.num_samples}.
        탐지기는 S3를 통과시킴(입력만으론 정상처럼 보임) → 서버 방어 D-09가 막는다. 오탐은 "탐지기만으론 부족하다"는 근거.
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
