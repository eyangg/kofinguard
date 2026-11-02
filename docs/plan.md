# KoFinGuard 개발 계획 (PLAN)

> 수업 문서 흐름: MVP → PRD → SPEC → **PLAN**(이 문서)

## 1. 계획의 목적

이 문서는 `spec.md`에 정한 기능을 **어떤 순서로 개발할지** 정한 순서표입니다.
한 번에 너무 많은 내용을 다루지 않도록 작업을 작은 Phase로 나눕니다. 한 번의 작업에서는 Phase 하나만 진행하고, 확인 기준을 모두 통과한 뒤 다음 Phase로 넘어갑니다.

기간은 10/30(금)부터 11/6(금) 발표 전까지입니다. 수업 일정상 11/6 오후는 산출물 정리와 발표입니다.

## 2. 개발 원칙

- `spec.md`에 없는 기능은 추가하지 않습니다.
- 각 Phase를 시작하기 전에 AI는 **내가 해야 할 일, 넣어야 할 값, 정해야 할 내용**을 먼저 알려줍니다.
- 각 Phase가 끝나면 다음 순서로 마무리합니다.
  1. 자동 테스트를 실행합니다.
  2. 사람이 직접 화면이나 결과를 확인합니다.
  3. `docs/learning_log.md`에 3줄을 씁니다.
  4. 커밋·푸시합니다.
- 확인에 실패하면 다음 Phase로 넘어가지 않고 현재 Phase만 고칩니다.
- 화면에서 버튼을 숨기는 것만으로 권한을 처리하지 않습니다. 서버에서도 검사합니다.
- 비밀값은 `backend/.env`에만 둡니다. 코드에 쓰거나 화면·답변에 보여주지 않습니다.
- `.env`, `.venv`, `node_modules`, `dist`, `__pycache__`, 로그, `models/`, `artifacts/`, `backend/uploads/`, `capstone_ref/`, SQLite 파일은 Git에서 제외합니다.
- Git 커밋은 사람이 요청할 때만 합니다.
- OFF 챗봇과 공격자 서버는 127.0.0.1에서만 실행합니다.

## 3. 전체 개발 순서

| Phase | 만드는 결과 | 다음 Phase로 넘어가기 위한 핵심 조건 |
|---|---|---|
| 0 | 개발 기준과 환경 확인 + 사람 준비 | 문서 충돌 없음, 키·모델·졸프 코드 준비 완료 |
| 1 | 실행되는 프로젝트 뼈대 | 빈 FastAPI·React 화면이 각각 실행됨 |
| 2 | 테이블 구조와 시드 데이터 (SQLite) | Alembic 명령 하나로 테이블 생성, 시드 확인 |
| 3 | 로그인·로그아웃 | 로그인·접근 제한 테스트 통과 |
| 4 | 가상 은행 기능 | 조회·송금·한도·원자성 테스트 통과 |
| 5 | 챗봇 OFF + 문서 첨부 + 공격자 서버 | 실제 API로 S1·S2가 OFF에서 뚫리는지 관측 기록 |
| 6 | 졸프 탐지 모듈 이식 | 실제 모델로 판정, 점수 기준값 결정 |
| 7 | 방어 장치 + 챗봇 ON + 시나리오 실행기 | S1·S2 OFF FAIL → ON PASS 실제 관측 |
| 8 | Supabase 연결 | 시연 데이터가 Supabase에 저장됨, RLS 확인 |
| 9 | Figma → React 비교 화면 | 화면에서 S1·S2 시연 가능, 빌드 성공 |
| 10 | 정량 평가 (탐지기 운영 지표, 공격 성공률) | E-02·E-03 표가 실제 결과로 생성 |
| 11 | 통합 확인·문서·발표 준비 | PRD 7장 완성 기준 전부 통과, 리허설 |

## 4. Phase별 상세 계획

### Phase 0. 개발 시작 전 기준 확인

**목표:** 코드를 만들기 전에 문서, 도구, 실행 환경, 사람 준비물을 확인합니다.

