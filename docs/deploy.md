# KoFinGuard 배포 runbook (포폴 공개용)

> **단일 출처 배포**: `https://bankguard.axworks.site` 한 곳에서 프론트(정적 빌드)와 `/api`를 함께 서빙.
> 백엔드 **AWS Lightsail** · DB **Supabase(PostgreSQL)** · DNS는 강사의 `axworks.site`에 서브도메인 요청.
> 담당자(강사)에게 보여줄 포폴 공개가 목적.

## 0. 결정된 구성

| 항목 | 결정 | 메모 |
|---|---|---|
| 도메인 | **bankguard.axworks.site** (단일) | 강사 `axworks.site`에 서브도메인 1개 요청 |
| 구조 | **한 서버·한 출처** | Lightsail의 Caddy가 프론트 정적파일 + `/api` 리버스프록시. Cloudflare Pages 안 씀 |
| OFF 모드 | **켬** (로그인 뒤에만) | OFF/ON 비교가 핵심. XSS는 CSP로 봉쇄 |
| XSS 대응 | **CSP 중간 정책** (Caddy 헤더) | 삽입 코드 실행은 되되, `connect/img-src 'self'`로 **외부 유출 차단** |
| 탐지기 | **Llama Guard 1b + Qwen GGUF** | 1b 오탐(13%)은 "탐지기 한계→서버 방어 필요" 근거 |
| 공격자 서버 | **독립 9999 서버는 배포 안 함** | 수집은 같은 출처의 `/api/demo/x`·`/collect`가 담당 → 배포판에서도 **실제 유출** 시연 |
| Lightsail | **8GB RAM / 2vCPU** (~$44/월) | Qwen+1b+앱 RAM ~6GB |

**왜 단일 출처가 유리한가**: 프론트와 `/api`가 같은 출처라 **CORS·SameSite=None·교차출처 유출 설정이 전부 불필요**. 유출도 같은 출처(`/api/demo/collect`)로 가서 `CSP connect-src 'self'`만으로 외부를 완전 차단. 성능 체감 차이는 없음(지연은 LLM·탐지기 쪽).

---

## Part A. 로컬 작업 — ✅ 완료 (커밋 `16b2b49` + 쿠키 Secure 옵션)

> 아래는 이미 반영됨. 단일 출처에서는 교차출처 변수(`KFG_FRONTEND_ORIGIN`·`KFG_COOKIE_CROSS_SITE`)를 **비워 두기만** 하면 된다.

- **api.ts**: `VITE_API_BASE` 비우면 상대경로 `/api`(동일 출처). `credentials:'include'`.
- **main.py**: `KFG_FRONTEND_ORIGIN` 비면 CORS 미적용(동일 출처라 불필요).
- **auth.py**: 기본 lax. 단일 출처 HTTPS는 `KFG_COOKIE_SECURE=1`로 Secure 추가.
- **demo.py**: `/api/demo/x`(유출 스크립트)·`/api/demo/collect`(기록) — 같은 출처에서 동작.
- **attacks.py**: S2 payload 목적지 `KFG_ATTACKER_BASE`. 단일 출처는 `/api/demo` → `import('/api/demo/x')`(상대, 같은 출처).
- **.env.example**: Guard 1b + 배포 변수.

> 참고: `frontend/public/_headers`·`_redirects`는 **Cloudflare Pages 분리 배포(부록)**용이다. 단일 출처에서는 Caddy가 CSP·SPA 폴백을 대신하므로 쓰이지 않는다(그냥 둬도 무해).

---

## Part B. Supabase (이미 됨 — 확인만)

1. 대시보드 → **Connect → Session pooler** 연결 문자열 확보(= 백엔드 `DATABASE_URL`).
2. 테이블·RLS 적용 확인(로컬 또는 서버에서):
   ```
   .\.venv\Scripts\python.exe -m alembic -c ..\database\alembic.ini upgrade head
   .\.venv\Scripts\python.exe seed.py
   .\.venv\Scripts\python.exe -m pytest -m postgres
   ```
3. (선택) Supabase **Network Restrictions**에서 Lightsail 고정 IP만 허용.

---

## Part C. Lightsail (프론트+백엔드 한 서버)

1. **인스턴스 생성**: Ubuntu 22.04, **8GB RAM / 2vCPU**.
2. **Static IP** 생성·연결.
3. **방화벽(Networking)**: 22·80·443만 허용. **8000·9999·11434는 열지 않음**(내부 전용).
4. **기본 세팅** (`ssh ubuntu@고정IP`):
   ```bash
   sudo apt update && sudo apt -y upgrade
   sudo apt -y install python3.12 python3.12-venv git curl
   # 프론트 빌드용 Node 20
   curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
   sudo apt -y install nodejs
   ```
5. **코드**:
   ```bash
   git clone https://github.com/eyangg/kofinguard.git
   cd kofinguard
   ```
6. **백엔드 의존성·모델**:
   ```bash
   cd backend
   python3.12 -m venv .venv
   ./.venv/bin/pip install -r requirements.txt
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
   # --- 단일 출처 배포 ---
   KFG_API_ORIGIN=https://bankguard.axworks.site
   KFG_COOKIE_SECURE=1
   KFG_ATTACKER_BASE=/api/demo
   ```
   (`KFG_FRONTEND_ORIGIN`·`KFG_COOKIE_CROSS_SITE`는 넣지 않는다.)
