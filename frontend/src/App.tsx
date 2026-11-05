import { useEffect, useState } from 'react'
import { api } from './api'
import { ComparePage } from './components/ComparePage'
import { EvalResults } from './components/EvalResults'
import { Login } from './components/Login'
import type { Me } from './types'

type Tab = 'compare' | 'eval'

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
          <button type="button" className={tab === 'eval' ? 'on' : ''} onClick={() => setTab('eval')}>
            방어 성능
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
        {/* 비교 채팅은 탭을 바꿔도 지우지 않고 숨기기만 한다 (보낸 질문·답변·응답 대기가 사라지지 않게) */}
        <div className="tab-pane" hidden={tab !== 'compare'}>
          <ComparePage />
        </div>
        {tab === 'eval' && <EvalResults />}
      </main>
    </div>
  )
}

export default App
