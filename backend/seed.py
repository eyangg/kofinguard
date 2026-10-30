"""시드 데이터 (모두 가상). 여러 번 실행해도 이미 있는 고객은 건너뛴다.

실행 (backend 폴더, 테이블을 먼저 만든 뒤):
    .\\.venv\\Scripts\\python.exe seed.py
    .\\.venv\\Scripts\\python.exe seed.py --reset   # 잔액을 처음 값으로, 거래·송금 대기 기록 삭제 (관측 반복용)
"""

import sys

from sqlalchemy import delete, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import db
from models import Account, Customer, PendingTransfer, Transaction
from passwords import hash_password

# 시연 계정 비밀번호. 가상 계정이라 비밀값이 아니다.
DEMO_PASSWORD = "demo1234!"

CUSTOMERS = [
    {
        "id": "C-1001",
        "login_id": "minsu",
        "name": "김민수",
        "email": "minsu@example.com",
        "phone": "010-0000-1001",
        "loan_info": "신용대출 1,000만원, 연 5.2%, 2027-03 만기 (가상)",
        "account_no": "111-1001-0001",
        "balance": 3_000_000,
    },
    {
        "id": "C-1002",
        "login_id": "seoyeon",
        "name": "이서연",
        "email": "seoyeon@example.com",
        "phone": "010-0000-1002",
        "loan_info": "주택담보대출 2억원, 연 4.1%, 2045-08 만기 (가상)",
        "account_no": "222-1002-0001",
        "balance": 5_000_000,
    },
]


def seed(session: Session) -> int:
    """없는 고객과 계좌만 넣고, 새로 넣은 고객 수를 돌려준다."""
    added = 0
    for c in CUSTOMERS:
        if session.get(Customer, c["id"]) is not None:
            continue
        session.add(
            Customer(
                id=c["id"],
                login_id=c["login_id"],
                name=c["name"],
                email=c["email"],
                phone=c["phone"],
                loan_info=c["loan_info"],
                password_hash=hash_password(DEMO_PASSWORD),
            )
        )
        session.flush()  # 계좌의 외래키보다 고객이 먼저 들어가야 한다
        session.add(Account(customer_id=c["id"], account_no=c["account_no"], balance=c["balance"]))
        added += 1
    session.commit()
    return added


def reset(session: Session) -> None:
    """잔액을 처음 값으로 돌리고 거래·송금 대기 기록을 지운다. 고객·대화 기록은 그대로 둔다."""
    session.execute(delete(PendingTransfer))
    session.execute(delete(Transaction))
    for c in CUSTOMERS:
        session.execute(update(Account).where(Account.account_no == c["account_no"]).values(balance=c["balance"]))
    session.commit()


def main() -> int:
    try:
        engine = db.get_engine()
        db.check_connection(engine)
        with Session(engine) as session:
            added = seed(session)
            if "--reset" in sys.argv[1:]:
                reset(session)
                print("잔액 초기화, 거래·송금 대기 기록 삭제")
    except db.DatabaseConfigError as e:
        print(e, file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("시드 실패: 테이블이 없으면 먼저 Alembic으로 만드세요 (README 참고).", file=sys.stderr)
        return 1
    print(f"시드 완료: 새 고객 {added}명 ({db.describe_url(str(engine.url))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
