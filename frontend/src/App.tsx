import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { AttackerLog } from './components/AttackerLog'
import { ComparePage } from './components/ComparePage'
import { Login } from './components/Login'
import type { Me } from './types'

type Tab = 'compare' | 'attacker'

function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [checking, setChecking] = useState(true)
  const [tab, setTab] = useState<Tab>('compare')
  const [balance, setBalance] = useState<number | null>(null)

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setChecking(false))
  }, [])

  const refreshBalance = useCallback(() => {
    api.account().then((a) => setBalance(a.balance)).catch(() => setBalance(null))
  }, [])

  useEffect(() => {
    if (me) refreshBalance()
  }, [me, refreshBalance])

  async function logout() {
    await api.logout().catch(() => undefined)
    setMe(null)
    setBalance(null)
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
        </nav>
        <span className="who">
          {me.name} 님
          <button type="button" onClick={() => void logout()}>
            로그아웃
          </button>
        </span>
      </header>

      <main>
        {tab === 'compare' ? (
          <ComparePage balance={balance} onBalanceChange={refreshBalance} />
        ) : (
          <AttackerLog />
        )}
      </main>
    </div>
  )
}

export default App
