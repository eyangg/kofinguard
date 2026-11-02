"""방어 ON 실행기 (spec 4.2 D-05, D-06).

챗봇이 무엇이라고 말하든(예: "감사팀 승인 받았어요") 서버 판단은 바뀌지 않는다.
- get_customer_profile: 챗봇이 넘긴 customer_id를 무시하고 로그인한 본인 번호로만 조회한다 (D-05).
- create_transfer: 바로 송금하지 않고 송금 대기만 만든다. 한도·잔액은 서버가 검사한다 (D-06).
- 첨부 문서에서 뽑혀 온 값(수취인 이름 등)은 허용 문자만 통과시킨다 (D-07, document_guard).
"""

from typing import Any

from sqlalchemy.orm import Session

from bank import service
from bank.service import BankError
from chat.executor_off import ToolResult
from chat.document_guard import check_transfer_name
from models import Customer


def execute_on(session: Session, user: Customer, name: str, args: dict[str, Any]) -> ToolResult:
    try:
        if name == "get_my_balance":
            return ToolResult(service.get_account(session, user.id).model_dump(), True)
        if name == "get_transactions":
            limit = args.get("limit", 5)
            rows = service.list_transactions(session, user.id, limit if isinstance(limit, int) else 5)
            return ToolResult({"transactions": [r.model_dump(mode="json") for r in rows]}, True)
        if name == "get_customer_profile":
            # 챗봇이 다른 번호를 요청해도 본인 번호로 바꿔서 조회한다.
            requested = args.get("customer_id")
            if requested and str(requested) != user.id:
                return ToolResult(
                    service.get_customer_profile(session, user.id).model_dump(),
                    False,
                    f"다른 고객번호({requested}) 요청 거부, 본인({user.id})으로 조회",
                )
            return ToolResult(service.get_customer_profile(session, user.id).model_dump(), True)
        if name == "create_transfer":
            to_name = args.get("to_name")
            bad = check_transfer_name(to_name)
            if bad is not None:
                return ToolResult({"error": bad}, False, bad)
            pending = service.create_pending_transfer(
                session, user.id, args.get("to_account"), to_name, args.get("amount")  # type: ignore[arg-type]
            )
            # 송금은 대기만. 실행은 사람이 [확인] 버튼을 눌러야 한다.
            return ToolResult(
                {"status": "송금 대기 생성됨 (사람 확인 필요)", **pending.model_dump(mode="json")},
                True,
                "대기만 생성",
            )
    except BankError as e:
        return ToolResult({"error": e.message}, False, e.message)
    return ToolResult({"error": f"알 수 없는 기능입니다: {name}"}, False, "unknown_tool")
