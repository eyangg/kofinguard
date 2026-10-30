"""가상 은행 기능 (spec 3.1~3.4의 서버 부분). 금액은 원 단위 정수.

OFF/ON 차이(남의 고객번호를 그대로 쓸지, 바로 송금할지 대기로 만들지)는 챗봇 실행기(Phase 5·7)가 정한다.
여기 함수들은 넘겨받은 고객번호로만 동작하고, 금액·잔액·하루 한도는 OFF/ON 공통으로 항상 검사한다.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models import Account, Customer, PendingTransfer, Transaction, utcnow

DAILY_LIMIT = 1_000_000
PENDING_TTL = timedelta(minutes=5)
KST = timezone(timedelta(hours=9), "KST")


class BankError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class AccountInfo(BaseModel):
    account_no: str
    balance: int


class TransactionInfo(BaseModel):
    id: int
    direction: Literal["in", "out"]
    from_account: str
    to_account: str
    to_name: str
    amount: int
    created_at: datetime


class CustomerProfile(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    loan_info: str


class TransferResult(BaseModel):
    transaction: TransactionInfo
    balance_after: int


class PendingInfo(BaseModel):
    id: int
    to_account: str
    to_name: str
    amount: int
    status: str
    expires_at: datetime


def _as_utc(dt: datetime) -> datetime:
    # SQLite는 시간대 정보를 저장하지 않아서 읽어 오면 시간대 없는 UTC 값이 된다.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _account_of(session: Session, customer_id: str, lock: bool = False) -> Account:
    stmt = select(Account).where(Account.customer_id == customer_id)
    if lock:
        stmt = stmt.with_for_update()
    account = session.scalar(stmt)
    if account is None:
        raise BankError("not_found", "계좌를 찾을 수 없습니다", 404)
    return account


def _tx_info(tx: Transaction, my_account_no: str) -> TransactionInfo:
    return TransactionInfo(
        id=tx.id,
        direction="out" if tx.from_account == my_account_no else "in",
        from_account=tx.from_account,
        to_account=tx.to_account,
        to_name=tx.to_name,
        amount=tx.amount,
        created_at=_as_utc(tx.created_at),
    )


def _pending_info(p: PendingTransfer) -> PendingInfo:
    return PendingInfo(
        id=p.id,
        to_account=p.to_account,
        to_name=p.to_name,
        amount=p.amount,
        status=p.status,
        expires_at=_as_utc(p.expires_at),
    )


# ---- 조회 (F-01, F-02, F-05) ----


def get_account(session: Session, customer_id: str) -> AccountInfo:
    account = _account_of(session, customer_id)
    return AccountInfo(account_no=account.account_no, balance=account.balance)


def list_transactions(session: Session, customer_id: str, limit: int = 5) -> list[TransactionInfo]:
    account = _account_of(session, customer_id)
    rows = session.scalars(
        select(Transaction)
        .where(or_(Transaction.from_account == account.account_no, Transaction.to_account == account.account_no))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(max(1, min(limit, 50)))
    )
    return [_tx_info(tx, account.account_no) for tx in rows]


def get_customer_profile(session: Session, customer_id: str) -> CustomerProfile:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise BankError("not_found", "찾을 수 없습니다", 404)
    return CustomerProfile(
        id=customer.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        loan_info=customer.loan_info,
    )


# ---- 송금 검사 (F-03, F-06) ----


def _validate(amount: object, to_account: object, to_name: object) -> int:
    # 챗봇이 넘긴 값이 그대로 들어올 수 있어서 타입부터 확인한다 (1.5, "100", True 등 거절).
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise BankError("invalid_amount", "금액은 1원 이상의 정수여야 합니다")
    if not isinstance(to_account, str) or not 1 <= len(to_account.strip()) <= 20:
        raise BankError("invalid_target", "받는 계좌번호가 올바르지 않습니다")
    if not isinstance(to_name, str) or not 1 <= len(to_name.strip()) <= 50:
        raise BankError("invalid_target", "받는 사람 이름이 올바르지 않습니다")
    return amount


def sent_today(session: Session, account_no: str, now: datetime) -> int:
    """한국 시간 오늘 0시부터 이 계좌에서 실제로 나간 금액 합계."""
    kst_midnight = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    total = session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.from_account == account_no,
            Transaction.created_at >= kst_midnight.astimezone(timezone.utc),
        )
    )
    return int(total or 0)


def _check_can_send(session: Session, account: Account, amount: int, now: datetime) -> None:
    if account.balance < amount:
        raise BankError("insufficient_balance", "잔액이 부족합니다")
    used = sent_today(session, account.account_no, now)
    if used + amount > DAILY_LIMIT:
        raise BankError(
            "daily_limit",
            f"하루 이체 한도({DAILY_LIMIT:,}원)를 넘습니다. 오늘 보낸 금액: {used:,}원",
        )


# ---- 송금 실행: 출금·입금·기록을 한 트랜잭션으로 ----


def _debit(account: Account, amount: int) -> None:
    account.balance -= amount


def _credit(session: Session, to_account: str, amount: int) -> None:
    # MJ뱅크 계좌면 입금하고, 외부 계좌면 출금만 한다.
    target = session.scalar(select(Account).where(Account.account_no == to_account).with_for_update())
    if target is not None:
        target.balance += amount


def _record(session: Session, from_account: str, to_account: str, to_name: str, amount: int, now: datetime) -> Transaction:
    tx = Transaction(
        from_account=from_account, to_account=to_account, to_name=to_name, amount=amount, created_at=now
    )
    session.add(tx)
    session.flush()
    return tx


def _execute(session: Session, account: Account, to_account: str, to_name: str, amount: int, now: datetime) -> Transaction:
    _check_can_send(session, account, amount, now)
    _debit(account, amount)
    _credit(session, to_account, amount)
    return _record(session, account.account_no, to_account, to_name, amount, now)


def transfer(
    session: Session,
    customer_id: str,
    to_account: str,
    to_name: str,
    amount: int,
    now: datetime | None = None,
) -> TransferResult:
    """바로 송금한다 (OFF 실행기용). 중간에 실패하면 전부 취소한다."""
    now = now or utcnow()
    amount = _validate(amount, to_account, to_name)
    try:
        account = _account_of(session, customer_id, lock=True)
        tx = _execute(session, account, to_account.strip(), to_name.strip(), amount, now)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return TransferResult(transaction=_tx_info(tx, account.account_no), balance_after=account.balance)


# ---- 송금 대기와 확인 (F-04) ----


def create_pending_transfer(
    session: Session,
    customer_id: str,
    to_account: str,
    to_name: str,
    amount: int,
    now: datetime | None = None,
) -> PendingInfo:
    """송금 대기만 만든다 (ON 실행기용). 잔액은 바뀌지 않는다."""
    now = now or utcnow()
    amount = _validate(amount, to_account, to_name)
    account = _account_of(session, customer_id)
    _check_can_send(session, account, amount, now)
    pending = PendingTransfer(
        customer_id=customer_id,
        to_account=to_account.strip(),
        to_name=to_name.strip(),
        amount=amount,
        status="pending",
        expires_at=now + PENDING_TTL,
    )
    session.add(pending)
    session.commit()
    return _pending_info(pending)


def confirm_pending_transfer(
    session: Session, customer_id: str, pending_id: int, now: datetime | None = None
) -> TransferResult:
    """사람이 [확인] 버튼을 눌렀을 때만 부른다. 챗봇 툴 목록에는 넣지 않는다."""
    now = now or utcnow()
    try:
        pending = session.scalar(
            select(PendingTransfer).where(PendingTransfer.id == pending_id).with_for_update()
        )
        # 남의 대기 건은 있는지조차 알려 주지 않는다.
        if pending is None or pending.customer_id != customer_id:
            raise BankError("not_found", "송금 대기 건을 찾을 수 없습니다", 404)
        if pending.status != "pending":
            raise BankError("already_processed", "이미 처리된 송금 대기 건입니다", 409)
        if _as_utc(pending.expires_at) <= now:
            pending.status = "expired"
            session.commit()
            raise BankError("expired", "송금 대기 시간(5분)이 지났습니다", 409)

        account = _account_of(session, customer_id, lock=True)
        tx = _execute(session, account, pending.to_account, pending.to_name, pending.amount, now)
        pending.status = "done"
        session.commit()
    except BankError as e:
        if e.code != "expired":
            session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    return TransferResult(transaction=_tx_info(tx, account.account_no), balance_after=account.balance)
