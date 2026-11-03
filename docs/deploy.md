# KoFinGuard 배포 runbook (포폴 공개용)

> 프론트 **Cloudflare Pages** · 백엔드 **AWS Lightsail** · DB **Supabase(PostgreSQL)**
> 담당자에게 보여줄 포폴 공개가 목적. 아래 "결정된 구성"을 전제로 한다.

## 0. 결정된 구성

| 항목 | 결정 | 메모 |
|---|---|---|
| OFF 모드 | **켬** (로그인 뒤에만) | OFF/ON 비교가 핵심이라 유지. XSS는 CSP로 봉쇄 |
| XSS 대응 | **CSP 중간 정책** | 삽입 코드 실행은 되되(시연 유지), **외부 출처로는 못 나감**(악용 차단) |
| 탐지기 | **Llama Guard 1b + Qwen GGUF** | 8b는 16GB라 과함. 1b 오탐(13%)은 "탐지기 한계 → 서버 방어 필요" 근거로 씀 |
| 공격자 서버 | **독립 9999 서버는 배포 안 함** | 대신 수집 기능을 백엔드 데모 엔드포인트로 옮겨, 배포판에서도 **실제 유출**을 보여줌 |
| Lightsail | **8GB RAM / 2vCPU** (약 $44/월) | Qwen+1b+앱 RAM ~6GB |
| 도메인 | **필요** | 쿠키(SameSite=None;Secure)·HTTPS 때문에 IP로는 불가 |

핵심 전제: 프론트(`app.도메인`)와 백엔드(`api.도메인`)가 **다른 출처** → ① CORS ② 교차사이트 쿠키 ③ 프론트가 백엔드 주소를 알게 — 이걸 코드로 먼저 고친다(Part A).

---

## Part A. 로컬 작업 (배포 전 코드 변경) — **먼저 전부 끝내고 커밋**

> 아래는 아직 안 된 작업. 로컬에서 바꾸고 테스트한 뒤 커밋해야 배포가 돌아간다.

### A1. 프론트 — API 주소 환경변수화 + 쿠키 포함
- `frontend/src/api.ts`: 모든 요청을 `${import.meta.env.VITE_API_BASE ?? ''}${path}` 로 보내고, `fetch(..., { credentials: 'include' })` 추가.
- 로컬은 `VITE_API_BASE` 비움(프록시 사용), 배포는 `https://api.도메인`.

### A2. 백엔드 — CORS 허용
- `backend/main.py`에 `CORSMiddleware` 추가. `allow_origins=[os.environ["KFG_FRONTEND_ORIGIN"]]`, `allow_credentials=True`.
- 로컬에선 `KFG_FRONTEND_ORIGIN` 없으면 CORS 미적용(기존대로 동작).

### A3. 백엔드 — 교차사이트 로그인 쿠키
- `backend/auth.py`의 `set_cookie`: 배포(HTTPS)에서는 `samesite="none", secure=True`, 로컬에서는 `lax`.
- `KFG_COOKIE_CROSS_SITE=1`(배포) 환경변수로 분기. (none+secure는 HTTPS에서만 동작하므로 로컬 http는 lax 유지)

### A4. 프론트 — CSP 헤더 (XSS 봉쇄, 중간 정책)
- **백엔드가 아니라 프론트에 둔다.** 공격 코드가 실행되는 HTML 페이지는 Cloudflare Pages(`app.도메인`)가 서빙하므로, CSP는 `frontend/public/_headers`에 넣어야 그 페이지에 적용된다(백엔드 api.도메인은 JSON만 줌).
- `frontend/public/_headers`:
  ```
  /*
    Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://api.도메인; connect-src 'self' https://api.도메인; img-src 'self' https://api.도메인 data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; base-uri 'self'; object-src 'none'; frame-ancestors 'none'
  ```
  → **배포 전 `https://api.도메인`을 실제 백엔드 주소로 치환**(정적 파일이라 env 치환 안 됨).
- 의도: 삽입된 `onerror` 코드는 **실행되되(OFF 시연 유지)**, **우리 백엔드(수집 엔드포인트) 외의 외부 출처로는 못 나감**(외부 유출 등 악용 차단).
- SPA 폴백 `frontend/public/_redirects`도 함께: `/*  /index.html  200`

