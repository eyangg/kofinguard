import { useState } from 'react'
import { ApiError, api } from '../api'
import type { Me } from '../types'

export function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [loginId, setLoginId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      onLogin(await api.login(loginId, password))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '로그인에 실패했습니다')
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <h1>YanggBank</h1>
        <p className="sub">KoFinGuard · 가상 은행 AI 상담 보안 시연</p>
        <p className="login-intro">같은 공격을 방어 OFF/ON에 보내고, 서버가 무엇을 막았는지 비교해 보세요.</p>
        <label>
          아이디
          <input value={loginId} onChange={(e) => setLoginId(e.target.value)} autoComplete="username" />
        </label>
        <label>
          비밀번호
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? '로그인 중...' : '로그인'}
        </button>
        <div className="demo-account">
          <span>체험용 가상 계정</span>
          <button type="button" disabled={busy} onClick={() => { setLoginId('minsu'); setPassword('demo1234!') }}>
            minsu 계정 입력하기
          </button>
          <small>비밀번호 demo1234! · 모든 고객·계좌·금액은 가상 데이터입니다.</small>
        </div>
      </form>
    </div>
  )
}
