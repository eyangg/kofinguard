"""E-03 공격 성공률 (spec 7.2).

S1·S2·S3를 각 n회씩 OFF/ON으로 실제 실행하고, 공격이 뚫린 비율을 낸다.
- OFF 성공률 = 공격이 뚫린 비율(높을수록 취약) → OFF가 위험하다는 근거
- ON  성공률 = 공격이 뚫린 비율(낮을수록 안전) → 서버 방어가 막는다는 근거
결과는 캐시(artifacts/attack_eval_cache.json)해서 다시 돌릴 때 OpenAI 호출을 아낀다.

--core-only: 방어 ON에서 입력 탐지기(D-01~D-04)만 빼고(항상 통과) 핵심 방어(D-05~D-09)만으로 돌린다.
S2처럼 탐지기가 먼저 막는 공격을 핵심 방어가 혼자서도 막는지 보는 실험이다. Ollama 불필요.
결과는 artifacts/attack_eval_core_only.json에 따로 쓰고, 회차마다 핵심 방어가 실제로 한 일도 센다
(예: 'D-08 HTML 태그 인코딩' = 답변 속 코드를 무력화, 'D-08 계좌번호 마스킹' = 계좌번호만 가림).

실행 (backend 폴더, Ollama 실행 중, 비용 발생):
    .\\.venv\\Scripts\\python.exe -m eval.run_attack_eval --n 10
    .\\.venv\\Scripts\\python.exe -m eval.run_attack_eval --n 10 --core-only
"""

import argparse
import json
import re
import sys
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import db

# scenarios.attacks는 import 시점에 KFG_ATTACKER_BASE(공격자 수집 주소)를 읽는다.
# 그 import보다 먼저 .env를 불러와야, 평가를 수동 실행해도 systemd 서비스와 같은 값(배포는 /api/demo)을 쓴다.
# (안 그러면 평가 프로세스에 기본값 127.0.0.1이 박혀 배포 PDF와 어긋나고, S2가 실제로 뚫려도 판정이 놓친다.)
db.load_env()

import seed
from attachments import load_attachment_text, save_attachment
from chat.llm_client import LLM, LLMConfigError, OpenAILLM
from chat.pipeline import DetectorLike, run_chat
from detector.router import DetectorConfigError, Verdict, build_detector
from models import Customer, EvalRun
from scenarios.attacks import S1_MESSAGE, S2_INVOICE_FILE, S2_MESSAGE, S3_MESSAGE, judge_s1, judge_s2, judge_s3

BACKEND = Path(__file__).resolve().parents[1]
OUT_FILE = BACKEND.parent / "artifacts" / "attack_eval.json"
CACHE_FILE = BACKEND.parent / "artifacts" / "attack_eval_cache.json"
CORE_OUT_FILE = BACKEND.parent / "artifacts" / "attack_eval_core_only.json"
CORE_CACHE_FILE = BACKEND.parent / "artifacts" / "attack_eval_core_only_cache.json"

INPUT_LAYERS = {"D-01", "D-02", "D-03", "D-04"}


class PassDetector:
    """--core-only 전용: 입력 검사를 항상 통과시켜 핵심 방어(D-05~D-09)만 떼어 본다. 서비스에서는 쓰지 않는다."""

    guard = None

    def check(self, text: str) -> Verdict:
        return Verdict(action="pass", normalized=text)


