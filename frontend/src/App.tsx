import { useEffect, useState } from 'react'
import { api } from './api'
import { AttackerLog } from './components/AttackerLog'
import { ComparePage } from './components/ComparePage'
import { EvalResults } from './components/EvalResults'
import { Login } from './components/Login'
import type { Me } from './types'

type Tab = 'compare' | 'attacker' | 'eval'

function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [checking, setChecking] = useState(true)
  const [tab, setTab] = useState<Tab>('compare')

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setChecking(false))
  }, [])

  async function logout() {
    await api.logout().catch(() => undefined)
    setMe(null)
  }

  if (checking) return <div className="center">확인 중…</div>
  if (!me) return <Login onLogin={setMe} />

  return (
    <div className="app">
      <header className="topbar">
        <strong>YanggBank</strong>
        <nav>
          <button type="button" className={tab === 'compare' ? 'on' : ''} onClick={() => setTab('compare')}>
            비교 채팅
          </button>
          <button type="button" className={tab === 'attacker' ? 'on' : ''} onClick={() => setTab('attacker')}>
            공격자 기록
          </button>
          <button type="button" className={tab === 'eval' ? 'on' : ''} onClick={() => setTab('eval')}>
            평가 결과
          </button>
        </nav>
        <span className="who">
          {me.name} 님
          <button type="button" onClick={() => void logout()}>
            로그아웃
          </button>
        </span>
      </header>

      <main>
        {tab === 'compare' && <ComparePage />}
        {tab === 'attacker' && <AttackerLog />}
        {tab === 'eval' && <EvalResults />}
      </main>
    </div>
  )
}

export default App
