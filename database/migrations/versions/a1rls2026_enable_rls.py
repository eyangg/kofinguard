"""enable RLS and revoke anon/authenticated (PostgreSQL only)

Supabase에서만 동작한다. 모든 테이블에 RLS를 켜고(정책 없음 = 외부 역할 거부),
anon·authenticated 역할의 권한을 회수해 브라우저가 PostgREST로 직접 접근하지 못하게 한다.
FORCE는 쓰지 않는다 — 테이블 소유자(백엔드 연결)는 RLS를 우회해야 서버가 정상 동작한다.
SQLite(테스트)에서는 아무것도 하지 않는다.

Revision ID: a1rls2026
Revises: 163be6f4f5e0
Create Date: 2026-11-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1rls2026"
down_revision: Union[str, Sequence[str], None] = "163be6f4f5e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "customers",
    "accounts",
    "transactions",
    "pending_transfers",
    "attachments",
    "chat_messages",
    "defense_events",
    "tool_calls",
    "eval_runs",
]

# Supabase에 없을 수도 있는 역할은 존재할 때만 회수한다.
_REVOKE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
  END IF;
END $$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite 등에서는 RLS를 적용하지 않는다
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(_REVOKE)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
