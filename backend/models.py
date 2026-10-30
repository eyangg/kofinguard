"""테이블 구조 (spec.md 8.3). 금액은 원 단위 정수."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # 예: C-1001
    login_id: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    loan_info: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(String(255))


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_accounts_balance_nonneg"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    account_no: Mapped[str] = mapped_column(String(20), unique=True)
    balance: Mapped[int] = mapped_column(BigInteger)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_transactions_amount_pos"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 받는 계좌는 MJ뱅크 밖일 수 있어서 외래키 대신 계좌번호 문자열로 둔다.
    from_account: Mapped[str] = mapped_column(String(20), index=True)
    to_account: Mapped[str] = mapped_column(String(20), index=True)
    to_name: Mapped[str] = mapped_column(String(50))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PendingTransfer(Base):
    __tablename__ = "pending_transfers"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_pending_transfers_amount_pos"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    to_account: Mapped[str] = mapped_column(String(20))
    to_name: Mapped[str] = mapped_column(String(50))
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (CheckConstraint("mode IN ('off', 'on')", name="ck_chat_messages_mode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(3))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DefenseEvent(Base):
    __tablename__ = "defense_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id"), index=True)
    layer: Mapped[str] = mapped_column(String(8))  # D-01 ~ D-08
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (CheckConstraint("mode IN ('off', 'on')", name="ck_tool_calls_mode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id"), index=True)
    mode: Mapped[str] = mapped_column(String(3))
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    allowed: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))  # detector / attack
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    env: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # CPU/코랩, 모델 크기 등
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
