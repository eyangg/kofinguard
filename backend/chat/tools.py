"""챗봇 툴 목록 (OFF/ON 공통).

송금 [확인] 기능은 넣지 않는다. 사람이 버튼(POST /api/transfers/{id}/confirm)으로만 실행한다 (spec 3.4).
"""

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_my_balance",
            "description": "로그인한 고객의 계좌번호와 잔액(원)을 조회한다.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transactions",
            "description": "로그인한 고객 계좌의 최근 거래내역을 최신순으로 조회한다.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "가져올 개수 (1~50, 기본 5)"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_profile",
            "description": "고객번호로 고객 정보(이름, 이메일, 연락처, 대출 정보)를 조회한다.",
            "parameters": {
                "type": "object",
                "properties": {"customer_id": {"type": "string", "description": "고객번호 (예: C-1001)"}},
                "required": ["customer_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_transfer",
            "description": "로그인한 고객 계좌에서 송금한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_account": {"type": "string", "description": "받는 계좌번호"},
                    "to_name": {"type": "string", "description": "받는 사람 이름"},
                    "amount": {"type": "integer", "description": "금액 (원, 정수)"},
                },
                "required": ["to_account", "to_name", "amount"],
                "additionalProperties": False,
            },
        },
    },
]

TOOL_NAMES = frozenset(t["function"]["name"] for t in TOOLS)
