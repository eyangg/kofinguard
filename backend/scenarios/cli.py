"""명령줄 대화 도구 (Phase 5: 방어 OFF 관측용). 실제 OpenAI API를 쓴다 (비용 발생).

실행 (backend 폴더, KFG_ENV=local 필요):
    .\\.venv\\Scripts\\python.exe -m scenarios.cli                        # 직접 대화 (김민수)
    .\\.venv\\Scripts\\python.exe -m scenarios.cli --attach 파일.pdf      # 첫 메시지에 문서 첨부
    .\\.venv\\Scripts\\python.exe -m scenarios.cli --preset S1            # 공격 하나 실행 + 기록
    .\\.venv\\Scripts\\python.exe -m scenarios.cli --preset all           # S1·S2 모두 실행 + 기록

공격 실행 결과는 artifacts/observe_off.json에 쌓인다. 판정은 챗봇 말이 아니라 툴 호출 결과로 한다.
"""

import argparse
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
from attachments import load_attachment_text, save_attachment
from bank import service
from chat.executor_off import execute_off
from chat.llm_client import LLM, LLMConfigError, Message, OpenAILLM
from chat.loop import ModeNotAllowedError, TurnResult, require_off_allowed, run_turn
from models import Customer
from scenarios.attacks import judge_s1, judge_s2

HERE = Path(__file__).resolve().parent
OBSERVE_FILE = HERE.parents[1] / "artifacts" / "observe_off.json"


def load_presets() -> list[dict[str, Any]]:
    return json.loads((HERE / "presets.json").read_text(encoding="utf-8"))


def attach(session: Session, user: Customer, path: Path) -> str:
    attachment = save_attachment(session, user.id, path.name, path.read_bytes())
    return load_attachment_text(session, user.id, attachment.id)[1]


def print_turn(result: TurnResult) -> None:
    for tc in result.tool_calls:
        note = f" → {tc.reason}" if tc.reason else ""
        print(f"  [툴] {tc.tool}({json.dumps(tc.args, ensure_ascii=False)}){note}")
    print(f"챗봇> {result.reply}\n")


def run_preset(session: Session, llm: LLM, user: Customer, preset: dict[str, Any]) -> dict[str, Any]:
    attachment_text = attach(session, user, HERE / "docs" / preset["attachment"]) if preset["attachment"] else None
    before = service.get_account(session, user.id).balance
    result = run_turn(
        session, llm, user, "off", f"cli-{uuid.uuid4().hex[:8]}", [], preset["message"], execute_off, attachment_text
    )
    after = service.get_account(session, user.id).balance
    calls = [asdict(tc) for tc in result.tool_calls]
    verdict = judge_s1(calls) if preset["id"] == "S1" else judge_s2(result.reply, calls)
    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "preset": preset["id"],
        "mode": "off",
        "model": llm.model,
        "message": preset["message"],
        "reply": result.reply,
        "tool_calls": calls,
        "balance_before": before,
        "balance_after": after,
        **verdict,
    }


def append_observation(record: dict[str, Any]) -> None:
    OBSERVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    records = json.loads(OBSERVE_FILE.read_text(encoding="utf-8")) if OBSERVE_FILE.exists() else []
    records.append(record)
    OBSERVE_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def interactive(session: Session, llm: LLM, user: Customer, attach_path: Path | None) -> None:
    print(f"[방어 OFF] {user.name}({user.id})로 대화합니다. 끝내려면 빈 줄 또는 Ctrl+C.\n")
    history: list[Message] = []
    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    attachment_text = attach(session, user, attach_path) if attach_path else None
    if attachment_text is not None:
        print(f"(첨부: {attach_path.name}, {len(attachment_text)}자 추출)\n")  # type: ignore[union-attr]
    while True:
        try:
            message = input("나> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            break
        print_turn(run_turn(session, llm, user, "off", session_id, history, message, execute_off, attachment_text))
        attachment_text = None  # 첨부는 첫 메시지에만 붙인다


def main() -> int:
    parser = argparse.ArgumentParser(description="KoFinGuard 명령줄 대화 (방어 OFF)")
    parser.add_argument("--mode", choices=["off"], default="off", help="ON은 Phase 7에서 추가")
    parser.add_argument("--user", default="minsu", help="로그인 아이디 (기본 minsu)")
    parser.add_argument("--preset", help="S1, S2 또는 all")
    parser.add_argument("--attach", type=Path, help="첫 메시지에 붙일 PDF/txt")
    args = parser.parse_args()

    db.load_env()
    try:
        require_off_allowed()
        llm = OpenAILLM()
        engine = db.get_engine()
        db.check_connection(engine)
    except (ModeNotAllowedError, LLMConfigError, db.DatabaseConfigError) as e:
        print(e, file=sys.stderr)
        return 1

    with Session(engine) as session:
        user = session.scalar(select(Customer).where(Customer.login_id == args.user))
        if user is None:
            print(f"사용자를 찾을 수 없습니다: {args.user}", file=sys.stderr)
            return 1
        if not args.preset:
            interactive(session, llm, user, args.attach)
            return 0

        presets = load_presets()
        chosen = presets if args.preset == "all" else [p for p in presets if p["id"] == args.preset]
        if not chosen:
            print(f"없는 preset입니다. 가능한 값: {', '.join(p['id'] for p in presets)}, all", file=sys.stderr)
            return 1
        for preset in chosen:
            print(f"=== {preset['id']} ({preset['label']}) ===\n나> {preset['message']}")
            record = run_preset(session, llm, user, preset)
            for tc in record["tool_calls"]:
                print(f"  [툴] {tc['tool']}({json.dumps(tc['args'], ensure_ascii=False)})")
            print(f"챗봇> {record['reply']}")
            print(f"판정: {'뚫림' if record['breached'] else '안 뚫림'} ({record['evidence']})")
            print(f"잔액: {record['balance_before']:,} → {record['balance_after']:,}\n")
            append_observation(record)
        print(f"기록: {OBSERVE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
