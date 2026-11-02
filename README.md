# KoFinGuard

가상 은행(MJ뱅크) 고객용 AI 상담 챗봇에 실제 은행 사고·취약점 기반 공격 2개(S1 권한 사칭, S2 PDF 속 숨은 지시)를 원문 그대로 재현하고, 방어 OFF 챗봇은 뚫리고 방어 ON 챗봇은 막히는 것을 실제 결과로 보여 주는 프로젝트입니다. 핵심 방어는 서버 쪽이고, 졸프 한국어 탈옥 탐지 파이프라인은 보조 레이어입니다. MJ뱅크와 모든 고객·계좌·금액은 가상입니다.

문서: [MVP](docs/mvp.md) · [PRD](docs/prd.md) · [SPEC](docs/spec.md) · [PLAN](docs/plan.md)

## 준비물

- Python 3.12, Node 20+, Ollama (`ollama pull llama-guard3:8b`, 너무 느리면 `llama-guard3:1b`)
- `models/qwen2.5-3b-instruct-q4_k_m.gguf`
- `backend/.env` (`backend/.env.example`을 복사해서 값 채우기, Git 제외)

## 실행 (Windows PowerShell)

백엔드 (`backend` 폴더, 처음 한 번 설치):

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`backend/.env`에 꼭 있어야 하는 값 (없으면 서버가 시작하지 않음):

- `DATABASE_URL` — 로컬은 `sqlite:///./kofinguard.db`
- `KFG_SESSION_SECRET` — 32자 이상 무작위 문자열. `.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"`로 만듭니다.

DB 준비:

```powershell
.\.venv\Scripts\python.exe -m alembic -c ..\database\alembic.ini upgrade head
.\.venv\Scripts\python.exe seed.py
```

시연 계정(가상): `minsu` / `seoyeon`, 비밀번호 `demo1234!`

서버 실행:

```powershell
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

## 공격자 서버와 명령줄 대화 (방어 OFF 관측)

`backend/.env`에 `OPENAI_MODEL`과 `KFG_ENV=local`이 있어야 합니다. 실제 OpenAI API를 써서 비용이 듭니다.

```powershell
cd backend
.\.venv\Scripts\python.exe -m attacker.server              # 127.0.0.1:9999 (다른 터미널에 켜 둠)
.\.venv\Scripts\python.exe -m scenarios.cli                # 김민수로 직접 대화
.\.venv\Scripts\python.exe -m scenarios.cli --preset all   # S1·S2 실행 → artifacts/observe_off.json
.\.venv\Scripts\python.exe seed.py --reset                 # 잔액을 처음 값으로 (관측 반복 전)
```

공격 문장을 바꾸면 `.\.venv\Scripts\python.exe -m scenarios.build`로 `presets.json`과 청구서 PDF를 다시 만듭니다.

## 졸프 탐지 파이프라인 (보조 레이어)

Ollama가 켜져 있어야 합니다 (`ollama pull llama-guard3:1b`). `backend/.env`에 `KFG_QWEN_GGUF_PATH`, `KFG_GUARD_MODEL`, `KFG_PPL_THRESHOLD`가 필요합니다.

```powershell
cd backend
.\.venv\Scripts\python.exe -m detector.calibrate        # 정상 질문 30개 + S1·S2 점수 → artifacts/detector_calibration.json
.\.venv\Scripts\python.exe -m pytest -m models          # 실제 Qwen·Llama Guard 확인
```

## 테스트

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

기본 테스트는 인터넷·OpenAI·모델 없이 돕니다. 실제 호출은 `-m llm`, `-m models`, `-m postgres`로 따로 돌립니다.
