"""추천 답장 필터 테스트. LLM 없이 돈다."""

from chat.router import _parse_suggestions


def test_suggestions_drop_name_and_customer_id() -> None:
    # 3인칭 이름·고객번호 문장은 Guard가 개인정보 요청(S7)으로 오탐하므로 버린다
    raw = '{"suggestions": ["김민수 고객 대출 상환일 알려줘", "C-1002 고객 잔액 알려줘", "내 대출 상환일 알려줘"]}'
    assert _parse_suggestions(raw, "김민수") == ["내 대출 상환일 알려줘"]


def test_suggestions_keep_normal_requests() -> None:
    raw = '{"suggestions": ["내 잔액 알려줘", "이체 한도 얼마야", "최근 거래내역 보여줘"]}'
    assert _parse_suggestions(raw, "김민수") == ["내 잔액 알려줘", "이체 한도 얼마야", "최근 거래내역 보여줘"]
