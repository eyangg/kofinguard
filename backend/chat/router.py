"""POST /api/chat (spec 8.5). OFF/ON 챗봇을 화면에서 쓴다.

OpenAI 클라이언트와 탐지기는 처음 쓸 때 한 번만 만든다(탐지기는 Qwen GGUF 로딩이 느리다).
기본 pytest는 이 라우터를 부르지 않는다(파이프라인은 test_defense가 가짜로 직접 검사).
"""

import json
import re
import uuid
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from auth import CurrentUser, DbSession
from attachments import AttachmentError, load_attachment_text
from chat.llm_client import LLMConfigError, OpenAILLM
from chat.loop import ModeNotAllowedError
from chat.pipeline import run_chat
from detector.router import DetectorConfigError, build_detector
from models import PendingTransfer


class ChatRequest(BaseModel):
    mode: str = Field(pattern="^(off|on)$")
    message: str = Field(min_length=1, max_length=4000)
    attachment_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
    trace: list[dict[str, Any]]
    pending_transfer: dict[str, Any] | None = None


class SuggestRequest(BaseModel):
    last_user: str = Field(min_length=1, max_length=4000)
    last_reply: str = Field(min_length=1, max_length=4000)


class SuggestResponse(BaseModel):
    suggestions: list[str]


SUGGEST_SYSTEM = (
    "너는 대화를 보고 사용자가 다음에 할 법한 질문/요청 3개를 제안한다.\n"
    "JSON 외의 텍스트는 출력하지 마라."
)


@lru_cache(maxsize=1)
def _llm() -> OpenAILLM:
    return OpenAILLM()


@lru_cache(maxsize=1)
def _detector():  # type: ignore[no-untyped-def]
    return build_detector()


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
def chat(body: ChatRequest, user: CurrentUser, db: DbSession) -> ChatResponse:
    attachment_text = None
    if body.attachment_id is not None:
        try:
            attachment_text = load_attachment_text(db, user.id, body.attachment_id)[1]
        except AttachmentError as e:
            raise HTTPException(e.status, e.message) from None
    try:
        llm = _llm()
        detector = _detector() if body.mode == "on" else None
        result = run_chat(
            db, llm, user, body.mode, f"web-{uuid.uuid4().hex[:8]}", body.message,
            detector=detector, attachment_text=attachment_text,
        )
    except ModeNotAllowedError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from None
    except (LLMConfigError, DetectorConfigError) as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None

    pending = db.scalar(
        select(PendingTransfer)
        .where(PendingTransfer.customer_id == user.id, PendingTransfer.status == "pending")
        .order_by(PendingTransfer.id.desc())
    )
    pending_out = (
        {"id": pending.id, "to_account": pending.to_account, "to_name": pending.to_name, "amount": pending.amount}
        if pending
        else None
    )
    return ChatResponse(
        reply=result.reply,
        trace=[{"layer": e.layer, "action": e.action, "detail": e.detail} for e in result.trace],
        pending_transfer=pending_out,
    )


def _parse_suggestions(raw: str | None) -> list[str]:
    if not raw:
        return []
    match = re.search(r"\{.*\}", raw, re.DOTALL)  # 코드펜스 등 군더더기 제거
    try:
        data = json.loads(match.group(0) if match else raw)
    except (json.JSONDecodeError, ValueError):
        return []
    items = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for s in items:
        if isinstance(s, str) and s.strip() and s.strip() not in out:
            out.append(s.strip())
    return out[:3]


@router.post("/suggestions")
def suggestions(body: SuggestRequest, _user: CurrentUser) -> SuggestResponse:
    """마지막 대화로 다음에 보낼 만한 메시지 3개를 생성한다. 실패하면 빈 목록(화면은 공격 칩만 보여 준다)."""
    prompt = (
        f"대화:\n사용자: {body.last_user}\n챗봇: {body.last_reply}\n\n"
        "사용자 입장에서 다음에 보낼 만한 메시지 3개를 제안해. 각 20자 안팎, 서로 겹치지 않게.\n"
        '형식: {"suggestions": ["...", "...", "..."]}'
    )
    try:
        reply = _llm().chat(
            [{"role": "system", "content": SUGGEST_SYSTEM}, {"role": "user", "content": prompt}], None
        )
    except Exception:
        return SuggestResponse(suggestions=[])
    return SuggestResponse(suggestions=_parse_suggestions(reply.content))