**작업 (AI)**
1. `mvp.md`, `prd.md`, `spec.md`, `plan.md`의 범위가 서로 맞는지 확인합니다.
2. Python 3.12, Node, Ollama 설치 여부를 읽기 전용 명령으로 확인합니다.
3. 서버 주소(백엔드 127.0.0.1:8000, 프론트 5173, 공격자 9999), 환경변수 이름, 테스트·실행 명령을 정리합니다.

**사람이 할 일**
- OpenAI 결제·키 발급·월 예산 설정 (`docs/setup_api.md`). 쓸 모델 이름 결정.
- Supabase 준비. 무료는 활성 프로젝트 2개까지라서 BankGuard 프로젝트를 일시정지할지 재사용할지 결정.
- Ollama 설치 → `ollama pull llama-guard3:8b` (졸프와 같은 8B·4bit 조건. 약 5GB)
- Qwen2.5-3B-Instruct GGUF(Q4_K_M) 다운로드 → `models/`
- 졸프 코드 중 **내 담당 부분**(자모 분해 전처리, SmoothPPL, Llama Guard 연동, 평가 스크립트)과 데이터셋을 `capstone_ref/`에 복사
- GitHub 새 저장소 만들기 (비공개 권장)

**예상 변경 파일:** 없음 (확인 결과만 보고)

**확인 방법:** 확인 결과 표를 읽고 막힌 항목이 없는지 봅니다.

**완료 조건:** 위 준비물이 모두 체크되고 다음 Phase 진행을 사람이 승인합니다.

### Phase 1. 프로젝트 뼈대 만들기

**목표:** 기능 없이도 백엔드와 화면이 각각 켜지게 합니다.

**작업**
1. `frontend`, `backend`, `database`, `docs` 폴더와 `README.md`
2. `.gitignore` (2장 목록), `backend/.env.example` (항목과 설명만)
3. `backend/.venv`, `requirements.txt` (정확한 버전 기록), FastAPI `/api/health`
4. `frontend`: Vite + React + TypeScript(strict), `/api` 프록시, 빈 첫 화면
5. pytest 설정과 빈 테스트 1개

**예상 변경 파일:** `README.md`, `.gitignore`, `backend/main.py`, `backend/requirements.txt`, `backend/.env.example`, `frontend/*`, `backend/tests/test_health.py`

**확인 방법:**
- 백엔드·프론트 각각 실행합니다.
- 브라우저에서 health 결과가 보이는지 확인합니다.
- `git status`에 `.env`가 안 보이는지 확인합니다.

**완료 조건:** 두 서버가 오류 없이 켜지고, pytest가 통과합니다.

### Phase 2. 테이블 구조와 시드 데이터

**목표:** SPEC 8.3의 테이블을 만들고 시연 데이터를 넣습니다. 지금은 SQLite로 합니다.

**작업**
1. SQLAlchemy 모델 + `database/`에 Alembic 설정과 첫 마이그레이션
2. 시드 스크립트 (김민수, 이서연, 계좌, 가짜 대출 정보, 비밀번호는 해시로 저장)
3. DB 연결 계층: `DATABASE_URL`을 읽고, 없으면 시작을 멈추고 안내 (테스트는 임시 SQLite)

**예상 변경 파일:** `backend/db.py`, `backend/models.py`, `backend/seed.py`, `database/alembic*`, `backend/tests/test_db.py`

**확인 방법:**
- Alembic 명령 하나로 테이블이 생기는지 확인합니다.
- 두 번 실행해도 오류가 없는지 확인합니다.
- 서버를 껐다 켜도 데이터가 남는지 확인합니다.
- 비밀번호 원문이 DB에 없는지 확인합니다.

**완료 조건:** DB 테스트가 통과하고, 사람이 시드 데이터를 확인합니다.

### Phase 3. 로그인·로그아웃

**목표:** SPEC 2장을 만듭니다.

**작업:**
- 로그인 API, httpOnly 쿠키 세션, `get_current_user`, 로그아웃
- 로그인 안 하면 401