### A5. 공격자 수집을 백엔드로 이전 (배포판에서도 "실제 유출" 보여주기)
- 독립 `attacker/server.py`(9999)는 **로컬 개발 전용**으로 남기고, 배포판에선 **백엔드 데모 엔드포인트**가 그 역할을 한다:
  - `GET /api/demo/x` — S2 숨은 코드가 불러가는 exfil 스크립트(로그인 사용자의 `/api/me`를 읽어 `/collect`로 보냄).
  - `GET /api/demo/collect?d=...` — 빼돌린 값이 도착하는 곳. `artifacts/attacker_log.jsonl`에 기록(기존 "공격자 기록" 탭이 이걸 읽음).
- S2 숨은 코드의 목적지 호스트를 **환경변수 `KFG_ATTACKER_BASE`** 로 뺀다.
  - 로컬: `http://127.0.0.1:9999` (지금처럼 독립 서버) 또는 백엔드.
  - 배포: `https://api.도메인/api/demo`.
- S2 청구서 PDF는 그 목적지로 **다시 생성**(`scenarios.build`). 배포용 PDF는 배포 호스트로 만들어 올린다.
- 결과: 배포판에서 OFF로 S2를 넣으면, 방문자 브라우저가 **우리 백엔드 수집 엔드포인트로 실제 전송** → "공격자 기록" 탭에 유출이 뜬다. CSP가 **우리 백엔드만 허용**하므로 외부 악용은 막힌다.

### A6. 로컬 전체 테스트
- `pytest` 전부 통과 확인(+ 바뀐 부분 수동 확인).
- 로컬에서 `KFG_SERVE_FRONTEND` 없이 기존 dev 흐름 안 깨지는지 확인.

### A7. 커밋
- 위 변경을 커밋·푸시. Cloudflare Pages가 이 커밋을 빌드한다.

---

## Part B. Supabase (이미 됨 — 확인만)

1. 대시보드 → **Connect → Session pooler** 연결 문자열 확보(= 백엔드 `DATABASE_URL`).
2. 테이블·RLS 적용 확인:
   ```
   .\.venv\Scripts\python.exe -m alembic -c ..\database\alembic.ini upgrade head
   .\.venv\Scripts\python.exe seed.py
   .\.venv\Scripts\python.exe -m pytest -m postgres
   ```
3. (선택) Supabase **Network Restrictions**에서 Lightsail 고정 IP만 허용.

---

## Part C. Lightsail 백엔드

1. **인스턴스 생성**: Ubuntu 22.04, **8GB RAM / 2vCPU** 플랜.
2. **Static IP** 생성·연결(재부팅해도 유지).
3. **방화벽(인스턴스 Networking)**: 22·80·443만 허용. **8000·9999는 열지 않음**(내부 전용).
4. **접속 & 기본 세팅** (`ssh ubuntu@고정IP`):
   ```bash
   sudo apt update && sudo apt -y upgrade
   sudo apt -y install python3.12 python3.12-venv git curl
   ```
5. **코드·의존성**:
   ```bash
   git clone https://github.com/eyangg/kofinguard.git
   cd kofinguard/backend
   python3.12 -m venv .venv
   ./.venv/bin/pip install -r requirements.txt
   ```
6. **모델**:
   ```bash
   mkdir -p ../models
   curl -L -o ../models/qwen2.5-3b-instruct-q4_k_m.gguf \
     https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull llama-guard3:1b
   ```
7. **`backend/.env`** (서버에만, 깃 금지):
   ```
   DATABASE_URL=postgresql://postgres.xxx:비밀번호@...pooler.supabase.com:5432/postgres
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4.1-mini
   KFG_SESSION_SECRET=(python -c "import secrets;print(secrets.token_urlsafe(32))")
   KFG_ENV=local
   KFG_QWEN_GGUF_PATH=../models/qwen2.5-3b-instruct-q4_k_m.gguf
   KFG_GUARD_MODEL=llama-guard3:1b
   KFG_PPL_THRESHOLD=5000
   KFG_FRONTEND_ORIGIN=https://app.도메인
   KFG_API_ORIGIN=https://api.도메인
   KFG_COOKIE_CROSS_SITE=1
   KFG_ATTACKER_BASE=https://api.도메인/api/demo
   ```
