"""D-02 SmoothPPL 점수 (보조 레이어). 점수만으로는 막지 않는다.

졸프 이식: capstone_ref/SmoothPPL_Qwen_졸프코드추정.ipynb 셀 3 — perturb_text, calculate_ppl, calculate_smooth_stats.

졸프와 같은 것
- 잡음 문자 [' ', '!', '@', '#', '.', '?'] 중 하나를 글자 수의 10%(최소 1개)만큼 무작위 위치에 끼운 문장 15개를 만든다.
- 각 문장의 PPL을 재서 평균(mean_ppl)과 분산(var_ppl, np.var)을 낸다. 자모 비율 표시(jamo_flag)도 같이 돌려준다.
졸프와 다른 것
- 모델 실행: transformers fp16 GPU → llama-cpp-python + Qwen2.5-3B-Instruct GGUF(Q4_K_M) CPU (spec 8.1).
  그래서 점수 크기가 졸프와 다르고, 기준값은 이 환경에서 다시 정한다.
- 무작위: 졸프는 seed가 없었다. 같은 문장은 같은 점수가 나오도록 문장별 고정 seed를 쓴다.
"""

import hashlib
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from detector.normalize import is_jamo_heavy, normalize_korean

NOISE_CHARS = [" ", "!", "@", "#", ".", "?"]
PERTURBATION_RATE = 0.1
NUM_SAMPLES = 15  # 졸프 값. 배포에서만 KFG_PPL_NUM_SAMPLES로 줄여 CPU 추론 횟수를 낮춘다.
N_CTX = 2048


def num_samples_from_env() -> int:
    """SmoothPPL 교란 샘플 수. 1회 검사당 모델 추론 횟수(=속도)를 좌우한다.

    기본은 NUM_SAMPLES(15, 졸프 값)이고, 배포에서 KFG_PPL_NUM_SAMPLES로만 줄인다.
    PPL은 라우팅 전용(단독 차단 안 함)이라 샘플을 줄여도 차단 로직엔 영향이 작지만,
    값을 바꾸면 calibrate로 임계값(KFG_PPL_THRESHOLD)을 다시 확인한다.
    """
    raw = os.environ.get("KFG_PPL_NUM_SAMPLES", "").strip()
    if not raw:
        return NUM_SAMPLES
    try:
        return max(1, int(raw))
    except ValueError:
        return NUM_SAMPLES


@dataclass(frozen=True)
class SmoothStats:
    mean_ppl: float
    var_ppl: float
    jamo_flag: bool


class PPLScorer(Protocol):
    def ppl(self, text: str) -> float: ...


def perturb_text(
    text: str,
    perturbation_rate: float = PERTURBATION_RATE,
    num_samples: int = NUM_SAMPLES,
    rng: random.Random | None = None,
) -> list[str]:
    rng = rng or random.Random()
    perturbed_samples = []
    chars = list(text)
    for _ in range(num_samples):
        temp_chars = chars.copy()
        num_noise = max(1, int(len(temp_chars) * perturbation_rate))
        for _ in range(num_noise):
            idx = rng.randint(0, len(temp_chars))
            temp_chars.insert(idx, rng.choice(NOISE_CHARS))
        perturbed_samples.append("".join(temp_chars))
    return perturbed_samples


def _stable_seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def calculate_smooth_stats(
    text: str, scorer: PPLScorer, num_samples: int = NUM_SAMPLES, seed: int | None = None
) -> SmoothStats:
    jamo_flag = is_jamo_heavy(text)
    clean_text = normalize_korean(text)
    rng = random.Random(_stable_seed(clean_text) if seed is None else seed)
    samples = perturb_text(clean_text, PERTURBATION_RATE, num_samples, rng)
    ppl_values = [scorer.ppl(s) for s in samples]
    return SmoothStats(float(np.mean(ppl_values)), float(np.var(ppl_values)), jamo_flag)


class LlamaCppPPL:
    """Qwen GGUF로 PPL을 잰다. 졸프 calculate_ppl(HF labels=input_ids의 loss)과 같은 정의:
    다음 토큰을 맞히는 평균 음의 로그우도의 exp. BOS는 붙이지 않는다 (Qwen 토크나이저와 같음)."""

    def __init__(self, model_path: Path, n_threads: int | None = None) -> None:
        from llama_cpp import Llama  # 기본 pytest에서는 불러오지 않도록 여기서 import

        if not model_path.is_file():
            raise FileNotFoundError(f"Qwen GGUF 파일이 없습니다: {model_path}")
        self._llm: Any = Llama(
            model_path=str(model_path), n_ctx=N_CTX, logits_all=True, n_threads=n_threads, verbose=False
        )

    def ppl(self, text: str) -> float:
        normalized_text = normalize_korean(text)
        if not normalized_text.strip():
            return 0.0
        tokens = self._llm.tokenize(normalized_text.encode("utf-8"), add_bos=False, special=False)[:N_CTX]
        if len(tokens) < 2:
            return 0.0
        self._llm.reset()
        self._llm.eval(tokens)
        # scores는 (토큰 수 × 어휘 15만) float32 배열이다. 복사·형변환 없이 행마다 log-softmax를 계산한다.
        logits = np.asarray(self._llm.scores[: len(tokens) - 1])
        row_max = logits.max(axis=1)
        log_norm = row_max + np.log(np.exp(logits - row_max[:, None]).sum(axis=1, dtype=np.float64))
        target = logits[np.arange(len(tokens) - 1), tokens[1:]]
        return float(np.exp(np.mean(log_norm - target)))
