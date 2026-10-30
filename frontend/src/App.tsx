import { useEffect, useState } from 'react'

type Health = { status: string }

function App() {
  const [health, setHealth] = useState<string>('확인 중...')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<Health>
      })
      .then((data) => setHealth(data.status))
      .catch((err: unknown) => {
        setHealth(`연결 실패 (${err instanceof Error ? err.message : '알 수 없음'})`)
      })
  }, [])

  return (
    <main>
      <h1>KoFinGuard</h1>
      <p>백엔드 상태: {health}</p>
    </main>
  )
}

export default App