**예상 변경 파일:** `backend/auth.py`, `backend/main.py`, `backend/tests/test_auth.py`

**확인 방법:** SPEC 2.1·2.2의 확인 방법 전부를 테스트로 확인합니다.

**완료 조건:** 테스트가 통과하고, 사람이 `/docs`(Swagger)에서 직접 로그인해 봅니다.

### Phase 4. 가상 은행 기능

**목표:** 챗봇이 부를 은행 기능을 먼저 단독으로 완성합니다 (SPEC 3.1~3.4의 서버 부분).

**작업**
1. 잔액·거래내역 조회 (F-01, F-02)
2. 고객 정보 조회 (F-05)
3. 송금 (F-03): 출금·입금·기록을 한 번에 처리. 금액은 정수만.
4. 하루 한도 계산 (F-06), 송금 대기와 확인 API (F-04)

**예상 변경 파일:** `backend/bank/*`, `backend/main.py`, `backend/tests/test_bank.py`

**확인 방법:**
- 정상 송금 시 잔액이 바뀌는지 확인합니다.
- 0원·음수·잔액 부족·한도 초과가 거절되는지 확인합니다.
- 중간에 실패하면 전부 취소되는지 확인합니다.
- 남의 대기 건은 확인할 수 없는지 확인합니다.

**완료 조건:** 은행 테스트가 통과합니다.

### Phase 5. 챗봇 OFF + 문서 첨부 + 공격자 서버

**목표:** 방어 없는 챗봇을 만들고, 최근 공격이 실제로 뚫리는지 관측합니다.

**작업**
1. `chat/llm_client.py`: OpenAI 호출 + 테스트용 가짜 LLM. 키만 넣으면 동작하게 합니다.
2. `chat/tools.py`: 툴 목록 (확인 API는 넣지 않음)
3. `chat/executor_off.py`: 챗봇이 준 값을 그대로 실행 (SPEC 3.2·3.3의 OFF 동작)
4. 문서 첨부 API: `backend/uploads/` + `attachments` 테이블, PDF·txt 글자 추출 (SPEC 3.5)
5. `attacker/server.py`: 127.0.0.1:9999, 받은 요청을 `artifacts/attacker_log.jsonl`에 기록
6. `scenarios/presets.json`(S1, S2 원문만), S2 청구서 PDF 1개(흰 글씨 숨은 지시, 숨긴 코드는 127.0.0.1로만 전송), 명령줄 대화 도구 (`--mode off`)

**예상 변경 파일:** `backend/chat/*`, `backend/attacker/server.py`, `backend/scenarios/*`, `backend/tests/test_chat_off.py`

**사람이 할 일:**
- 명령줄로 정상 대화를 직접 해 봅니다.
- S1·S2를 직접 넣어 봅니다. S2는 챗봇 답변에 숨긴 코드 문자열이 그대로 들어가는지 확인합니다 (화면 실행은 Phase 9).
- 뚫리지 않으면 문장 표현을 바꿀지 정합니다 (PRD 10장 미정 항목).

**확인 방법:** 가짜 LLM 테스트가 통과하는지 확인합니다. 실제 API 관측 결과는 `artifacts/observe_off.json`에 기록합니다.

**완료 조건:** S1·S2 OFF 관측 결과가 기록됩니다. 뚫리지 않은 것도 그대로 기록합니다.

### Phase 6. 졸프 탐지 모듈 이식

**목표:** SPEC 4.1 흐름(D-01~D-04, 보조 레이어)을 만듭니다. 졸프 파이프라인(자모 분해 → SmoothPPL → Llama Guard)을 그대로 살리고, 새 단계는 붙이지 않습니다.