8. **배포용 S2 PDF 재생성**(배포 호스트로):
   ```bash
   ./.venv/bin/python -m scenarios.build
   ```
9. **DB 적용**(한 번): `./.venv/bin/python -m alembic -c ../database/alembic.ini upgrade head && ./.venv/bin/python seed.py`
10. **systemd 서비스** `/etc/systemd/system/kofinguard.service`:
    ```ini
    [Unit]
    Description=KoFinGuard API
    After=network.target
    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/kofinguard/backend
    ExecStart=/home/ubuntu/kofinguard/backend/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
    Restart=always
    [Install]
    WantedBy=multi-user.target
    ```
    ```bash
    sudo systemctl daemon-reload && sudo systemctl enable --now kofinguard
    sudo systemctl status kofinguard
    ```
    (Ollama는 설치 시 자동 서비스. `systemctl status ollama`)
11. **HTTPS 리버스 프록시 (Caddy)**:
    - DNS: `api.도메인` **A 레코드 → 고정 IP** (Cloudflare DNS면 주황 구름 off = DNS only).
    - 설치 후 `/etc/caddy/Caddyfile`:
      ```
      api.도메인 {
          reverse_proxy 127.0.0.1:8000
      }
      ```
    - `sudo systemctl restart caddy` → `curl https://api.도메인/api/health` → `{"status":"ok"}`
12. **독립 공격자 서버(9999)는 켜지 않는다.** 수집은 A5의 백엔드 엔드포인트가 담당.

---

## Part D. Cloudflare Pages 프론트

1. Cloudflare → **Workers & Pages → Create → Pages → Connect to Git** → `eyangg/kofinguard`.
2. 빌드 설정:
   - Root directory: `frontend`
   - Build command: `npm run build`
   - Build output directory: `dist`
3. 환경변수(Production):
   - `VITE_API_BASE = https://api.도메인`
   - (필요 시) `NODE_VERSION = 20`
4. Deploy → `xxxx.pages.dev` 생성.
5. **Custom domain**: `app.도메인` 추가(자동 인증서).
6. `frontend/public/_redirects`에:
   ```
   /*   /index.html   200
   ```

---

## Part E. 연결·확인 (순서대로)

1. `https://api.도메인/api/health` → `{"status":"ok"}`
2. `https://app.도메인` → 로그인 화면(YanggBank)
3. `minsu / demo1234!` 로그인 → 개발자도구 Cookies에서 `Secure`·`SameSite=None` 확인
4. "내 잔액 알려줘" → 양쪽 답(ON은 느림)
5. **S1**: OFF 이서연 정보 노출 / ON 차단
6. **S2**: OFF 답변에 코드 + **공격자 기록 탭에 유출 뜸**(A5 덕분) / ON 차단
7. **S3**(추천 칩): OFF 내부 지침 노출 / ON D-09 차단
8. 평가 탭: 서버에서 `python -m eval.run_*` 한 번 돌려야 숫자가 뜸

---

## Part F. 운영 체크리스트

- [ ] 비밀값은 서버 `.env`에만. 깃·Cloudflare 빌드로그 금지
- [ ] OpenAI **월 예산 한도** 설정(공개되면 호출 급증 가능)
- [ ] OFF는 로그인 뒤에만 + CSP 적용 확인(외부 출처 차단)
- [ ] 독립 9999 서버·8000·8000 외부 미개방
- [ ] 로그인 rate-limit 고려(무차별 시도 방지)
- [ ] (선택) Supabase Network Restriction으로 Lightsail IP만 허용
- [ ] 비용: Lightsail 8GB ~$44/월 + 도메인 + OpenAI 사용분

---

## 로컬 전용으로 남기는 것 (배포 안 함)

- `attacker/server.py` 독립 서버(9999): 로컬 개발·발표 시연용. 배포판은 백엔드 수집 엔드포인트(A5)가 대체.
- `KFG_SERVE_FRONTEND`(있다면) 등 로컬 편의 기능.

---

## 요약 순서

1. **Part A**(로컬 코드 변경 A1~A7) → 커밋
2. **Part B** Supabase 확인
3. **Part C** Lightsail 백엔드(인스턴스→모델→.env→PDF재생성→systemd→Caddy/HTTPS)
4. **Part D** Cloudflare Pages 프론트
5. **Part E** 연결 확인
6. **Part F** 운영 점검
