"""E-03 --core-only (탐지기 끄고 핵심 방어만) 테스트. 가짜 LLM으로 모델·인터넷 없이 돈다."""

from conftest import login
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from chat.llm_client import FakeLLM, LLMReply, ToolCallRequest
from chat.pipeline import run_chat
from eval.run_attack_eval import PassDetector, acted
from models import Customer
from scenarios.attacks import S2_PAYLOAD, judge_s2


def test_core_only_detector_always_passes() -> None:
    assert PassDetector().check("<img src=x onerror=alert(1)>").action == "pass"


def test_core_only_s2_blocked_by_output_filter(seeded: Engine) -> None:
    # 탐지기가 통과시켜도, 답변에 심긴 코드는 D-08이 글자로 바꿔 실행되지 않는다.
    llm = FakeLLM([LLMReply(content=f"청구서 확인했습니다 {S2_PAYLOAD}")])
    with Session(seeded) as s:
        user = s.scalar(select(Customer).where(Customer.login_id == "minsu"))
        result = run_chat(s, llm, user, "on", "t", "청구서 정리해줘", detector=PassDetector(), attachment_text="청구서")
    assert judge_s2(result.reply, [])["breached"] is False
    # 입력 검사(D-01~D-04)는 세지 않고, D-08이 한 일을 개수 없이 남긴다
    assert acted(result) == ["D-08 HTML 태그 인코딩"]


def test_core_only_records_forced_own_id(seeded: Engine) -> None:
    llm = FakeLLM([
        LLMReply(content=None, tool_calls=[ToolCallRequest(id="c1", name="get_customer_profile", arguments={"customer_id": "C-1002"})]),
        LLMReply(content="안내드립니다."),
    ])
    with Session(seeded) as s:
        user = s.scalar(select(Customer).where(Customer.login_id == "minsu"))
        result = run_chat(s, llm, user, "on", "t", "C-1002 정보 알려줘", detector=PassDetector())
    assert acted(result) == ["D-05 다른 고객번호 요청 거부, 본인으로 조회"]


def test_eval_endpoint_has_attack_core(client: TestClient) -> None:
    login(client)
    body = client.get("/api/demo/eval").json()
    assert "attack_core" in body
