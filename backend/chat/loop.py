"""대화 한 턴 실행: (방어 입력 검사 →) 챗봇 호출 → 툴 실행 → (방어 출력 처리 →) 최종 답변.

어떤 실행기(OFF/ON)와 방어(Defense)를 쓸지는 호출하는 쪽이 정한다. 대화·툴 호출·방어 판단은
DB에 남긴다(chat_messages, tool_calls, defense_events). 공격 성공 판정은 챗봇 말이 아니라 이 기록으로 한다.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from chat.executor_off import ToolResult
from chat.llm_client import LLM, SYSTEM_PROMPT, Message
from chat.tools import TOOLS
from models import ChatMessage, Customer, DefenseEvent, ToolCall

MAX_TOOL_ROUNDS = 5

Executor = Callable[[Session, Customer, str, dict[str, Any]], ToolResult]


class ModeNotAllowedError(RuntimeError):
    pass


def require_off_allowed() -> None:
    """방어 OFF는 로컬(KFG_ENV=local)에서만 쓴다."""
    if os.environ.get("KFG_ENV", "").strip() != "local":
        raise ModeNotAllowedError("방어 OFF 모드는 KFG_ENV=local일 때만 쓸 수 있습니다 (backend/.env).")


@dataclass
class TraceEvent:
    layer: str  # D-01 ~ D-08
    action: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class InputDecision:
    # proceed=True면 챗봇을 부른다. False면 blocked_reply를 그대로 답으로 쓴다.
    proceed: bool
    blocked_reply: str = ""
    events: list[TraceEvent] = field(default_factory=list)


class Defense(Protocol):
    def check_input(self, message: str, attachment_text: str | None) -> InputDecision: ...
    def wrap_attachment(self, text: str) -> str: ...
    def filter_output(self, reply: str) -> tuple[str, list[TraceEvent]]: ...


class NullDefense:
    """방어 OFF: 입력을 검사하지 않고, 문서를 그대로 넘기고, 답변도 손대지 않는다."""

    def check_input(self, message: str, attachment_text: str | None) -> InputDecision:
        return InputDecision(proceed=True)

    def wrap_attachment(self, text: str) -> str:
        return text

    def filter_output(self, reply: str) -> tuple[str, list[TraceEvent]]:
        return reply, []


NULL_DEFENSE = NullDefense()


@dataclass
class ToolCallRecord:
    tool: str
    args: dict[str, Any]
    allowed: bool
    reason: str | None
    result: dict[str, Any]


@dataclass
class TurnResult:
    reply: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    trace: list[TraceEvent] = field(default_factory=list)
    message_id: int | None = None  # 이번 턴의 사용자 메시지 id (chat_messages)


def system_message(user: Customer) -> Message:
    return {"role": "system", "content": SYSTEM_PROMPT.format(name=user.name, customer_id=user.id)}


def user_content(message: str, attachment_text: str | None) -> str:
    if attachment_text is None:
        return message
    return f"{message}\n\n[첨부 문서 내용]\n{attachment_text}"


def _save_events(session: Session, message_id: int, events: list[TraceEvent]) -> None:
    for e in events:
        session.add(DefenseEvent(message_id=message_id, layer=e.layer, action=e.action, detail=e.detail))


def run_turn(
    session: Session,
    llm: LLM,
    user: Customer,
    mode: str,
    session_id: str,
    history: list[Message],
    message: str,
    executor: Executor,
    attachment_text: str | None = None,
    use_tools: bool = True,
    defense: Defense = NULL_DEFENSE,
) -> TurnResult:
    """history는 이전 턴까지의 대화(시스템 메시지 제외). 이번 턴 내용이 끝에 덧붙여진다."""
    user_msg = ChatMessage(session_id=session_id, mode=mode, role="user", content=message)
    session.add(user_msg)
    session.commit()

    trace: list[TraceEvent] = []
    records: list[ToolCallRecord] = []

    # D-01~D-04, D-07: 입력 검사 (방어 ON에서만 실제로 동작). 위험·판정 불가면 챗봇을 부르지 않는다.
    decision = defense.check_input(message, attachment_text)
    trace.extend(decision.events)
    if not decision.proceed:
        _save_events(session, user_msg.id, decision.events)
        session.add(ChatMessage(session_id=session_id, mode=mode, role="assistant", content=decision.blocked_reply))
        session.commit()
        return TurnResult(reply=decision.blocked_reply, trace=trace, message_id=user_msg.id)

    doc_text = defense.wrap_attachment(attachment_text) if attachment_text is not None else None
    history.append({"role": "user", "content": user_content(message, doc_text)})
    reply = ""
    for _ in range(MAX_TOOL_ROUNDS):
        answer = llm.chat([system_message(user), *history], TOOLS if use_tools else None)
        history.append(answer.as_message())
        if not answer.tool_calls:
            reply = answer.content or ""
            break
        for call in answer.tool_calls:
            result = executor(session, user, call.name, call.arguments)
            records.append(ToolCallRecord(call.name, call.arguments, result.allowed, result.reason, result.content))
            session.add(
                ToolCall(
                    message_id=user_msg.id,
                    mode=mode,
                    tool=call.name,
                    args=call.arguments,
                    allowed=result.allowed,
                    reason=result.reason,
                )
            )
            history.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result.content, ensure_ascii=False)}
            )
        session.commit()
    else:
        reply = "요청을 처리하지 못했습니다. 다시 말씀해 주세요."

    # D-08: 답변 안전 처리 (방어 ON에서만). OFF는 답변을 그대로 둔다(화면이 HTML로 그려 S2 재현).
    reply, filter_events = defense.filter_output(reply)
    trace.extend(filter_events)

    _save_events(session, user_msg.id, decision.events + filter_events)
    session.add(ChatMessage(session_id=session_id, mode=mode, role="assistant", content=reply))
    session.commit()
    return TurnResult(reply=reply, tool_calls=records, trace=trace, message_id=user_msg.id)
