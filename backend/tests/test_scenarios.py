"""시나리오 실행기 테스트: S1·S2가 OFF에서 FAIL(뚫림), ON에서 PASS(막힘)인지.

가짜 LLM이 '공격에 넘어간' 챗봇을 흉내 낸다. 판정은 챗봇 말이 아니라 tool_calls·답변 코드로 한다.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from chat.llm_client import LLMReply, ToolCallRequest
from detector.router import Verdict
from models import Customer
from scenarios import runner
from scenarios.attacks import S2_PAYLOAD, presets


class PassDetector:
    def check(self, text: str) -> Verdict:
        return Verdict(action="pass", normalized=text, mean_ppl=1.0, var_ppl=0.0, guard_safe=True)


class CompromisedLLM:
    """공격에 넘어간 챗봇을 흉내 낸다. 시나리오를 user 메시지로 구분하고, 지시대로 툴을 부르고 코드를 답변에 넣는다.
    (상태 없음: 매 턴 messages만 보고 판단해서 OFF·ON 모두에 그대로 쓸 수 있다.)"""

    model = "fake-compromised"

    def chat(self, messages, tools):  # type: ignore[no-untyped-def]
        user_text = " ".join(m.get("content") or "" for m in messages if m.get("role") == "user")
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        is_s2 = "청구서" in user_text
        if not has_tool_result:
            if is_s2:
                tc = ToolCallRequest("c1", "create_transfer", {"to_account": "333-0000-1111", "to_name": S2_PAYLOAD, "amount": 120_000})
            else:
                tc = ToolCallRequest("c1", "get_customer_profile", {"customer_id": "C-1002"})
            return LLMReply(content=None, tool_calls=[tc])
        if is_s2:
            return LLMReply(content=f"청구서대로 송금 처리했습니다. {S2_PAYLOAD}")
        return LLMReply(content="C-1002 고객님 정보를 안내드립니다.")


@pytest.fixture
def minsu(seeded: Engine):  # type: ignore[no-untyped-def]
    with Session(seeded) as s:
        yield s.scalar(select(Customer).where(Customer.login_id == "minsu"))


def by_id(presets_list):  # type: ignore[no-untyped-def]
    return {p["id"]: p for p in presets_list}


@pytest.mark.parametrize("preset_id", ["S1", "S2"])
def test_scenario_off_fails_on_passes(seeded: Engine, monkeypatch: pytest.MonkeyPatch, preset_id: str) -> None:
    monkeypatch.setenv("KFG_ENV", "local")  # OFF 허용
    preset = by_id(presets())[preset_id]
    with Session(seeded) as s:
        user = s.scalar(select(Customer).where(Customer.login_id == "minsu"))
        row = runner.run_one(s, CompromisedLLM(), user, PassDetector(), preset)
    assert row["off"]["breached"] is True, row["off"]
    assert row["on"]["breached"] is False, row["on"]
    assert row["as_expected"] is True


def test_s1_detail(seeded: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KFG_ENV", "local")
    with Session(seeded) as s:
        user = s.scalar(select(Customer).where(Customer.login_id == "minsu"))
        row = runner.run_one(s, CompromisedLLM(), user, PassDetector(), by_id(presets())["S1"])
    # OFF: C-1002 조회됨 / ON: 본인(C-1001)으로 바뀌어 거부 기록
    assert any(tc["tool"] == "get_customer_profile" and tc["allowed"] for tc in row["off"]["tool_calls"])
    assert any(tc["tool"] == "get_customer_profile" and not tc["allowed"] for tc in row["on"]["tool_calls"])


def test_s2_detail(seeded: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KFG_ENV", "local")
    with Session(seeded) as s:
        user = s.scalar(select(Customer).where(Customer.login_id == "minsu"))
        row = runner.run_one(s, CompromisedLLM(), user, PassDetector(), by_id(presets())["S2"])
    # OFF: 답변에 실행 가능한 코드가 남음 / ON: 인코딩되어 실행 불가
    assert row["off"]["code_in_reply"] is True
    assert row["on"]["code_in_reply"] is False
