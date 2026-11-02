import { useEffect, useState } from 'react'
import { api } from '../api'
import type { AttackerLogEntry } from '../types'

// 공격자 서버(127.0.0.1:9999)가 받은 요청 (U-05). S2가 실제로 유출됐는지 확인한다.
export function AttackerLog() {
  const [entries, setEntries] = useState<AttackerLogEntry[]>([])
  const [error, setError] = useState('')

  async function refresh() {
    try {
      setEntries(await api.attackerLog())
      setError('')
    } catch {
      setError('공격자 서버 기록을 불러오지 못했습니다')
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  return (
    <div className="attacker">
      <div className="attacker-head">
        <h2>공격자 서버 기록 ({entries.length})</h2>
        <button type="button" onClick={() => void refresh()}>
          새로고침
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {entries.length === 0 ? (
        <p className="empty">아직 기록이 없습니다. (OFF에서 S2 공격이 성공하면 여기에 유출 요청이 쌓입니다)</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>시각</th>
              <th>경로</th>
              <th>빼간 데이터</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={i}>
                <td>{e.time.slice(11, 19)}</td>
                <td>{e.path}</td>
                <td className="leak">{e.query['d'] ? String(e.query['d']) : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
