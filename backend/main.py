"""KoFinGuard 백엔드 (FastAPI).

실행 (backend 폴더에서):
    .\\.venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import attachments
import auth
import db
from auth import CurrentUser, MeResponse
from bank.router import router as bank_router

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
app.include_router(auth.router)
app.include_router(bank_router)
app.include_router(attachments.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/me")
def me(user: CurrentUser) -> MeResponse:
    return MeResponse.of(user)
