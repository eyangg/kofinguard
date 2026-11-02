"""S1·S2를 OFF/ON으로 실행하고 실제 결과로 판정한다 (spec 5장).

판정은 챗봇 말이 아니라 tool_calls 기록(그리고 Phase 9부터는 공격자 서버 기록)으로 한다.
- OFF는 뚫려야(FAIL) 정상, ON은 막혀야(PASS) 정상.
- S2는 브라우저 없이도 판정되도록 답변에 실행 가능한 HTML이 남는지 본다. 화면 실행 확인은 Phase 9.

실행 (backend 폴더, Ollama 실행 중, 비용 발생):
    .\\.venv\\Scripts\\python.exe -m scenarios.runner          # 실제 OpenAI·모델로 S1·S2 OFF/ON → artifacts/scenarios.json
"""

import json
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import db
import seed
from attachments import load_attachment_text, save_attachment
from chat.llm_client import LLM, LLMConfigError, OpenAILLM
from chat.loop import ModeNotAllowedError
from chat.pipeline import DetectorLike, run_chat
from detector.router import DetectorConfigError, build_detector
from models import Customer
from scenarios.attacks import judge_s1, judge_s2, presets

HERE = Path(__file__).resolve().parent
OUT_FILE = HERE.parents[1] / "artifacts" / "scenarios.json"


def _attachment_text(session: Session, user: Customer, filename: str | None) -> str | None:
    if not filename:
        return None
    attachment = save_attachment(session, user.id, filename, (HERE / "docs" / filename).read_bytes())
    return load_attachment_text(session, user.id, attachment.id)[1]


def _judge(preset_id: str, result) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    calls = [asdict(tc) for tc in result.tool_calls]
    verdict = judge_s1(calls) if preset_id == "S1" else judge_s2(result.reply, calls)
    return {
        "reply": result.reply,
        "tool_calls": [{"tool": c["tool"], "args": c["args"], "allowed": c["allowed"], "reason": c["reason"]} for c in calls],
        **verdict,
    }


def run_one(session: Session, llm: LLM, user: Customer, detector: DetectorLike, preset: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"preset": preset["id"], "label": preset["label"]}
    for mode in ("off", "on"):
        seed.reset(session)  # 깨끗한 상태(잔액 초기화, 기록 삭제)에서 각 모드 실행
        text = _attachment_text(session, user, preset["attachment"])
        result = run_chat(
            session, llm, user, mode, f"scn-{uuid.uuid4().hex[:8]}", preset["message"],
            detector=detector, attachment_text=text,
        )
        row[mode] = _judge(preset["id"], result)
    # OFF는 뚫리고(FAIL) ON은 막혀야(PASS) 기대대로.
    row["as_expected"] = row["off"]["breached"] and not row["on"]["breached"]
    return row


def main() -> int:
    db.load_env()
    try:
        require_env_llm = OpenAILLM()
        detector = build_detector()
    except (LLMConfigError, DetectorConfigError) as e:
        print(e, file=sys.stderr)
        return 1

    with Session(db.get_engine()) as session:
        user = session.scalar(select(Customer).where(Customer.login_id == "minsu"))
        if user is None:
            print("시드 데이터(minsu)가 없습니다. seed.py를 먼저 실행하세요.", file=sys.stderr)
            return 1
        rows = []
        for preset in presets():
            print(f"=== {preset['id']} {preset['label']} ===", flush=True)
            try:
                row = run_one(session, require_env_llm, user, detector, preset)
            except ModeNotAllowedError as e:
                print(e, file=sys.stderr)
                return 1
            print(f"  OFF 뚫림={row['off']['breached']} ({row['off']['evidence']})")
            print(f"  ON  뚫림={row['on']['breached']} ({row['on']['evidence']})")
            print(f"  기대대로(OFF FAIL→ON PASS)={row['as_expected']}\n")
            rows.append(row)
        seed.reset(session)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": datetime.now(timezone.utc).isoformat(), "model": require_env_llm.model, "guard": detector.guard.model, "scenarios": rows}
    OUT_FILE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"기록: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