**작업**
1. 사람이 지정한 `capstone_ref/` 파일에서 자모 분해 전처리를 `detector/normalize.py`로 옮깁니다. 원본과 같은 결과가 나오는지 테스트합니다.
2. SmoothPPL을 `detector/smoothppl.py`로 옮깁니다 (`llama-cpp-python` + Qwen GGUF, CPU).
3. 졸프 코드에서 SmoothPPL과 Llama Guard 결과를 원래 어떻게 합쳤는지 확인해 보고합니다. SPEC 4.1 초안과 다르면 사람에게 묻습니다.
4. `detector/guard.py`: Ollama Llama Guard 3-8B(4bit) 호출. 판정 1회 시간을 재서, 시연에 너무 느리면 사람에게 알리고 1B(`llama-guard3:1b`)로 바꿀지 묻는다
5. `detector/router.py`: 4.1 흐름대로 판정 결과를 반환합니다. 모델이 꺼져 있으면 통과시키지 않습니다.
6. 정상 문장 30개의 점수 분포를 보여 주고 기준값 후보를 제안합니다.

**예상 변경 파일:** `backend/detector/*`, `backend/tests/test_detector*.py`

**사람이 할 일:**
- 이식할 졸프 파일을 지정합니다.
- 기준값을 정해서 `.env`에 넣습니다.
- 정상 은행 질문과 S1·S2 입력에 대한 판정 결과를 눈으로 확인합니다.
- 지금 `capstone_ref/`의 노트북 2개에는 Llama Guard 코드가 없습니다. 연동 코드가 있으면 추가로 넣습니다.

**확인 방법:**
- 기본 pytest(가짜 탐지기)를 실행합니다.
- `pytest -m models`로 실제 모델을 확인합니다.
- 단계별 걸린 시간을 기록합니다.

**완료 조건:** 테스트가 통과하고 기준값이 결정됩니다.

**주의:** Windows에서 `llama-cpp-python` 설치가 실패하면 CPU용으로 미리 만들어진 설치 파일을 먼저 시도합니다. 그래도 안 되면 대안만 보고하고 멈춥니다.

### Phase 7. 방어 장치 + 챗봇 ON + 시나리오 실행기

**목표:** SPEC 4.2~4.4와 5장을 완성합니다.

**작업**
1. `chat/executor_on.py`: 본인 번호로 바꿔서 실행, 한도 검사, 송금은 대기만 (D-05, D-06)
2. 첨부 문서 격리: 신뢰할 수 없는 문서 표시, 문서 값 허용 문자 검사 (D-07)
3. `chat/output_filter.py`: HTML 인코딩, 링크·이미지 제거, 계좌번호 가리기 (D-08)
4. `chat/pipeline.py`: OFF/ON 흐름, 판단 근거(trace) 기록
5. `scenarios/runner.py`: S1·S2를 OFF/ON으로 실행하고 `tool_calls`·공격자 기록으로 판정. S2는 브라우저 없이도 판정되도록, 답변에 실행 가능한 HTML이 남는지 검사 + Phase 9 이후 브라우저 확인

**예상 변경 파일:** `backend/chat/*`, `backend/scenarios/runner.py`, `backend/tests/test_defense.py`, `backend/tests/test_scenarios.py`

**확인 방법:** 가짜 LLM으로 S1·S2 OFF FAIL / ON PASS 테스트를 통과시킵니다. 실제 API 결과는 `artifacts/scenarios.json`에 기록합니다.

**완료 조건:** 테스트가 통과하고, 사람이 runner 결과와 근거를 읽고 납득합니다.

### Phase 8. Supabase 연결 (수업 06강 방식)

**목표:** 시연 데이터를 Supabase PostgreSQL에 저장합니다.

**작업**
1. `backend/.env.example`에 `DATABASE_URL`(Session pooler) 설명을 씁니다.
2. Alembic으로 같은 테이블을 생성하는 명령을 준비합니다.
3. RLS 활성화 + `anon`·`authenticated` 권한 회수 마이그레이션
4. 연결 정보가 없거나 틀리면 확인할 것을 안내합니다. SQLite로 넘어가지 않습니다.

**사람이 할 일:** Supabase에서 Session pooler 연결 문자열을 복사해 `backend/.env`에 넣습니다. 채팅에 붙여 넣지 않습니다.

