"""DB 연결.

DATABASE_URL만 사용한다. 없거나 연결할 수 없으면 SQLite로 자동 전환하지 않고 멈춘다.
연결 문자열과 비밀번호는 오류 메시지·로그에 출력하지 않는다.
"""

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIR / ".env"

SETUP_HELP = (
    "확인할 것:\n"
    "  1. backend/.env 파일에 DATABASE_URL 줄이 있는지\n"
    "  2. 로컬 개발(Phase 2~7): DATABASE_URL=sqlite:///./kofinguard.db\n"
    "  3. 시연(Phase 8): Supabase Session pooler 연결 문자열 ([YOUR-PASSWORD]를 실제 비밀번호로 바꿨는지)\n"
    "SQLite로 자동 전환하지 않습니다."
)


class DatabaseConfigError(RuntimeError):
    pass


def load_env() -> None:
    """backend/.env를 읽는다. 이미 설정된 환경변수는 덮어쓰지 않는다."""
    load_dotenv(ENV_FILE, override=False)


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseConfigError("DATABASE_URL이 설정되지 않았습니다.\n" + SETUP_HELP)
    return url


def resolve_url(url: str) -> URL:
    """SQLite 상대 경로는 실행 위치와 상관없이 backend 폴더 기준으로 맞춘다."""
    try:
        parsed = make_url(url)
    except ArgumentError:
        raise DatabaseConfigError("DATABASE_URL 형식이 올바르지 않습니다.\n" + SETUP_HELP) from None
    if parsed.get_backend_name() == "sqlite":
        database = parsed.database
        if database and database != ":memory:" and not Path(database).is_absolute():
            parsed = parsed.set(database=str((BACKEND_DIR / database).resolve()))
    return parsed


def describe_url(url: str | URL) -> str:
    """로그용. 비밀번호를 가린 DB 종류와 위치만 보여 준다."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        return f"sqlite ({Path(parsed.database or '').name})"
    return f"{parsed.get_backend_name()} ({parsed.host})"


def make_engine(url: str) -> Engine:
    engine = create_engine(resolve_url(url), pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def check_connection(engine: Engine) -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise DatabaseConfigError(
            f"DB에 연결할 수 없습니다: {describe_url(str(engine.url))}\n" + SETUP_HELP
        ) from None


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    load_env()
    return make_engine(get_database_url())


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI 의존성: 요청마다 DB 세션을 열고 닫는다."""
    with get_session_factory()() as session:
        yield session