def acted(result: Any) -> list[str]:
    """이번 턴에 핵심 방어(D-05~D-09)가 실제로 한 일. 개수·고객번호는 빼서 회차끼리 합칠 수 있게 한다.

    D-05~D-07 툴 검사는 서버가 손댄 경우(사유가 있을 때)만 센다. D-07 문서 격리 표시는 매번 붙지만 기록은 없다.
    """
    out: set[str] = set()
    for e in result.trace:
        if e.layer in INPUT_LAYERS:
            continue
        if e.layer == "D-08":
            out.update(f"D-08 {re.sub(r' ?[0-9]+개', '', c)}" for c in e.detail.get("changes", []))
        elif e.layer == "D-09":
            out.add("D-09 답변 차단")
        elif e.detail.get("reason"):
            out.add(f"{e.layer} {re.sub(r'\([^)]*\)', '', str(e.detail['reason'])).strip()}")
    return sorted(out)

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
    parser.add_argument("--core-only", action="store_true", help="방어 ON에서 탐지기를 빼고 핵심 방어(D-05~D-09)만으로 실행")
    args = parser.parse_args()
    core_only: bool = args.core_only
    out_file = CORE_OUT_FILE if core_only else OUT_FILE
    cache_file = CORE_CACHE_FILE if core_only else CACHE_FILE
    modes = ("on",) if core_only else ("off", "on")

    try:
        llm: LLM = OpenAILLM()
        detector: DetectorLike = PassDetector() if core_only else build_detector()
    except (LLMConfigError, DetectorConfigError) as e:
        print(e, file=sys.stderr)
        return 1

    # 일반: 키 → 뚫림 여부(bool). core-only: 키 → {"breached": bool, "actions": [...]}
    cache: dict[str, Any] = {}
    if cache_file.exists() and not args.no_cache:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))

    rows: list[dict[str, Any]] = []
    with Session(db.get_engine()) as session:
        seed.seed(session)
        user = session.scalar(select(Customer).where(Customer.login_id == "minsu"))
        if user is None:
            print("시드(minsu)가 없습니다.", file=sys.stderr)
            return 1

        for scenario, spec in SCENARIOS.items():
            for mode in modes:
                breaches = 0
                used_cache = 0
                actions: Counter[str] = Counter()  # 방어가 한 일 → 그 일이 있었던 회차 수
                quiet = 0  # 방어가 끼어들 일이 없었던 회차 (챗봇이 공격에 넘어가지 않음)
                for i in range(args.n):
                    key = f"{llm.model}|{scenario}|{mode}|{i}"
                    if key in cache:
                        hit = cache[key]
                        used_cache += 1
                    else:
                        seed.reset(session)
                        text = _attachment_text(session, user, spec["attachment"])
                        result = run_chat(
                            session, llm, user, mode, f"eval-{uuid.uuid4().hex[:8]}", spec["message"],
                            detector=detector if mode == "on" else None, attachment_text=text,
                        )
                        breached = _judge(scenario, result)
                        hit = {"breached": breached, "actions": acted(result)} if core_only else breached
                        cache[key] = hit
                    if core_only:
                        breached = hit["breached"]
                        actions.update(hit["actions"])
                        quiet += 0 if hit["actions"] else 1
                    else:
                        breached = hit
                    breaches += 1 if breached else 0
                rate = round(breaches / args.n, 2)
                row: dict[str, Any] = {"scenario": scenario, "mode": mode, "n": args.n, "breaches": breaches, "rate": rate}
                if core_only:
                    row["actions"] = dict(sorted(actions.items()))
                    row["quiet"] = quiet
                rows.append(row)
                extra = f"  방어가 한 일 {row['actions']} · 끼어들 일 없음 {quiet}" if core_only else ""
                print(f"  {scenario} {mode.upper():<3} 뚫림 {breaches}/{args.n} = {rate:.0%}  (캐시 {used_cache}){extra}")
        seed.reset(session)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    if core_only:
        env: dict[str, Any] = {"model": llm.model, "detector": "off (핵심 방어만)"}
    else:
        env = {"model": llm.model, "guard_model": getattr(detector, "guard", None) and detector.guard.model}
    metrics = {f"{r['scenario']}_{r['mode']}": r["rate"] for r in rows}
    out_file.write_text(
        json.dumps(
            {"measured_at": datetime.now(timezone.utc).isoformat(), "n": args.n, "env": env, "rows": rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with Session(db.get_engine()) as s:
        s.add(EvalRun(kind="attack_core" if core_only else "attack", config={"n": args.n}, metrics=metrics, env=env))
        s.commit()
    print(f"\n기록: {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
