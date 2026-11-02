import { useState } from 'react'
import { ApiError, api } from '../api'
import type { Me } from '../types'

export function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [loginId, setLoginId] = useState('minsu')
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
        <p className="sub">양갱뱅크 AI 상담 챗봇 (시연용)</p>
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
        <p className="hint">시연 계정: minsu / seoyeon · 비밀번호 demo1234!</p>
      </form>
    </div>
  )
}
