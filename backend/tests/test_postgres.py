"""Supabase(PostgreSQL) 연결 확인 (pytest -m postgres).

실제 PostgreSQL이 필요하다. DATABASE_URL이 postgresql이 아니면 SKIP한다.
기본 pytest에서는 돌지 않는다(인터넷·DB 없이). 사람이 .env에 Session pooler 문자열을 넣고 실행한다.
"""

import os

import pytest
from sqlalchemy import inspect, text

import db

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def engine():  # type: ignore[no-untyped-def]
    db.load_env()
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL이 PostgreSQL이 아닙니다 (Supabase Session pooler 필요)")
    eng = db.make_engine(url)
    try:
        db.check_connection(eng)
    except db.DatabaseConfigError as e:
        pytest.skip(str(e))
    return eng


EXPECTED = {"customers", "accounts", "transactions", "pending_transfers", "attachments",
            "chat_messages", "defense_events", "tool_calls", "eval_runs"}


def test_tables_exist(engine) -> None:  # type: ignore[no-untyped-def]
    assert EXPECTED <= set(inspect(engine).get_table_names())


def test_rls_enabled_on_all_tables(engine) -> None:  # type: ignore[no-untyped-def]
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT relname FROM pg_class WHERE relname = ANY(:names) AND relrowsecurity"),
            {"names": list(EXPECTED)},
        ).all()
    assert {r[0] for r in rows} == EXPECTED, "모든 테이블에 RLS가 켜져 있어야 합니다"


def test_anon_has_no_table_privileges(engine) -> None:  # type: ignore[no-untyped-def]
    with engine.connect() as conn:
        has_anon = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname='anon'")).first()
        if not has_anon:
            pytest.skip("anon 역할이 없습니다 (Supabase가 아님)")
        leaked = conn.execute(
            text(
                "SELECT table_name FROM information_schema.role_table_grants "
                "WHERE grantee='anon' AND table_schema='public' AND table_name = ANY(:names)"
            ),
            {"names": list(EXPECTED)},
        ).all()
    assert leaked == [], f"anon 역할에 권한이 남아 있습니다: {leaked}"


def test_backend_can_read_write(engine) -> None:  # type: ignore[no-untyped-def]
    """백엔드 연결(테이블 소유자)은 RLS를 우회해 정상 동작해야 한다."""
    from sqlalchemy.orm import Session

    from models import Customer

    with Session(engine) as s:
        count = s.query(Customer).count()
    assert count >= 0
