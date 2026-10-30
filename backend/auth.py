"""로그인·로그아웃·현재 사용자 (spec 2장).

쿠키에는 무작위 세션 ID와 서명(KFG_SESSION_SECRET)만 담고, 누가 로그인했는지는 서버 메모리에 둔다.
로그아웃하면 서버에서 지우므로 이전 쿠키는 더 이상 쓸 수 없다. 서버를 다시 켜면 모두 로그아웃된다.
"""

import hashlib
import hmac
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db
from models import Customer
from passwords import hash_password, verify_password

COOKIE_NAME = "kfg_session"
SESSION_TTL = timedelta(hours=8)
LOGIN_FAILED = "아이디 또는 비밀번호가 맞지 않습니다"
NOT_LOGGED_IN = "로그인이 필요합니다"

SECRET_HELP = (
    "KFG_SESSION_SECRET이 없거나 너무 짧습니다 (32자 이상).\n"
    "만드는 법 (backend 폴더):\n"
    '  .\\.venv\\Scripts\\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"\n'
    "나온 값을 backend/.env에 KFG_SESSION_SECRET=값 으로 넣으세요."
)


class SessionConfigError(RuntimeError):
    pass


def get_session_secret() -> bytes:
    secret = os.environ.get("KFG_SESSION_SECRET", "").strip()
    if len(secret) < 32:
        raise SessionConfigError(SECRET_HELP)
    return secret.encode()


@dataclass
class _Entry:
    customer_id: str
    expires_at: datetime


class SessionStore:
    def __init__(self) -> None:
        self._items: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def create(self, customer_id: str) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._items[sid] = _Entry(customer_id, datetime.now(timezone.utc) + SESSION_TTL)
        return sid

    def get(self, sid: str) -> str | None:
        with self._lock:
            entry = self._items.get(sid)
            if entry is None:
                return None
            if entry.expires_at <= datetime.now(timezone.utc):
                del self._items[sid]
                return None
            return entry.customer_id

    def delete(self, sid: str) -> None:
        with self._lock:
            self._items.pop(sid, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


sessions = SessionStore()


def _sign(sid: str) -> str:
    return hmac.new(get_session_secret(), sid.encode(), hashlib.sha256).hexdigest()


def make_cookie_value(sid: str) -> str:
    return f"{sid}.{_sign(sid)}"


def read_cookie_value(value: str | None) -> str | None:
    """서명이 맞으면 세션 ID를, 아니면 None을 돌려준다."""
    if not value:
        return None
    sid, _, signature = value.rpartition(".")
    if not sid or not hmac.compare_digest(signature, _sign(sid)):
        return None
    return sid


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    # 없는 아이디도 비밀번호 검사 시간을 똑같이 써서, 응답 시간으로 아이디 존재 여부를 알 수 없게 한다.
    return hash_password(secrets.token_hex(16))


SessionCookie = Annotated[str | None, Cookie(alias=COOKIE_NAME)]
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, kfg_session: SessionCookie = None) -> Customer:
    sid = read_cookie_value(kfg_session)
    customer_id = sessions.get(sid) if sid else None
    customer = db.get(Customer, customer_id) if customer_id else None
    if customer is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_LOGGED_IN)
    return customer


CurrentUser = Annotated[Customer, Depends(get_current_user)]


class LoginRequest(BaseModel):
    login_id: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class MeResponse(BaseModel):
    id: str
    login_id: str
    name: str
    email: str
    phone: str

    @classmethod
    def of(cls, c: Customer) -> "MeResponse":
        return cls(id=c.id, login_id=c.login_id, name=c.name, email=c.email, phone=c.phone)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, response: Response, db: DbSession, kfg_session: SessionCookie = None) -> MeResponse:
    customer = db.scalar(select(Customer).where(Customer.login_id == body.login_id))
    stored = customer.password_hash if customer else _dummy_hash()
    if not verify_password(body.password, stored) or customer is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)

    # 같은 브라우저의 이전 세션은 지우고 새 세션 ID를 준다.
    old_sid = read_cookie_value(kfg_session)
    if old_sid:
        sessions.delete(old_sid)
    sid = sessions.create(customer.id)
    response.set_cookie(
        COOKIE_NAME,
        make_cookie_value(sid),
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
    )
    return MeResponse.of(customer)


@router.post("/logout")
def logout(response: Response, kfg_session: SessionCookie = None) -> dict[str, str]:
    sid = read_cookie_value(kfg_session)
    if sid:
        sessions.delete(sid)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")
    return {"status": "ok"}
