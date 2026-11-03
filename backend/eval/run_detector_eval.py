"""E-02 탐지기 운영 지표 (spec 7.1).

정상 은행 질문 30개와 공격 입력(S1·S2·S3)을 졸프 파이프라인(D-01~D-04)에 넣어
- 정상 질문 오탐률(차단 + 다시 묻기)
- 단계별 판정 평균 시간
- 공격 입력별 판정
을 잰다. 결과는 artifacts/detector_eval.json과 eval_runs 테이블에 저장한다.

실행 (backend 폴더, Ollama 실행 중):
    .\\.venv\\Scripts\\python.exe -m eval.run_detector_eval
"""

import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

import db
from attachments import extract_text
from detector.router import DetectorConfigError, build_detector
from detector.smoothppl import NUM_SAMPLES
from models import EvalRun
from scenarios.attacks import S1_MESSAGE, S2_INVOICE_FILE, S3_MESSAGE

BACKEND = Path(__file__).resolve().parents[1]
NORMAL_FILE = BACKEND / "eval" / "datasets" / "normal_bank_questions.json"
OUT_FILE = BACKEND.parent / "artifacts" / "detector_eval.json"


def _attacks() -> dict[str, str]:
    s2_doc = extract_text((BACKEND / "scenarios" / "docs" / S2_INVOICE_FILE).read_bytes(), ".pdf")
    return {"S1": S1_MESSAGE, "S2(문서)": s2_doc, "S3": S3_MESSAGE}


def _row(label: str, verdict: Any) -> dict[str, Any]:
    v = verdict.as_dict()
    return {
        "label": label,
        "action": verdict.action,
        "mean_ppl": round(v["mean_ppl"], 1) if v["mean_ppl"] is not None else None,
        "guard_safe": v["guard_safe"],
        "sec": round(sum(v["timings"].values()), 2),
        "timings": {k: round(x, 2) for k, x in v["timings"].items()},
    }


def main() -> int:
    db.load_env()
    try:
        detector = build_detector()
    except DetectorConfigError as e:
        print(e, file=sys.stderr)
        return 1

    normal_texts = json.loads(NORMAL_FILE.read_text(encoding="utf-8"))
    print(f"정상 질문 {len(normal_texts)}개 판정 중...")
    normal = [_row(f"N{i + 1:02d}", detector.check(q)) for i, q in enumerate(normal_texts)]
    for r, q in zip(normal, normal_texts):
        if r["action"] != "pass":
            print(f"  오탐 [{r['action']}] {q}")

    print("공격 입력 판정 중...")
    attacks = [_row(label, detector.check(text)) for label, text in _attacks().items()]
    for r in attacks:
        print(f"  {r['label']:<8} action={r['action']} guard_safe={r['guard_safe']} ({r['sec']}s)")

    blocked = sum(1 for r in normal if r["action"] == "block")
    reask = sum(1 for r in normal if r["action"] == "reask")
    n = len(normal)
    metrics = {
        "normal_total": n,
        "normal_pass": n - blocked - reask,
        "normal_blocked": blocked,
        "normal_reask": reask,
        "false_positive_rate": round((blocked + reask) / n, 3) if n else 0.0,
        "avg_sec": round(sum(r["sec"] for r in normal) / n, 2) if n else 0.0,
        "attacks": {r["label"]: r["action"] for r in attacks},
    }
    env = {
        "cpu": platform.processor(),
        "guard_model": detector.guard.model,
        "ppl_threshold": detector.ppl_threshold,
        "num_samples": NUM_SAMPLES,
    }
    record = {
        "kind": "detector",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "env": env,
        "metrics": metrics,
        "normal": normal,
        "attacks": attacks,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with Session(db.get_engine()) as s:
        s.add(EvalRun(kind="detector", config={"dataset": NORMAL_FILE.name}, metrics=metrics, env=env))
        s.commit()

    print(
        f"\n오탐률 {metrics['false_positive_rate']:.0%} "
        f"(정상 {n}개 중 차단 {blocked} · 다시 묻기 {reask} · 통과 {metrics['normal_pass']})"
    )
    print(f"평균 판정 {metrics['avg_sec']}s · 공격 판정 {metrics['attacks']}")
    print(f"기록: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
