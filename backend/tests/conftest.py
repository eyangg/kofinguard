from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import auth
import db
import seed
from main import app

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "database" / "alembic.ini"
TEST_SECRET = "test-secret-" + "x" * 32


def run_migrations() -> None:
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """테스트마다 임시 SQLite 파일을 쓴다. 실제 backend/.env의 DB는 건드리지 않는다."""
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    db.get_engine.cache_clear()
    return url


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    run_migrations()
    eng = db.make_engine(db_url)
    yield eng
    eng.dispose()
    db.get_engine.cache_clear()


@pytest.fixture
def seeded(engine: Engine) -> Engine:
    with Session(engine) as s:
        seed.seed(s)
    return engine


@pytest.fixture
def client(seeded: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("KFG_SESSION_SECRET", TEST_SECRET)
    auth.sessions.clear()
    with TestClient(app) as c:
        yield c
    auth.sessions.clear()


def login(c: TestClient, login_id: str = "minsu", password: str = seed.DEMO_PASSWORD) -> httpx.Response:
    return c.post("/api/auth/login", json={"login_id": login_id, "password": password})
