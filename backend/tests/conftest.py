from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

import db

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "database" / "alembic.ini"


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
