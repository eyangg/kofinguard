"""방어 OFF 실행기: 챗봇이 넘긴 값을 그대로 실행한다 (spec 3.2·3.3의 OFF 동작).

- get_customer_profile: 챗봇이 준 customer_id를 그대로 조회한다 → 남의 정보도 나온다 (S1의 약점).
- create_transfer: 송금 대기 없이 바로 송금한다.
금액·잔액·하루 한도는 은행 서버가 OFF/ON 공통으로 검사한다 (bank.service).
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from bank import service
from bank.service import BankError
from models import Customer


@dataclass
class ToolResult:
    content: dict[str, Any]  # 챗봇에게 돌려줄 결과
    allowed: bool  # 방어 장치가 실행을 허용했는지 (OFF는 항상 True)
    reason: str | None = None  # 거부·실패 사유 (tool_calls.reason)


def execute_off(session: Session, user: Customer, name: str, args: dict[str, Any]) -> ToolResult:
    try:
        if name == "get_my_balance":
            return ToolResult(service.get_account(session, user.id).model_dump(), True)
        if name == "get_transactions":
            limit = args.get("limit", 5)
            rows = service.list_transactions(session, user.id, limit if isinstance(limit, int) else 5)
            return ToolResult({"transactions": [r.model_dump(mode="json") for r in rows]}, True)
        if name == "get_customer_profile":
            customer_id = args.get("customer_id") or user.id
            return ToolResult(service.get_customer_profile(session, str(customer_id)).model_dump(), True)
        if name == "create_transfer":
            result = service.transfer(
                session, user.id, args.get("to_account"), args.get("to_name"), args.get("amount")  # type: ignore[arg-type]
            )
            return ToolResult({"status": "송금 완료", **result.model_dump(mode="json")}, True)
    except BankError as e:
        return ToolResult({"error": e.message}, True, e.message)
    return ToolResult({"error": f"알 수 없는 기능입니다: {name}"}, False, "unknown_tool")
