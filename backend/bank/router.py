"""은행 HTTP API (spec 8.5). 모두 로그인한 본인 기준으로만 동작한다."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from auth import CurrentUser, DbSession
from bank import service
from bank.service import AccountInfo, BankError, TransactionInfo, TransferResult

router = APIRouter(prefix="/api", tags=["bank"])


def _http(e: BankError) -> HTTPException:
    return HTTPException(e.status, e.message)


@router.get("/accounts/me")
def my_account(user: CurrentUser, db: DbSession) -> AccountInfo:
    try:
        return service.get_account(db, user.id)
    except BankError as e:
        raise _http(e) from None


@router.get("/transactions")
def my_transactions(
    user: CurrentUser, db: DbSession, limit: Annotated[int, Query(ge=1, le=50)] = 5
) -> list[TransactionInfo]:
    try:
        return service.list_transactions(db, user.id, limit)
    except BankError as e:
        raise _http(e) from None


@router.post("/transfers/{pending_id}/confirm")
def confirm_transfer(pending_id: int, user: CurrentUser, db: DbSession) -> TransferResult:
    try:
        return service.confirm_pending_transfer(db, user.id, pending_id)
    except BankError as e:
        raise _http(e) from None
