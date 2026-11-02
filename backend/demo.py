"""화면용 데모 API (spec 8.5): 공격 버튼 목록, 공격 첨부 준비, 공격자 서버 기록."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from attacker.server import read_log
from attachments import save_attachment
from auth import CurrentUser, DbSession
from scenarios.attacks import extra_presets, presets


def _all_presets() -> list[dict[str, Any]]:
    # pinned=True는 고정 공격 버튼(S1·S2), False는 추천 묶음에 섞는 추가 공격
    return [{**p, "pinned": True} for p in presets()] + [{**p, "pinned": False} for p in extra_presets()]

DOCS_DIR = Path(__file__).resolve().parent / "scenarios" / "docs"

router = APIRouter(prefix="/api/demo", tags=["demo"])


class PresetInfo(BaseModel):
    id: str
    label: str
    message: str
    has_attachment: bool
    pinned: bool  # True=고정 공격 버튼, False=추천 묶음에 섞는 추가 공격


class AttachRequest(BaseModel):
    preset_id: str


@router.get("/presets")
def list_presets() -> list[PresetInfo]:
    return [
        PresetInfo(
            id=p["id"], label=p["label"], message=p["message"], has_attachment=bool(p["attachment"]), pinned=p["pinned"]
        )
        for p in _all_presets()
    ]


class AttachResult(BaseModel):
    attachment_id: int
    filename: str


@router.post("/attachment")
def preset_attachment(body: AttachRequest, user: CurrentUser, db: DbSession) -> AttachResult:
    """공격 프리셋의 청구서 PDF를 현재 사용자 첨부로 저장하고 id·파일명을 돌려준다 (S2 버튼용)."""
    preset = next((p for p in _all_presets() if p["id"] == body.preset_id), None)
    if preset is None or not preset["attachment"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "첨부가 있는 프리셋이 아닙니다")
    data = (DOCS_DIR / preset["attachment"]).read_bytes()
    attachment = save_attachment(db, user.id, preset["attachment"], data)
    return AttachResult(attachment_id=attachment.id, filename=attachment.filename)


@router.get("/attacker-log")
def attacker_log(_user: CurrentUser) -> list[dict[str, Any]]:
    """공격자 서버(127.0.0.1:9999)가 받은 요청 기록. 로그인한 사용자만 읽는다."""
    return read_log()
