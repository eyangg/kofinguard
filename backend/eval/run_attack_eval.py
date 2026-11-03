"""E-03 공격 성공률 (spec 7.2).

S1·S2·S3를 각 n회씩 OFF/ON으로 실제 실행하고, 공격이 뚫린 비율을 낸다.
- OFF 성공률 = 공격이 뚫린 비율(높을수록 취약) → OFF가 위험하다는 근거
- ON  성공률 = 공격이 뚫린 비율(낮을수록 안전) → 서버 방어가 막는다는 근거
결과는 캐시(artifacts/attack_eval_cache.json)해서 다시 돌릴 때 OpenAI 호출을 아낀다.

실행 (backend 폴더, Ollama 실행 중, 비용 발생):
    .\\.venv\\Scripts\\python.exe -m eval.run_attack_eval --n 5
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
import seed
from attachments import load_attachment_text, save_attachment
from chat.llm_client import LLM, LLMConfigError, OpenAILLM
from chat.pipeline import DetectorLike, run_chat
from detector.router import DetectorConfigError, build_detector
from models import Customer, EvalRun
from scenarios.attacks import S1_MESSAGE, S2_INVOICE_FILE, S2_MESSAGE, S3_MESSAGE, judge_s1, judge_s2, judge_s3

BACKEND = Path(__file__).resolve().parents[1]
OUT_FILE = BACKEND.parent / "artifacts" / "attack_eval.json"
CACHE_FILE = BACKEND.parent / "artifacts" / "attack_eval_cache.json"

SCENARIOS = {
    "S1": {"message": S1_MESSAGE, "attachment": None},
    "S2": {"message": S2_MESSAGE, "attachment": S2_INVOICE_FILE},
    "S3": {"message": S3_MESSAGE, "attachment": None},
}


def _judge(scenario: str, result: Any) -> bool:
    calls = [asdict(c) for c in result.tool_calls]
    if scenario == "S1":
        return bool(judge_s1(calls)["breached"])
    if scenario == "S2":
        return bool(judge_s2(result.reply, calls)["breached"])
    return bool(judge_s3(result.reply)["breached"])


def _attachment_text(session: Session, user: Customer, filename: str | None) -> str | None:
    if not filename:
        return None
    att = save_attachment(session, user.id, filename, (BACKEND / "scenarios" / "docs" / filename).read_bytes())
    return load_attachment_text(session, user.id, att.id)[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5, help="시나리오·모드별 반복 횟수 (기본 5)")
    parser.add_argument("--no-cache", action="store_true", help="캐시 무시하고 모두 새로 실행")
    args = parser.parse_args()

    db.load_env()
    try:
        llm: LLM = OpenAILLM()
        detector: DetectorLike = build_detector()
    except (LLMConfigError, DetectorConfigError) as e:
        print(e, file=sys.stderr)
        return 1

    cache: dict[str, bool] = {}
    if CACHE_FILE.exists() and not args.no_cache:
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    rows: list[dict[str, Any]] = []
    with Session(db.get_engine()) as session:
        seed.seed(session)
        user = session.scalar(select(Customer).where(Customer.login_id == "minsu"))
        if user is None:
            print("시드(minsu)가 없습니다.", file=sys.stderr)
            return 1

        for scenario, spec in SCENARIOS.items():
            for mode in ("off", "on"):
                breaches = 0
                used_cache = 0
                for i in range(args.n):
                    key = f"{llm.model}|{scenario}|{mode}|{i}"
                    if key in cache:
                        breached = cache[key]
                        used_cache += 1
                    else:
                        seed.reset(session)
                        text = _attachment_text(session, user, spec["attachment"])
                        result = run_chat(
                            session, llm, user, mode, f"eval-{uuid.uuid4().hex[:8]}", spec["message"],
                            detector=detector if mode == "on" else None, attachment_text=text,
                        )
                        breached = _judge(scenario, result)
                        cache[key] = breached
                    breaches += 1 if breached else 0
                rate = round(breaches / args.n, 2)
                rows.append({"scenario": scenario, "mode": mode, "n": args.n, "breaches": breaches, "rate": rate})
                print(f"  {scenario} {mode.upper():<3} 뚫림 {breaches}/{args.n} = {rate:.0%}  (캐시 {used_cache})")
        seed.reset(session)

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    env = {"model": llm.model, "guard_model": getattr(detector, "guard", None) and detector.guard.model}
    metrics = {f"{r['scenario']}_{r['mode']}": r["rate"] for r in rows}
    OUT_FILE.write_text(
        json.dumps(
            {"measured_at": datetime.now(timezone.utc).isoformat(), "n": args.n, "env": env, "rows": rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with Session(db.get_engine()) as s:
        s.add(EvalRun(kind="attack", config={"n": args.n}, metrics=metrics, env=env))
        s.commit()
    print(f"\n기록: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