**예상 변경 파일:** `backend/.env.example`, `database/*`, `backend/tests/test_postgres.py`

**확인 방법:**
- 로그인하고 대화했을 때 Supabase Table Editor에 기록이 보이는지 확인합니다.
- `pytest -m postgres`를 실행합니다.
- 기본 pytest는 여전히 오프라인으로 통과하는지 확인합니다.

**완료 조건:** 위 확인을 모두 통과합니다. 연결 전에는 "완료"로 보고하지 않습니다.

### Phase 9. Figma → React 비교 화면 (수업 07강 방식)

**목표:** PRD 6장 화면(U-01~U-06)을 만듭니다.

**작업**
1. (사람) Figma로 화면을 그립니다: 로그인, 비교 채팅, 근거 패널, 송금 대기 카드, 공격자 기록, 평가 결과.
2. Figma MCP로 디자인을 읽고, 무엇을 읽었는지 먼저 설명하게 합니다.
3. React 화면을 만듭니다.
   - OFF 패널은 답변을 HTML로 그립니다 (S2 재현용, 취약. 127.0.0.1 전용).
   - ON 패널은 답변을 텍스트로만 그립니다.
4. 공격 버튼 하나로 양쪽에 동시 전송합니다.

**예상 변경 파일:** `frontend/src/*`

**사람이 할 일:**
- Figma 작업을 합니다.
- 브라우저에서 S1·S2를 직접 시연합니다. S2는 OFF에서 공격자 서버 기록이 생기고 ON에서는 0건인지 확인합니다.
- Network 탭에서 Supabase 주소로 가는 요청이 없는지 확인합니다.

**확인 방법:** `npm run build`가 성공하는지 확인합니다. 화면 확인 순서는 화면 → Console → Network → 백엔드 터미널입니다.

**완료 조건:** 화면에서 S1·S2 OFF/ON 결과와 근거가 보입니다.

### Phase 10. 정량 평가

**목표:** SPEC 7장 평가표를 만듭니다.

**작업**
1. `eval/datasets/`: 정상 은행 질문 30~50개 + S1 문장 + S2 청구서 추출 글자.
2. `run_detector_eval.py`: 탐지기 운영 지표 — 정상 질문 오탐률·다시 묻기 개수, 단계별 판정 시간, S1·S2 판정 결과 (SPEC 7.1)
3. `run_attack_eval.py`: S1·S2 공격 성공률을 OFF/ON으로 계산합니다. 결과는 캐시합니다.
4. 결과를 `artifacts/`와 `eval_runs`에 저장하고 화면 U-06에 표시합니다.

**사람이 할 일:**
- 정상 문장 오탐률 목표를 정합니다.
- 발표 메시지를 정합니다.

**예상 변경 파일:** `backend/eval/*`, `frontend/src/*`(결과 화면)

**확인 방법:** 표에 실행 환경이 적혔는지 확인합니다. 몇 문장은 직접 넣어 표와 같은 판정이 나오는지 확인합니다.

**완료 조건:** E-02·E-03 표가 실제 결과로 존재합니다.

### Phase 11. 통합 확인·문서·발표 준비

**작업**
1. PRD 7장 완성 기준을 하나씩 확인합니다.
2. `README.md`를 씁니다. 소개, 실행 방법(백엔드·프론트·공격자 서버·Ollama 터미널), 결과 요약 표를 넣습니다.
3. `docs/threat_model.md`: 데이터 흐름, 신뢰 경계(사용자 입력·첨부 문서·챗봇 답변), 시나리오별 방어
4. `docs/limitations.md`: 졸프(bitsandbytes 4bit)와 Ollama(GGUF 4bit) 양자화 방식 차이, (1B로 내렸다면) 1B 한국어 한계, CPU 속도, 챗봇 답변이 매번 다를 수 있음, 탐지기를 우회하는 공격
5. `docs/demo_script.md`: 3분/5분 시연 대본, 예상 질문

**사람이 할 일:** 리허설 1회, **시연 녹화(백업)**, 예상 질문 답변 연습.

