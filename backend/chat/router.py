"""POST /api/chat (spec 8.5). OFF/ON 챗봇을 화면에서 쓴다.

OpenAI 클라이언트와 탐지기는 처음 쓸 때 한 번만 만든다(탐지기는 Qwen GGUF 로딩이 느리다).
기본 pytest는 이 라우터를 부르지 않는다(파이프라인은 test_defense가 가짜로 직접 검사).
"""

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
