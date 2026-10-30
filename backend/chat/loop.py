"""대화 한 턴 실행: 챗봇 호출 → 툴 실행 → 결과를 다시 챗봇에게 → 최종 답변.

어떤 실행기(OFF/ON)를 쓸지는 호출하는 쪽이 정한다. 대화와 툴 호출은 DB에 남긴다
(chat_messages, tool_calls). 공격 성공 판정은 챗봇 말이 아니라 이 기록으로 한다.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from chat.executor_off import ToolResult
from chat.llm_client import LLM, SYSTEM_PROMPT, Message
from chat.tools import TOOLS
from models import ChatMessage, Customer, ToolCall

MAX_TOOL_ROUNDS = 5

Executor = Callable[[Session, Customer, str, dict[str, Any]], ToolResult]


class ModeNotAllowedError(RuntimeError):
    pass


def require_off_allowed() -> None:
    """방어 OFF는 로컬(KFG_ENV=local)에서만 쓴다."""
    if os.environ.get("KFG_ENV", "").strip() != "local":
        raise ModeNotAllowedError("방어 OFF 모드는 KFG_ENV=local일 때만 쓸 수 있습니다 (backend/.env).")


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
    message_id: int | None = None  # 이번 턴의 사용자 메시지 id (chat_messages)


def system_message(user: Customer) -> Message:
    return {"role": "system", "content": SYSTEM_PROMPT.format(name=user.name, customer_id=user.id)}


def user_content(message: str, attachment_text: str | None) -> str:
    if attachment_text is None:
        return message
    return f"{message}\n\n[첨부 문서 내용]\n{attachment_text}"


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
) -> TurnResult:
    """history는 이전 턴까지의 대화(시스템 메시지 제외). 이번 턴 내용이 끝에 덧붙여진다."""
    user_msg = ChatMessage(session_id=session_id, mode=mode, role="user", content=message)
    session.add(user_msg)
    session.commit()

    history.append({"role": "user", "content": user_content(message, attachment_text)})
    records: list[ToolCallRecord] = []
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

    session.add(ChatMessage(session_id=session_id, mode=mode, role="assistant", content=reply))
    session.commit()
    return TurnResult(reply=reply, tool_calls=records, message_id=user_msg.id)
