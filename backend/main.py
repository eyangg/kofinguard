"""KoFinGuard 백엔드 (FastAPI).

실행 (backend 폴더에서):
    .\\.venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import attachments
import auth
import db
from auth import CurrentUser, MeResponse
from bank.router import router as bank_router
from chat.router import router as chat_router
from demo import router as demo_router

# uvicorn 기본 로그 설정이 출력하는 로거를 써야 서버 터미널에 INFO 줄이 보인다.
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # DATABASE_URL이 없거나 연결할 수 없으면 SQLite로 넘어가지 않고 시작을 멈춘다.
    # 세션 서명 키(KFG_SESSION_SECRET)가 없어도 멈춘다.
    db.load_env()
    try:
        engine = db.get_engine()
        db.check_connection(engine)
        auth.get_session_secret()
    except (db.DatabaseConfigError, auth.SessionConfigError) as e:
        logger.error("%s", e)
        raise
    logger.info("DB 연결: %s", db.describe_url(str(engine.url)))
    yield


app = FastAPI(title="KoFinGuard", lifespan=lifespan)

# 배포 시 프론트(Cloudflare)는 백엔드와 다른 출처라 CORS 허용이 필요하다. 쿠키를 주고받으므로
# allow_credentials=True이며, 이 경우 와일드카드 출처는 쓸 수 없어 정확한 출처만 등록한다.
# 로컬 개발은 Vite 프록시(동일 출처)라 KFG_FRONTEND_ORIGIN을 비워 두면 CORS를 켜지 않는다.
_frontend_origins = [o.strip() for o in os.environ.get("KFG_FRONTEND_ORIGIN", "").split(",") if o.strip()]
if _frontend_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(bank_router)
app.include_router(attachments.router)
app.include_router(chat_router)
app.include_router(demo_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/me")
def me(user: CurrentUser) -> MeResponse:
    return MeResponse.of(user)
