"""OFF/ON 챗봇 흐름을 한곳에서 만든다 (spec 4장 전체).

- OFF: 방어 없음(NullDefense) + executor_off. 답변은 그대로 둔다(화면이 HTML로 그려 S2 재현).
- ON:  OnDefense(입력 검사 D-01~D-04 + 문서 격리 D-07 + 답변 안전 처리 D-08) + executor_on(D-05, D-06).

판단 근거(trace)는 run_turn이 defense_events에 남긴다. 공격 성공 판정은 tool_calls·공격자 기록으로 한다.
"""

import os
from typing import Protocol

from sqlalchemy.orm import Session

from chat.document_guard import wrap_untrusted
from chat.executor_off import execute_off
from chat.executor_on import execute_on
from chat.llm_client import LLM, Message
from chat.loop import (
    NULL_DEFENSE,
    InputDecision,
    ModeNotAllowedError,
    TraceEvent,
    TurnResult,
    require_off_allowed,
    run_turn,
)
from chat.output_filter import PROMPT_LEAK_REFUSAL, detect_prompt_leak, filter_reply
from detector.router import MESSAGES
from models import Customer

# 입력 검사 결과(action) → 챗봇 호출 여부와 안내 문구
_INPUT_BLOCKING = {"block", "reask", "unavailable"}


class DetectorLike(Protocol):
    def check(self, text: str): ...  # -> detector.router.Verdict


def _verdict_events(source: str, original: str, verdict) -> list[TraceEvent]:  # type: ignore[no-untyped-def]
    v = verdict.as_dict()
    # D-01은 실제로 정리된 게 있을 때만 의미가 있다(changed). 변형이 없으면 화면에서 생략한다.
    changed = v["normalized"] != original
    return [
        TraceEvent("D-01", "정리", {"source": source, "changed": changed, "normalized": v["normalized"][:120]}),
        TraceEvent("D-02", "점수", {"mean_ppl": v["mean_ppl"], "var_ppl": v["var_ppl"], "jamo": v["jamo_flag"]}),
        TraceEvent(
            "D-03",
            "판정",
            {"guard_safe": v["guard_safe"], "categories": v["guard_categories"], "error": v["error"]},
        ),
        TraceEvent("D-04", verdict.action, {"source": source, "timings": v["timings"]}),
    ]


class OnDefense:
    """방어 ON. 사용자 메시지와 첨부 문서를 모두 탐지 파이프라인에 넣는다."""

    def __init__(self, detector: DetectorLike) -> None:
        self.detector = detector

    def check_input(self, message: str, attachment_text: str | None) -> InputDecision:
        events: list[TraceEvent] = []
        for source, text in [("message", message), ("document", attachment_text)]:
            if not text:
                continue
            verdict = self.detector.check(text)
            events.extend(_verdict_events(source, text, verdict))
            if verdict.action in _INPUT_BLOCKING:
                return InputDecision(proceed=False, blocked_reply=MESSAGES[verdict.action], events=events)
        return InputDecision(proceed=True, events=events)

    def wrap_attachment(self, text: str) -> str:
        return wrap_untrusted(text)

    def filter_output(self, reply: str) -> tuple[str, list[TraceEvent]]:
        # D-09: 답변에 시스템 프롬프트(내부 지침)가 새면 통째로 막는다 (S3 방어).
        if detect_prompt_leak(reply):
            return PROMPT_LEAK_REFUSAL, [TraceEvent("D-09", "차단", {"reason": "시스템 프롬프트 유출"})]
        # D-08: 답변 안전 처리 (HTML 인코딩·링크/이미지 제거·계좌 마스킹).
        result = filter_reply(reply)
        events = [TraceEvent("D-08", "답변 안전 처리", {"changes": result.changes})] if result.changes else []
        return result.text, events


def run_chat(
    session: Session,
    llm: LLM,
    user: Customer,
    mode: str,
    session_id: str,
    message: str,
    detector: DetectorLike | None = None,
    attachment_text: str | None = None,
    history: list[Message] | None = None,
) -> TurnResult:
    if mode == "off":
        require_off_allowed()
        return run_turn(
            session, llm, user, "off", session_id, history or [], message, execute_off,
            attachment_text=attachment_text, defense=NULL_DEFENSE,
        )
    if mode == "on":
        if detector is None:
            raise ValueError("방어 ON에는 detector가 필요합니다")
        return run_turn(
            session, llm, user, "on", session_id, history or [], message, execute_on,
            attachment_text=attachment_text, defense=OnDefense(detector),
        )
    raise ValueError(f"알 수 없는 모드: {mode}")
