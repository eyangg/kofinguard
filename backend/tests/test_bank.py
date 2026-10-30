from datetime import datetime, timedelta, timezone

import pytest
from conftest import login
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from bank import service
from bank.service import BankError
from models import Account, PendingTransfer, Transaction

MINSU, SEOYEON = "C-1001", "C-1002"
MINSU_ACC, SEOYEON_ACC = "111-1001-0001", "222-1002-0001"
EXTERNAL_ACC = "333-0000-1111"  # MJ뱅크 밖 계좌 (S2 청구서의 MJ전자)
# 한국 시간 2026-10-30 오후 3시
NOW = datetime(2026, 10, 30, 6, 0, tzinfo=timezone.utc)


def balance(engine: Engine, account_no: str) -> int:
    with Session(engine) as s:
        return s.scalar(select(Account.balance).where(Account.account_no == account_no)) or 0


def tx_count(engine: Engine) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(Transaction)) or 0


# ---- 조회 ----


def test_account_and_profile(seeded: Engine) -> None:
    with Session(seeded) as s:
        assert service.get_account(s, MINSU).model_dump() == {"account_no": MINSU_ACC, "balance": 3_000_000}
        profile = service.get_customer_profile(s, SEOYEON)
        assert profile.name == "이서연" and profile.email == "seoyeon@example.com"
        assert "주택담보대출" in profile.loan_info
        with pytest.raises(BankError, match="찾을 수 없습니다"):
            service.get_customer_profile(s, "C-9999")


# ---- 송금 ----


def test_transfer_moves_money_and_records(seeded: Engine) -> None:
    with Session(seeded) as s:
        result = service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 50_000, now=NOW)
    assert result.balance_after == 2_950_000
    assert balance(seeded, MINSU_ACC) == 2_950_000
    assert balance(seeded, SEOYEON_ACC) == 5_050_000
    with Session(seeded) as s:
        mine = service.list_transactions(s, MINSU)
        theirs = service.list_transactions(s, SEOYEON)
    assert [(t.direction, t.amount) for t in mine] == [("out", 50_000)]
    assert [(t.direction, t.amount) for t in theirs] == [("in", 50_000)]


def test_external_transfer_only_debits(seeded: Engine) -> None:
    with Session(seeded) as s:
        service.transfer(s, MINSU, EXTERNAL_ACC, "MJ전자", 120_000, now=NOW)
    assert balance(seeded, MINSU_ACC) == 2_880_000
    assert balance(seeded, SEOYEON_ACC) == 5_000_000


@pytest.mark.parametrize("amount", [0, -1, 1.5, "100", True, None])
def test_invalid_amount_rejected(seeded: Engine, amount: object) -> None:
    with Session(seeded) as s, pytest.raises(BankError, match="정수"):
        service.transfer(s, MINSU, SEOYEON_ACC, "이서연", amount, now=NOW)  # type: ignore[arg-type]
    assert balance(seeded, MINSU_ACC) == 3_000_000
    assert tx_count(seeded) == 0


def test_insufficient_balance_rejected(seeded: Engine) -> None:
    with Session(seeded) as s:
        s.execute(update(Account).where(Account.account_no == MINSU_ACC).values(balance=10_000))
        s.commit()
        with pytest.raises(BankError, match="잔액이 부족"):
            service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 20_000, now=NOW)
    assert balance(seeded, MINSU_ACC) == 10_000
    assert tx_count(seeded) == 0


def test_daily_limit(seeded: Engine) -> None:
    with Session(seeded) as s:
        service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 600_000, now=NOW)
        with pytest.raises(BankError, match="한도"):
            service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 500_000, now=NOW)
        service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 400_000, now=NOW)  # 정확히 100만원은 허용
        with pytest.raises(BankError, match="한도"):
            service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 1, now=NOW)
    assert balance(seeded, MINSU_ACC) == 2_000_000


def test_single_transfer_over_limit_rejected(seeded: Engine) -> None:
    with Session(seeded) as s, pytest.raises(BankError, match="한도"):
        service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 2_000_000, now=NOW)
    assert balance(seeded, MINSU_ACC) == 3_000_000


def test_daily_limit_resets_at_kst_midnight(seeded: Engine) -> None:
    yesterday_kst_23h = datetime(2026, 10, 29, 14, 30, tzinfo=timezone.utc)  # 한국 시간 10/29 23:30
    with Session(seeded) as s:
        service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 900_000, now=yesterday_kst_23h)
        today_kst_0h30 = datetime(2026, 10, 29, 15, 30, tzinfo=timezone.utc)  # 한국 시간 10/30 00:30
        service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 900_000, now=today_kst_0h30)
    assert balance(seeded, MINSU_ACC) == 1_200_000


