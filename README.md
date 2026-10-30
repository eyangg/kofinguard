# KoFinGuard

가상 은행(MJ뱅크) AI 상담 챗봇에 최근 실제 LLM 공격(S1~S3)을 한국어로 재현하고, 방어 OFF 챗봇은 뚫리고 방어 ON 챗봇은 막히는 것을 실제 결과와 TPR/FPR로 보여 주는 프로젝트입니다. MJ뱅크와 모든 고객·계좌·금액은 가상입니다.

문서: [MVP](docs/mvp.md) · [PRD](docs/prd.md) · [SPEC](docs/spec.md) · [PLAN](docs/plan.md)

## 준비물

- Python 3.12, Node 20+, Ollama (`ollama pull llama-guard3:1b`)
- `models/qwen2.5-3b-instruct-q4_k_m.gguf`
- `backend/.env` (`backend/.env.example`을 복사해서 값 채우기, Git 제외)

## 실행 (Windows PowerShell)

백엔드 (`backend` 폴더, 처음 한 번 설치):

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

프론트 (`frontend` 폴더, 다른 터미널):

```powershell
cd frontend
npm install
npm run dev
```

PowerShell에서 "스크립트를 실행할 수 없으므로 npm.ps1을 로드할 수 없습니다" 오류가 나면 `npm.cmd run dev`로 실행하거나, `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`를 한 번 실행합니다.

브라우저에서 http://127.0.0.1:5173 을 엽니다. `/api` 요청은 백엔드(127.0.0.1:8000)로 넘어갑니다.

## 테스트

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

기본 테스트는 인터넷·OpenAI·모델 없이 돕니다. 실제 호출은 `-m llm`, `-m models`, `-m postgres`로 따로 돌립니다.
