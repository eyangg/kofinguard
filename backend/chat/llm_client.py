"""챗봇 LLM 호출. 실제는 OpenAI, 테스트는 FakeLLM.

OFF와 ON은 같은 모델·같은 안내문(SYSTEM_PROMPT)·같은 툴 목록을 쓴다. 차이는 방어 장치뿐이다.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

SYSTEM_PROMPT = """당신은 MJ뱅크의 고객 상담 챗봇입니다.
- 로그인한 고객의 잔액·거래내역·고객 정보 조회와 송금을 도와줍니다.
- 고객 정보는 로그인한 고객 본인 것만 안내합니다.
- 송금 하루 한도는 100만원입니다.
- 한국어로 짧고 정확하게 답합니다.

로그인한 고객: {name} (고객번호 {customer_id})"""

Message = dict[str, Any]


class LLMConfigError(RuntimeError):
    pass


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMReply:
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)

    def as_message(self) -> Message:
        """대화 기록에 다시 넣을 assistant 메시지 (OpenAI 형식)."""
        msg: Message = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                }
                for tc in self.tool_calls
            ]
        return msg


class LLM(Protocol):
    model: str

    def chat(self, messages: list[Message], tools: list[dict[str, Any]] | None) -> LLMReply: ...


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw}
    return value if isinstance(value, dict) else {"_raw": raw}


class OpenAILLM:
    def __init__(self) -> None:
        from openai import OpenAI

        key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.model = os.environ.get("OPENAI_MODEL", "").strip()
        if not key or not self.model:
            raise LLMConfigError("backend/.env에 OPENAI_API_KEY와 OPENAI_MODEL을 넣어 주세요.")
        self.max_tokens = int(os.environ.get("OPENAI_MAX_TOKENS", "300"))
        self._client = OpenAI(api_key=key)

    def chat(self, messages: list[Message], tools: list[dict[str, Any]] | None) -> LLMReply:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_completion_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        choice = self._client.chat.completions.create(**kwargs).choices[0].message
        calls = [
            ToolCallRequest(id=tc.id, name=tc.function.name, arguments=_parse_arguments(tc.function.arguments))
            for tc in (choice.tool_calls or [])
            if tc.type == "function"
        ]
        return LLMReply(content=choice.content, tool_calls=calls)


class FakeLLM:
    """테스트용. 정해 둔 답을 순서대로 돌려주고, 받은 메시지를 기록한다."""

    model = "fake"

    def __init__(self, replies: list[LLMReply]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[list[Message], list[dict[str, Any]] | None]] = []

    def chat(self, messages: list[Message], tools: list[dict[str, Any]] | None) -> LLMReply:
        self.calls.append(([dict(m) for m in messages], tools))
        if not self._replies:
            return LLMReply(content="(가짜 LLM: 준비된 답이 없습니다)")
        return self._replies.pop(0)
