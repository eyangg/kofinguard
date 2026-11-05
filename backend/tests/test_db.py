import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import db
import seed
from main import app
from models import Account, Customer
from passwords import verify_password
from conftest import run_migrations

TABLES = {
    "customers",
    "accounts",
    "transactions",
    "pending_transfers",
    "attachments",
    "chat_messages",
    "defense_events",
    "tool_calls",
    "eval_runs",
}


def test_migration_creates_all_tables(engine: Engine) -> None:
    assert TABLES <= set(inspect(engine).get_table_names())


def test_migration_twice_is_ok(engine: Engine) -> None:
    run_migrations()  # 이미 적용된 변경은 다시 적용하지 않는다
    assert TABLES <= set(inspect(engine).get_table_names())


def test_seed_twice_does_not_duplicate(engine: Engine) -> None:
    with Session(engine) as s:
        assert seed.seed(s) == len(seed.CUSTOMERS)
    with Session(engine) as s:
        assert seed.seed(s) == 0
        assert len(s.scalars(select(Customer)).all()) == len(seed.CUSTOMERS)
        balances = {a.account_no: a.balance for a in s.scalars(select(Account))}
    assert balances == {c["account_no"]: c["balance"] for c in seed.CUSTOMERS}
    assert balances["111-1001-0001"] == 3_000_000  # 시연 기준 계정(김민수)
    assert balances["222-1002-0001"] == 5_000_000  # S1 대상(이서연)


def test_no_plaintext_password(engine: Engine) -> None:
    with Session(engine) as s:
        seed.seed(s)
        for c in s.scalars(select(Customer)):
            assert seed.DEMO_PASSWORD not in c.password_hash
            assert verify_password(seed.DEMO_PASSWORD, c.password_hash)
            assert not verify_password("wrong-password", c.password_hash)


def test_data_survives_new_engine(engine: Engine, db_url: str) -> None:
    """서버를 껐다 켠 것처럼 새 엔진으로 다시 열어도 데이터가 남는다."""
    with Session(engine) as s:
        seed.seed(s)
    engine.dispose()
    fresh = db.make_engine(db_url)
    with Session(fresh) as s:
        assert s.get(Customer, "C-1001") is not None
    fresh.dispose()


def test_missing_database_url_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(db.DatabaseConfigError, match="DATABASE_URL"):
        db.get_database_url()


def test_server_does_not_start_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db, "load_env", lambda: None)  # backend/.env를 읽지 않게 한다
    db.get_engine.cache_clear()
    with pytest.raises(db.DatabaseConfigError):
        with TestClient(app):
            pass
    db.get_engine.cache_clear()


def test_unreachable_db_stops_with_help(tmp_path) -> None:  # type: ignore[no-untyped-def]
    eng = db.make_engine(f"sqlite:///{(tmp_path / 'no_such_dir' / 'x.db').as_posix()}")
    with pytest.raises(db.DatabaseConfigError, match="연결할 수 없습니다"):
        db.check_connection(eng)
    eng.dispose()


def test_log_description_hides_password() -> None:
    desc = db.describe_url("postgresql://user:supersecret@db.example.com:5432/postgres")
    assert "supersecret" not in desc
    assert "db.example.com" in desc


def test_sqlite_relative_path_is_under_backend() -> None:
    resolved = db.resolve_url("sqlite:///./kofinguard.db")
    assert resolved.database == str(db.BACKEND_DIR / "kofinguard.db")
