# OpenAI API 결제·키 발급 가이드

> ChatGPT Plus 같은 ChatGPT 구독과 API 결제는 **별개**입니다. 구독이 있어도 API는 따로 충전해야 합니다.
> 화면 메뉴 이름은 바뀔 수 있습니다. 비슷한 이름을 찾으면 됩니다.

## 1. 계정 만들기

1. https://platform.openai.com 접속 → 로그인 (ChatGPT 계정 그대로 써도 됨)
2. 처음이면 조직(Organization) 이름 입력 → 아무 이름이나 OK
3. 휴대폰 인증을 요구하면 진행

## 2. 결제 수단 등록 + 충전

1. 오른쪽 위 톱니바퀴(Settings) → 왼쪽 **Billing**
2. **Add payment method** → 해외결제 되는 카드 (Visa/Master 로고) 등록
3. **Add to credit balance** → 금액 **$5~10** 입력 (최소 $5)
   - 세금이 추가로 붙을 수 있음
4. **Auto recharge(자동 충전)은 끄기** → 충전한 만큼만 쓰고 멈춤 (요금 폭탄 방지)

## 3. 사용 한도 설정 (권장)

1. Settings → **Limits** (또는 Billing 안의 usage limit)
2. 월 예산(budget)을 충전 금액과 같게 설정 (예: $10)
3. 알림 기준(notification threshold)도 절반 정도로 설정 (예: $5)

## 4. API 키 발급

1. 왼쪽 메뉴 **API keys** → **Create new secret key**
2. 이름: `kofinguard-local`
3. 생성된 키(`sk-...`)는 **이 화면에서 딱 한 번만** 보임 → 바로 복사

## 5. 키 넣기 (중요)

1. `backend/.env.example`을 복사해서 `backend/.env` 만들기 (Phase 1에서 생김)
2. `backend/.env`에 붙여 넣기:
   ```
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=(Phase 0에서 작은 모델 이름 확인 후 입력)
   ```
3. 하지 말 것:
   - 키를 채팅(Claude 포함)에 붙여 넣기
   - 코드에 직접 쓰기
   - 깃에 올리기 (`.gitignore`에 `.env` 포함 확인)
4. 키가 노출됐다고 생각되면 API keys 화면에서 바로 **Revoke(삭제)** 후 새로 발급

## 6. 모델 고르기

- Settings의 **Pricing** 또는 Models 문서에서 툴 호출(function calling)을 지원하는 **작은 모델(mini 급)** 을 고른다.
- 이 프로젝트 규모(개발 테스트 + 시연 + 공격 평가 수십~백 회)는 $5~10 안에서 충분할 것으로 예상한다. 실제 사용량은 Usage 화면에서 확인한다.
