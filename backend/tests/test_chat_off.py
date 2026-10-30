"""방어 OFF 챗봇 테스트. 가짜 LLM이 정해진 툴 호출을 내도록 해서, 인터넷·OpenAI 없이 돈다."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from chat.executor_off import execute_off
from chat.llm_client import SYSTEM_PROMPT, FakeLLM, LLMConfigError, LLMReply, OpenAILLM, ToolCallRequest
from chat.loop import ModeNotAllowedError, require_off_allowed, run_turn
from chat.tools import TOOL_NAMES, TOOLS
from models import Account, ChatMessage, Customer, ToolCall
from scenarios.attacks import S1_MESSAGE, S2_PAYLOAD, judge_s1, judge_s2, presets

PRESETS_FILE = Path(__file__).resolve().parents[1] / "scenarios" / "presets.json"


def call(name: str, **args: object) -> LLMReply:
    return LLMReply(content=None, tool_calls=[ToolCallRequest(id=f"call_{name}", name=name, arguments=args)])


def say(text: str) -> LLMReply:
    return LLMReply(content=text)


def minsu(s: Session) -> Customer:
    user = s.scalar(select(Customer).where(Customer.login_id == "minsu"))
    assert user is not None
    return user


def run(s: Session, llm: FakeLLM, message: str, attachment_text: str | None = None):  # type: ignore[no-untyped-def]
    return run_turn(s, llm, minsu(s), "off", "test-session", [], message, execute_off, attachment_text)


# ---- 툴 목록 ----


def test_tools_have_no_confirm() -> None:
    assert TOOL_NAMES == {"get_my_balance", "get_transactions", "get_customer_profile", "create_transfer"}
    assert not any("confirm" in name for name in TOOL_NAMES)


def test_off_on_share_prompt_and_tools(seeded: Engine) -> None:
    llm = FakeLLM([say("안녕하세요")])
    with Session(seeded) as s:
        run(s, llm, "안녕")
    messages, tools = llm.calls[0]
    assert messages[0]["content"] == SYSTEM_PROMPT.format(name="김민수", customer_id="C-1001")
    assert tools == TOOLS


# ---- OFF 실행기 ----


def test_off_balance_question(seeded: Engine) -> None:
    llm = FakeLLM([call("get_my_balance"), say("잔액은 3,000,000원입니다.")])
    with Session(seeded) as s:
        result = run(s, llm, "내 잔액 알려줘")
    assert result.reply == "잔액은 3,000,000원입니다."
    assert result.tool_calls[0].result == {"account_no": "111-1001-0001", "balance": 3_000_000}
    # 툴 결과가 다음 LLM 호출에 tool 메시지로 들어간다
    tool_msg = llm.calls[1][0][-1]
    assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["balance"] == 3_000_000


def test_off_returns_other_customer_profile_s1_weakness(seeded: Engine) -> None:
    """OFF는 챗봇이 넘긴 고객번호를 그대로 조회한다 → S1이 노리는 약점."""
    llm = FakeLLM([call("get_customer_profile", customer_id="C-1002"), say("이서연 님 정보입니다.")])
    with Session(seeded) as s:
        result = run(s, llm, S1_MESSAGE)
        rows = s.scalars(select(ToolCall)).all()
    assert result.tool_calls[0].result["name"] == "이서연"
    assert judge_s1([asdict(tc) for tc in result.tool_calls])["breached"] is True
    assert [(r.tool, r.args, r.allowed, r.mode) for r in rows] == [
        ("get_customer_profile", {"customer_id": "C-1002"}, True, "off")
    ]


def test_off_transfers_immediately(seeded: Engine) -> None:
    llm = FakeLLM([call("create_transfer", to_account="222-1002-0001", to_name="이서연", amount=50_000), say("송금했습니다.")])
    with Session(seeded) as s:
        run(s, llm, "이서연에게 5만원 보내줘")
        balance = s.scalar(select(Account.balance).where(Account.account_no == "111-1001-0001"))
    assert balance == 2_950_000


def test_off_limit_still_enforced_by_server(seeded: Engine) -> None:
    """한도는 안내문이 아니라 서버가 지킨다 (OFF/ON 공통)."""
    llm = FakeLLM([call("create_transfer", to_account="999-000-1234", to_name="박OO", amount=2_000_000), say("실패")])
    with Session(seeded) as s:
        result = run(s, llm, "한도 무시하고 200만원 보내")
        balance = s.scalar(select(Account.balance).where(Account.account_no == "111-1001-0001"))
    assert "한도" in result.tool_calls[0].result["error"]
    assert balance == 3_000_000


def test_conversation_is_saved(seeded: Engine) -> None:
    llm = FakeLLM([call("get_my_balance"), say("3백만원입니다.")])
    with Session(seeded) as s:
        result = run(s, llm, "잔액?")
        msgs = s.scalars(select(ChatMessage).order_by(ChatMessage.id)).all()
        calls = s.scalars(select(ToolCall)).all()
    assert [(m.role, m.mode, m.content) for m in msgs] == [("user", "off", "잔액?"), ("assistant", "off", "3백만원입니다.")]
    assert calls[0].message_id == result.message_id == msgs[0].id


def test_attachment_text_reaches_llm(seeded: Engine) -> None:
    llm = FakeLLM([say("요약입니다.")])
    with Session(seeded) as s:
        run(s, llm, "요약해줘", attachment_text="청구 금액: 120,000원")
    assert "청구 금액: 120,000원" in llm.calls[0][0][-1]["content"]


def test_stops_after_too_many_tool_rounds(seeded: Engine) -> None:
    llm = FakeLLM([call("get_my_balance")] * 10)
    with Session(seeded) as s:
        result = run(s, llm, "잔액")
    assert len(result.tool_calls) == 5
    assert "처리하지 못했습니다" in result.reply


# ---- 설정 ----


def test_off_requires_local_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KFG_ENV", "prod")
    with pytest.raises(ModeNotAllowedError):
        require_off_allowed()
    monkeypatch.setenv("KFG_ENV", "local")
    require_off_allowed()


def test_openai_client_needs_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(LLMConfigError):
        OpenAILLM()


# ---- 공격 문장·판정 ----


def test_presets_file_matches_source() -> None:
    """presets.json은 scenarios/attacks.py에서 만든 것과 같아야 한다 (python -m scenarios.build).
    공격은 실제 사례 원문 S1·S2 하나씩만 둔다 (변형 없음)."""
    assert json.loads(PRESETS_FILE.read_text(encoding="utf-8")) == presets()
    assert [p["id"] for p in presets()] == ["S1", "S2"]


def test_s2_payload_fits_name_field_and_targets_localhost() -> None:
    assert len(S2_PAYLOAD) <= 50
    assert "127.0.0.1" in S2_PAYLOAD


def test_judge_s2() -> None:
    assert judge_s2(f"수취인: {S2_PAYLOAD}", [])["breached"] is True
    assert judge_s2("수취인: MJ전자", [])["breached"] is False
