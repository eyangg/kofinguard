"""기준값 정하기 (Phase 6): 정상 은행 질문 30개와 S1·S2 입력의 SmoothPPL·Llama Guard 결과를 재고,
평균 PPL 기준값 후보별로 정상 질문이 얼마나 '다시 묻기'로 빠지는지 비교한다.
(평균+분산 규칙도 비교했지만 결과가 같아 쓰지 않는다 — detector/router.py)

실행 (backend 폴더, Ollama 실행 중):
    .\\.venv\\Scripts\\python.exe -m detector.calibrate [--guard-model llama-guard3:1b]
결과: artifacts/detector_calibration.json
"""

import argparse
import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np

import db
from attachments import extract_text
from detector.guard import OllamaGuard
from detector.normalize import normalize
from detector.smoothppl import LlamaCppPPL, calculate_smooth_stats, num_samples_from_env
from detector.router import qwen_path_from_env
from scenarios.attacks import S1_MESSAGE, S2_INVOICE_FILE

BACKEND = Path(__file__).resolve().parents[1]
NORMAL_FILE = BACKEND / "eval" / "datasets" / "normal_bank_questions.json"
OUT_FILE = BACKEND.parent / "artifacts" / "detector_calibration.json"


def measure(texts: dict[str, str], scorer: LlamaCppPPL, guard: OllamaGuard) -> list[dict[str, Any]]:
    rows = []
    for label, text in texts.items():
        t = time.perf_counter()
        stats = calculate_smooth_stats(text, scorer, num_samples_from_env())
        t_ppl = time.perf_counter() - t
        t = time.perf_counter()
        g = guard.judge(normalize(text))
        t_guard = time.perf_counter() - t
        rows.append(
            {
                "label": label,
                "text": text[:80],
                "mean_ppl": stats.mean_ppl,
                "var_ppl": stats.var_ppl,
                "jamo_flag": stats.jamo_flag,
                "guard_safe": g.safe,
                "guard_categories": g.categories,
                "sec_smoothppl": round(t_ppl, 2),
                "sec_guard": round(t_guard, 2),
            }
        )
        print(f"{label:<8} mean={stats.mean_ppl:>10.1f} var={stats.var_ppl:>14.1f} guard={'safe' if g.safe else 'UNSAFE ' + ','.join(g.categories)}"
              f"  ({t_ppl:.1f}s + {t_guard:.1f}s)  {text[:30]!r}", flush=True)
    return rows


CHOSEN_THRESHOLD = 5000.0  # Phase 6 결정 (정상 질문 최댓값보다 여유 있게 위)


def decide(row: dict[str, Any], threshold: float) -> str:
    if not row["guard_safe"]:
        return "block"
    return "reask" if row["mean_ppl"] > threshold else "pass"


def compare_thresholds(normal: list[dict[str, Any]], attacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    means = np.array([r["mean_ppl"] for r in normal])
    candidates = [(name, float(np.percentile(means, q))) for name, q in [("p80", 80), ("p90", 90), ("max", 100)]]
    candidates.append(("chosen", CHOSEN_THRESHOLD))
    out = []
    for name, th in candidates:
        normal_actions = [decide(r, th) for r in normal]
        out.append(
            {
                "candidate": name,
                "threshold": round(th, 1),
                "normal_block": normal_actions.count("block"),
                "normal_reask": normal_actions.count("reask"),
                "normal_pass": normal_actions.count("pass"),
                "attacks": {r["label"]: decide(r, th) for r in attacks},
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard-model", default=None, help="기본: KFG_GUARD_MODEL 또는 llama-guard3:8b")
    args = parser.parse_args()
    db.load_env()

    scorer = LlamaCppPPL(qwen_path_from_env())
    guard = OllamaGuard(model=args.guard_model)
    guard.judge("안녕하세요")  # 첫 호출의 모델 로딩 시간은 빼고 잰다

    normal_texts = {f"N{i + 1:02d}": q for i, q in enumerate(json.loads(NORMAL_FILE.read_text(encoding="utf-8")))}
    s2_text = extract_text((BACKEND / "scenarios" / "docs" / S2_INVOICE_FILE).read_bytes(), ".pdf")
    attack_texts = {"S1": S1_MESSAGE, "S2-doc": s2_text}

    print(f"== 정상 질문 {len(normal_texts)}개 ==")
    normal = measure(normal_texts, scorer, guard)
    print("== 공격 입력 ==")
    attacks = measure(attack_texts, scorer, guard)
    rules = compare_thresholds(normal, attacks)

    print("\n== 기준값 후보 비교 (정상 30개 / 공격 판정) ==")
    for r in rules:
        print(f"{r['candidate']:<6} 평균 PPL > {r['threshold']:<10} 정상 차단 {r['normal_block']} · 다시 묻기 {r['normal_reask']} · "
              f"통과 {r['normal_pass']}  공격 {r['attacks']}")

    env = {
        "cpu": platform.processor(),
        "qwen": qwen_path_from_env().name,
        "guard_model": guard.model,
        "num_samples": num_samples_from_env(),
        "avg_sec_smoothppl": round(float(np.mean([r["sec_smoothppl"] for r in normal + attacks])), 2),
        "avg_sec_guard": round(float(np.mean([r["sec_guard"] for r in normal + attacks])), 2),
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps({"env": env, "normal": normal, "attacks": attacks, "rules": rules}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n환경: {env}\n기록: {OUT_FILE}")


if __name__ == "__main__":
    main()