8. **DB 적용**(한 번): `./.venv/bin/python -m alembic -c ../database/alembic.ini upgrade head && ./.venv/bin/python seed.py`
9. **배포용 S2 PDF 재생성** — payload 목적지를 `/api/demo`로:
   ```bash
   KFG_ATTACKER_BASE=/api/demo ./.venv/bin/python -m scenarios.build
   ```
   > `S2_PAYLOAD`은 `attacks.py` **임포트 시점**에 env로 결정된다. 그래서 ① PDF 생성은 위처럼 env를 인라인으로 주고, ② 실행 서비스는 아래 systemd `EnvironmentFile`로 env를 **파이썬 시작 전**에 주입한다.
10. **프론트 빌드** (상대경로 `/api` 사용, 추가 env 불필요):
    ```bash
    cd ../frontend && npm ci && npm run build   # → frontend/dist
    ```
11. **systemd** `/etc/systemd/system/kofinguard.service`:
    ```ini
    [Unit]
    Description=KoFinGuard API
    After=network.target
    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/kofinguard/backend
    EnvironmentFile=/home/ubuntu/kofinguard/backend/.env
    ExecStart=/home/ubuntu/kofinguard/backend/.venv/bin/python -m uvicorn main:app \
      --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
    Restart=always
    [Install]
    WantedBy=multi-user.target
    ```
    ```bash
    sudo systemctl daemon-reload && sudo systemctl enable --now kofinguard
    sudo systemctl status kofinguard
    ```
12. **Caddy (HTTPS + 프론트 서빙 + /api 프록시 + CSP)**:
    - 설치 후 `/etc/caddy/Caddyfile`:
      ```
      bankguard.axworks.site {
          encode gzip
          @api path /api/*
          handle @api {
              reverse_proxy 127.0.0.1:8000
          }
          handle {
              root * /home/ubuntu/kofinguard/frontend/dist
              try_files {path} /index.html
              file_server
          }
          header {
              Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; base-uri 'self'; object-src 'none'; frame-ancestors 'none'"
              X-Content-Type-Options "nosniff"
              Referrer-Policy "no-referrer"
          }
      }
      ```
    - `sudo systemctl restart caddy`
13. **독립 공격자 서버(9999)는 켜지 않는다.** 수집은 `/api/demo/*`가 담당.

---

## Part D. DNS — 강사에게 요청 (한 줄)

- `axworks.site`를 관리하는 강사에게:
  > **`bankguard` A 레코드 → (Lightsail 고정 IP)** 추가, **DNS only(프록시 OFF)** 로 부탁드립니다.
- DNS only여야 Caddy가 자체 Let's Encrypt 인증서를 발급받는다. (Cloudflare 프록시 ON이면 ACME가 막힐 수 있음.)
- 전파 후 Caddy가 자동으로 HTTPS 인증서를 발급한다.

---

## Part E. 연결·확인 (순서대로)

1. `https://bankguard.axworks.site/api/health` → `{"status":"ok"}`
2. `https://bankguard.axworks.site` → 로그인 화면(YanggBank)
3. `minsu / demo1234!` 로그인 → 개발자도구 Cookies에서 `Secure`·`SameSite=Lax` 확인
4. "내 잔액 알려줘" → 양쪽 답(ON은 느림)
5. **S1**: OFF 이서연 정보 노출 / ON 차단
6. **S2**: OFF 답변에 코드 + **공격자 기록 탭에 유출 뜸** / ON 차단
7. **S3**(추천 칩): OFF 내부 지침 노출 / ON D-09 차단
8. 평가 탭: 서버에서 `./.venv/bin/python -m eval.run_detector_eval` / `-m eval.run_attack_eval` 한 번 돌려야 숫자가 뜸

---

## Part F. 운영 체크리스트

- [ ] 비밀값은 서버 `.env`에만. 깃·빌드로그 금지
- [ ] OpenAI **월 예산 한도** 설정(공개되면 호출 급증 가능)
- [ ] OFF는 로그인 뒤에만 + CSP 적용 확인(개발자도구 Network에서 collect가 same-origin인지)
- [ ] 8000·9999·11434 외부 미개방 (22·80·443만)
- [ ] 로그인 rate-limit 고려
- [ ] 코드 갱신 시: `git pull` → 백엔드 `pip install -r requirements.txt`(변경 시) → 프론트 `npm ci && npm run build` → `sudo systemctl restart kofinguard`
- [ ] 비용: Lightsail 8GB ~$44/월 + OpenAI 사용분 (도메인은 강사 것)

---

## 로컬 전용으로 남기는 것 (배포 안 함)

- `attacker/server.py` 독립 서버(9999): 로컬 개발·발표 시연용. 배포판은 `/api/demo/*`가 대체.

---

## 부록: 서브도메인 2개 분리 배포 (대안 — 지금은 안 씀)

프론트 Cloudflare Pages + 백엔드 Lightsail로 나눌 경우에만. 서브도메인 2개(예: `bankguard`·`api.bankguard`) 필요.
- `.env`: `KFG_FRONTEND_ORIGIN=https://bankguard.axworks.site`, `KFG_API_ORIGIN=https://api.bankguard.axworks.site`, `KFG_COOKIE_CROSS_SITE=1`, `KFG_ATTACKER_BASE=//api.bankguard.axworks.site/api/demo`
- 프론트 빌드 env: `VITE_API_BASE=https://api.bankguard.axworks.site`
- CSP는 `frontend/public/_headers`에 api 출처를 명시(코드에 이미 있음). SPA 폴백은 `_redirects`.
- 코드는 그대로(전부 env 분기). 쿠키는 None+Secure, CORS 적용됨.

---

## 요약 순서

1. **Part A** 로컬 작업 ✅
2. **Part B** Supabase 확인
3. **Part C** Lightsail(모델→.env→PDF재생성→프론트빌드→systemd→Caddy)
4. **Part D** 강사에게 DNS 한 줄 요청
5. **Part E** 연결 확인 → **Part F** 운영 점검