**완료 조건:** 완성 기준이 모두 체크되고 녹화본이 있습니다.

## 5. 확장 (Phase 11 이후, 남는 시간에만)

| ID | 내용 | 완료 조건 |
|---|---|---|
| X1 | **S3 직원 개인정보 유출** (2026년 5월 미국 CB Financial: 직원이 고객 이름·생년월일·사회보장번호를 승인 안 된 외부 AI 앱에 입력, SEC 공시). 직원 계정 + 업무 보조 챗봇 모드를 추가하고, OFF는 붙여넣은 주민번호·계좌번호를 그대로 OpenAI로 보내고 ON은 보내기 전에 마스킹(D-09). 판정은 외부로 보낸 요청 기록에 원문 개인정보가 있는지로 함 | OFF FAIL → ON PASS, 시연 1회 |
| X2 | GitHub Actions: pytest + 프론트 빌드 | CI 성공 |

## 6. 날짜별 목표

| 날짜 | 목표 |
|---|---|
| 10/30(금) | Phase 0 → 1 → 2 → 3 → 4 |
| 10/31~11/1 (주말) | 여유: 밀린 Phase, Phase 5, Figma 초안 |
| 11/2(월) | Phase 5 마무리, Phase 6, Phase 7 |
| 11/3(화) | Phase 8, Phase 9 |
| 11/4(수) | Phase 9 마무리, Phase 10 |
| 11/5(목) | Phase 11, 리허설·녹화, 남으면 X1 |
| 11/6(금) | 오전 최종 점검, 오후 산출물 정리·발표 |

**일정이 밀리면 줄이는 순서:**
1. 확장 X1·X2
2. E-03 반복 횟수 (10 → 5)
3. 근거 패널 꾸미기
4. E-02 정상 질문 수 (50 → 30)

S1·S2 OFF/ON 시연과 E-02 표는 줄이지 않습니다. X1을 못 하면 발표에 "향후 과제" 한 장으로 넣습니다.

## 7. 진행 기록

> Phase가 끝날 때마다 AI가 "완료한 것 / 다음 할 일"을 한 줄씩 남깁니다.

