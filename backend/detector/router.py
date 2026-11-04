"""D-01~D-04 입력 검사 흐름 (spec 4.1, 보조 레이어).

    입력 → [D-01 정리] → [D-02 SmoothPPL] + [D-03 Llama Guard]
      ├ Guard 위험                  → 차단 (block)
      ├ Guard 안전 + 점수 기준 이하  → 통과 (pass)
      └ Guard 안전 + 점수 기준 초과  → [D-04 다시 묻기] (reask, 막지 않음)

점수(PPL)만으로는 절대 막지 않는다. 모델을 못 쓰면 통과시키지 않는다(unavailable).

결합 규칙은 졸프 코드에 없어서 Phase 6에서 정했다: '점수'는 SmoothPPL 평균(mean_ppl) 하나만 본다.
평균+분산(규칙 B)도 실측했지만 결과가 같았고, 분산을 기준으로 쓰는 근거 논문을 찾지 못했다.
분산(var_ppl)은 기록만 한다.
"""

import concurrent.futures as cf
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from detector.guard import Guard, GuardUnavailableError, OllamaGuard
from detector.normalize import normalize
from detector.smoothppl import NUM_SAMPLES, LlamaCppPPL, PPLScorer, calculate_smooth_stats, num_samples_from_env

Action = Literal["pass", "block", "reask", "unavailable"]

MESSAGES: dict[str, str] = {
    "block": "보안 정책상 처리할 수 없는 요청입니다.",
    "reask": "알아보기 어려운 문장이 있어요. 일반 문장으로 다시 말씀해 주세요.",
    "unavailable": "보안 검사를 할 수 없어 요청을 처리하지 않았습니다.",
}

BACKEND_DIR = Path(__file__).resolve().parents[1]


class DetectorConfigError(RuntimeError):
    pass


@dataclass
class Verdict:
    action: Action
    normalized: str
    mean_ppl: float | None = None
    var_ppl: float | None = None
    jamo_flag: bool | None = None
    guard_safe: bool | None = None
    guard_categories: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)  # 초
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Detector:
    def __init__(self, scorer: PPLScorer, guard: Guard, ppl_threshold: float, num_samples: int = NUM_SAMPLES) -> None:
        self.scorer = scorer
        self.guard = guard
        self.ppl_threshold = ppl_threshold
        self.num_samples = num_samples

    def _run_ppl(self, text: str) -> tuple[Any, float]:
        t = time.perf_counter()
        stats = calculate_smooth_stats(text, self.scorer, self.num_samples)
        return stats, time.perf_counter() - t

    def _run_guard(self, normalized: str) -> tuple[Any, float]:
        t = time.perf_counter()
        guard = self.guard.judge(normalized)
        return guard, time.perf_counter() - t

    def check(self, text: str) -> Verdict:
        verdict = Verdict(action="unavailable", normalized=normalize(text))

        # D-02(SmoothPPL)와 D-03(Llama Guard)은 서로 독립이라 병렬로 돌려 대기 시간을 줄인다.
        # (llama_cpp 추론과 ollama HTTP 호출이 각각 GIL을 풀어 2코어에서 동시에 진행된다.)
        # D-04 결정은 둘 다 끝난 뒤에 한다. 어느 하나라도 실패하면 통과시키지 않는다(unavailable).
        with cf.ThreadPoolExecutor(max_workers=2) as pool:
            ppl_future = pool.submit(self._run_ppl, text)
            guard_future = pool.submit(self._run_guard, verdict.normalized)

            try:
                stats, ppl_time = ppl_future.result()
            except Exception as e:  # 모델 오류도 통과시키지 않는다
                verdict.error = f"SmoothPPL 실패 ({type(e).__name__})"
                return verdict
            verdict.timings["smoothppl"] = ppl_time
            verdict.mean_ppl, verdict.var_ppl, verdict.jamo_flag = stats.mean_ppl, stats.var_ppl, stats.jamo_flag

            try:
                guard, guard_time = guard_future.result()
            except GuardUnavailableError as e:
                verdict.error = str(e)
                return verdict
            verdict.timings["guard"] = guard_time
            verdict.guard_safe, verdict.guard_categories = guard.safe, guard.categories

        if not guard.safe:
            verdict.action = "block"
        elif stats.mean_ppl > self.ppl_threshold:
            verdict.action = "reask"
        else:
            verdict.action = "pass"
        return verdict


def threshold_from_env() -> float:
    raw = os.environ.get("KFG_PPL_THRESHOLD", "").strip()
    try:
        return float(raw)
    except ValueError:
        raise DetectorConfigError("backend/.env에 KFG_PPL_THRESHOLD(숫자)를 넣어 주세요 (Phase 6 결정값: 5000).") from None


def qwen_path_from_env() -> Path:
    raw = os.environ.get("KFG_QWEN_GGUF_PATH", "").strip()
    if not raw:
        raise DetectorConfigError("backend/.env에 KFG_QWEN_GGUF_PATH를 넣어 주세요.")
    path = Path(raw)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


def build_detector() -> Detector:
    """실제 모델로 탐지기를 만든다. 설정이나 모델 파일이 없으면 DetectorConfigError."""
    threshold = threshold_from_env()
    try:
        scorer = LlamaCppPPL(qwen_path_from_env())
    except FileNotFoundError as e:
        raise DetectorConfigError(str(e)) from None
    return Detector(scorer, OllamaGuard(), threshold, num_samples_from_env())