def test_failure_midway_rolls_back_everything(seeded: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_record(*_args: object, **_kwargs: object) -> Transaction:
        raise RuntimeError("기록 중 장애")

    monkeypatch.setattr(service, "_record", broken_record)
    with Session(seeded) as s, pytest.raises(RuntimeError):
        service.transfer(s, MINSU, SEOYEON_ACC, "이서연", 50_000, now=NOW)
    # 출금·입금이 먼저 일어났어도 기록이 실패하면 모두 취소된다.
    assert balance(seeded, MINSU_ACC) == 3_000_000
    assert balance(seeded, SEOYEON_ACC) == 5_000_000
    assert tx_count(seeded) == 0


# ---- 송금 대기와 확인 ----


def make_pending(engine: Engine, amount: int = 50_000, now: datetime = NOW) -> int:
    with Session(engine) as s:
        return service.create_pending_transfer(s, MINSU, SEOYEON_ACC, "이서연", amount, now=now).id


def test_pending_does_not_move_money(seeded: Engine) -> None:
    make_pending(seeded)
    assert balance(seeded, MINSU_ACC) == 3_000_000
    assert tx_count(seeded) == 0


def test_pending_creation_checks_limit(seeded: Engine) -> None:
    with Session(seeded) as s, pytest.raises(BankError, match="한도"):
        service.create_pending_transfer(s, MINSU, SEOYEON_ACC, "이서연", 2_000_000, now=NOW)


def test_confirm_executes_once(seeded: Engine) -> None:
    pid = make_pending(seeded)
    with Session(seeded) as s:
        result = service.confirm_pending_transfer(s, MINSU, pid, now=NOW + timedelta(minutes=1))
        assert result.balance_after == 2_950_000
        with pytest.raises(BankError, match="이미 처리"):
            service.confirm_pending_transfer(s, MINSU, pid, now=NOW + timedelta(minutes=2))
    assert balance(seeded, MINSU_ACC) == 2_950_000


def test_confirm_others_pending_rejected(seeded: Engine) -> None:
    pid = make_pending(seeded)
    with Session(seeded) as s, pytest.raises(BankError, match="찾을 수 없습니다"):
        service.confirm_pending_transfer(s, SEOYEON, pid, now=NOW)
    assert balance(seeded, MINSU_ACC) == 3_000_000


def test_confirm_after_5_minutes_rejected(seeded: Engine) -> None:
    pid = make_pending(seeded)
    with Session(seeded) as s:
        with pytest.raises(BankError, match="5분"):
            service.confirm_pending_transfer(s, MINSU, pid, now=NOW + timedelta(minutes=5, seconds=1))
        assert s.get(PendingTransfer, pid).status == "expired"  # type: ignore[union-attr]
    assert balance(seeded, MINSU_ACC) == 3_000_000


def test_confirm_rechecks_limit_at_execution(seeded: Engine) -> None:
    pid = make_pending(seeded, amount=600_000)
    with Session(seeded) as s:
        service.transfer(s, MINSU, EXTERNAL_ACC, "MJ전자", 500_000, now=NOW)
        with pytest.raises(BankError, match="한도"):
            service.confirm_pending_transfer(s, MINSU, pid, now=NOW + timedelta(minutes=1))
        assert s.get(PendingTransfer, pid).status == "pending"  # type: ignore[union-attr]
    assert balance(seeded, MINSU_ACC) == 2_500_000


# ---- HTTP API ----


def test_bank_api_requires_login(client: TestClient) -> None:
    assert client.get("/api/accounts/me").status_code == 401
    assert client.get("/api/transactions").status_code == 401
    assert client.post("/api/transfers/1/confirm").status_code == 401


def test_bank_api_shows_only_my_data(client: TestClient, seeded: Engine) -> None:
    with Session(seeded) as s:
        service.transfer(s, SEOYEON, EXTERNAL_ACC, "MJ전자", 10_000)
    login(client)
    assert client.get("/api/accounts/me").json() == {"account_no": MINSU_ACC, "balance": 3_000_000}
    assert client.get("/api/transactions").json() == []  # 이서연의 거래는 안 보인다


def test_confirm_api(client: TestClient, seeded: Engine) -> None:
    with Session(seeded) as s:
        pid = service.create_pending_transfer(s, MINSU, SEOYEON_ACC, "이서연", 50_000).id

    login(client, "seoyeon")
    res = client.post(f"/api/transfers/{pid}/confirm")
    assert res.status_code == 404  # 남의 대기 건

    login(client, "minsu")
    res = client.post(f"/api/transfers/{pid}/confirm")
    assert res.status_code == 200
    assert res.json()["balance_after"] == 2_950_000
    assert client.post(f"/api/transfers/{pid}/confirm").status_code == 409
    assert [t["direction"] for t in client.get("/api/transactions").json()] == ["out"]