| Phase | 상태 | 완료한 것 | 다음 할 일 |
|---|---|---|---|
| 0 | 완료 | 문서 범위 대조, Python 3.12.10·Node 24·Git·Ollama 0.40(llama-guard3:1b) 확인, Qwen GGUF 무결성 확인(2,104,932,768B, GGUF), 졸프 노트북 2개 `capstone_ref/` 확인, 포트 8000·5173·9999 비어 있음. Supabase는 BankGuard 재사용 결정. GitHub: eyangg/kofinguard. `OPENAI_API_KEY` 입력됨 | `OPENAI_MODEL`은 Phase 5 전까지 결정 |
| 1 | 완료 (브라우저 확인됨) | `backend/.venv`(3.12)·FastAPI `/api/health`·pytest(마커 llm/models/postgres 기본 제외) 1 passed, Vite+React+TS(strict) 빌드 성공·`/api` 프록시 확인, `.gitignore`·`.env.example`·README, `git init`+origin 연결(커밋 안 함), `.env`·models·capstone_ref 제외 확인 | 사람: 두 서버 직접 실행·브라우저 확인, learning_log 작성, 커밋 요청 → Phase 2 |
| 2 | 완료 (서버·화면 확인됨) | SQLAlchemy 모델 9개(email·to_name 포함), `database/` Alembic + 첫 마이그레이션, `db.py`(DATABASE_URL 없거나 연결 실패 시 멈춤, SQLite 상대경로는 backend 기준), `seed.py`(김민수·이서연, PBKDF2 해시, 재실행 안전), `passwords.py`. pytest 11 passed. 실제 흐름(임시 SQLite): 서버 미설정 시 종료, upgrade 2회, seed 2회, 재시작 후 데이터 유지 확인 | 사람: `.env`에 `DATABASE_URL=sqlite:///./kofinguard.db` 추가 → upgrade·seed 직접 실행, learning_log → Phase 3 |
| 3 | 완료 | `auth.py`: 로그인(httpOnly·SameSite=lax 쿠키, 서명된 무작위 세션 ID, 서버 메모리 세션 8시간), 로그아웃(서버 세션 삭제), `get_current_user`, `GET /api/me`. `KFG_SESSION_SECRET` 없으면 서버 시작 안 함. pytest 24 passed. 실제 서버: 미로그인 401, 틀린 비번 401, 로그인 200, 로그아웃 후 이전 쿠키 401 확인. `/api/chat` 401은 Phase 5에서 확인 | 사람: `.env`에 `KFG_SESSION_SECRET` 추가, `/docs`에서 직접 로그인, learning_log → Phase 4 |
| 4 | 완료 | `bank/service.py`: 잔액·거래내역·고객 정보 조회, 송금(출금·입금·기록 한 트랜잭션, 실패 시 전부 취소), 금액 정수 검사, 잔액·하루 한도 100만원(KST 0시 기준, OFF/ON 공통), 송금 대기(5분)·확인(본인만, 1회, 실행 시 재검사). `bank/router.py`: `GET /api/accounts/me`, `GET /api/transactions`, `POST /api/transfers/{id}/confirm`. pytest 47 passed. DB 복사본으로 실제 API 확인 | 사람: Swagger로 조회 API 확인 → Phase 5 (`OPENAI_MODEL` 결정 필요) |
| 5 | 완료 | `OPENAI_MODEL=gpt-4.1-mini` 결정. `chat/`(llm_client+FakeLLM, tools 4개·확인 없음, executor_off, loop), `attachments.py`(POST /api/attachments, PDF·txt 1MB, pypdf 추출, 본인만), `attacker/server.py`(127.0.0.1:9999, /x 스크립트·/c 수집, attacker_log.jsonl), `scenarios/`(attacks.py S1·S2 원문, presets.json 2개, 청구서 PDF 1개 흰 글씨, cli.py → observe_off.json), `seed.py --reset`. 문서 변경(8장)에 따라 자모·사투리 변형 삭제. 1차 관측: S1·S2 모두 OFF 안 뚫림 → DB 복사본으로 후보 실험 후 표현 확정: S1 '상담 메모 위장', S2 '전자영수증 태그 위장' (안내문은 변경 없음). 최종 관측(`artifacts/observe_off.json`): **S1 뚫림(C-1002 조회), S2 뚫림(답변에 코드)**. pytest 73 passed | Phase 6 (졸프 탐지 파이프라인, 보조 레이어). spec 5.1의 S1 원문 예시 문장 갱신 여부는 사람 결정 |
| 6 | 완료 | `detector/`: normalize(졸프 셀3 NFC 그대로), smoothppl(졸프 셀3 잡음 10%·표본 15개, llama-cpp-python 0.3.36 CPU + Qwen GGUF, 문장별 고정 seed), guard(Ollama, 출력 해석 실패·연결 불가 시 판정 불가), router(Guard 위험→차단 / 평균 PPL>기준→다시 묻기 / 그 외 통과, 모델 꺼지면 통과 안 함). 결정: 결합 규칙=평균 PPL만(평균+분산은 결과 동일·근거 논문 없음), `KFG_PPL_THRESHOLD=5000`, Guard=`llama-guard3:1b`, 문서도 표본 15개. 보정(`artifacts/detector_calibration.json`): 정상 30개 중 통과 26·차단 4(Guard 1b 오탐)·다시 묻기 0, S1 차단(분류 S1), S2 청구서 차단(S2). 평균 SmoothPPL 4.5초, Guard 0.7초, 문서 SmoothPPL 약 33초. pytest 88 passed, `-m models` 3 passed | 사람: `.env`에 KFG_QWEN_GGUF_PATH·KFG_GUARD_MODEL=llama-guard3:1b·KFG_PPL_THRESHOLD=5000 추가 → Phase 7. 주의: Guard 1b가 정상 질문 4개를 막음(ON 시연 때 재확인), 졸프 원본 파일을 찾으면 부품 교체 |
| 7 | 완료 (사람 확인 대기) | `chat/executor_on.py`(D-05 본인 번호 강제, D-06 송금 대기만, D-07 수취인 이름 허용 문자 검사), `chat/document_guard.py`(신뢰할 수 없는 문서 표시 + 이름 검사), `chat/output_filter.py`(D-08 HTML 인코딩·링크/이미지 제거·계좌 마스킹), `chat/loop.py`(Defense 훅으로 입력 검사·문서 격리·출력 처리 통합, defense_events 기록·trace 반환), `chat/pipeline.py`(OFF=NullDefense, ON=OnDefense+탐지기), `chat/router.py`(POST /api/chat, LLM·탐지기 lru_cache), `scenarios/runner.py`. judge_s2를 '실행 가능한 태그' 기준으로 수정. pytest 109 passed. 실제 실행: `scenarios.json` S1·S2 모두 OFF FAIL→ON PASS, `/api/chat` 미로그인 401·정상 통과·S1 차단 | 사람: (선택) `scenarios.runner` 직접 실행, learning_log 확인 → Phase 8 (Supabase) |
| 8 | 완료 | psycopg2-binary, RLS 마이그레이션(`a1rls2026`, PostgreSQL ENABLE RLS + anon·authenticated 권한 회수, FORCE 안 함, SQLite no-op), `db.py` postgresql 드라이버 psycopg2로 통일, `test_postgres.py`. BankGuard 기존 9개 테이블(users·audit_log 등) 사람 확인 후 DROP → Supabase에 KoFinGuard 9개 테이블+RLS 생성+시드. 검증: `pytest -m postgres` 4 passed(테이블·RLS·anon 권한 없음·백엔드 읽기쓰기), 앱 로그인·잔액 조회 성공, 기본 pytest 109 passed | Phase 9 (Figma→React 화면). 시연 시 `.env` DATABASE_URL=Supabase 유지 |
| 9 | 완료 (좌우 비교 화면 확인됨, 공격 시연 미확인) | Figma 없이 React로 구현. `demo.py`(presets·attacker-log·attachment, suggestions). 프론트: Login, 비교 채팅(좌 OFF/우 ON 나란히+토글, 공격·추천 칩을 입력 박스 안에, 첨부 자동+직접 업로드 📎·✕), ChatPanel(OFF=HTML 렌더 S2 재현·ON=텍스트), TracePanel(쉬운 말, D-04=D1~D3 종합, Guard 분류 숨김), 송금 대기 카드, AttackerLog 탭, LLM 추천 답장. 토스 스타일 디자인. 사용자 다수 UI 요청 반영. npm build 성공, 기본 pytest 109 passed | 사람: 브라우저에서 S1·S2 OFF뚫림/ON막힘 끝까지 시연 확인 → Phase 10 |
| 10 | 대기 | | |
| 11 | 대기 | | |

## 8. 문서 변경 기록

- 10/30: 시나리오를 실제 사례 원문만 쓰도록 변경. 자모·사투리 변형 공격(attacks.py 변형, presets 변형 버튼, 변형 PDF 2개)은 삭제 대상. 핵심 방어는 서버 쪽(D-05~D-08), 졸프 파이프라인(D-01~D-04)은 보조 레이어. E-02는 졸프 데이터셋 비교 대신 탐지기 운영 지표(정상 질문 오탐, 속도, S1·S2 판정)로 변경.
- 11/02: 은행 이름 MJ뱅크→YanggBank(양갱뱅크). **S3 프롬프트 유출 공격 + D-09 방어 추가**(실측: OFF 시스템 프롬프트 전문 유출, ON 차단). S1·S2와 다른 유형이나 직접 피해가 작아 고정 버튼이 아니라 화면 추천 묶음에만 섞음. D-09 한계(영어 번역 우회)는 limitations에 기록. 화면: 토스 스타일, 거래내역 마크다운 표, 추천 답장(공격 1+일반 2).
