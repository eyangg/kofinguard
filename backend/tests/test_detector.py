"""졸프 탐지 파이프라인 테스트 (가짜 점수기·가짜 Guard, 모델·인터넷 없이)."""

import random
import unicodedata

import pytest

from detector.guard import GuardResult, GuardUnavailableError, OllamaGuard, parse_guard_output
from detector.normalize import is_jamo_heavy, normalize
from detector.router import MESSAGES, Detector, DetectorConfigError, threshold_from_env
from detector.smoothppl import NOISE_CHARS, NUM_SAMPLES, calculate_smooth_stats, perturb_text


class FakeScorer:
    """문장 길이로 PPL을 흉내 낸다. ppl 값을 고정하고 싶으면 value를 준다."""

    def __init__(self, value: float | None = None, fail: bool = False) -> None:
        self.value = value
        self.fail = fail
        self.calls: list[str] = []

    def ppl(self, text: str) -> float:
        if self.fail:
            raise RuntimeError("model crashed")
        self.calls.append(text)
        return self.value if self.value is not None else float(len(text))


class FakeGuard:
    model = "fake-guard"

    def __init__(self, result: GuardResult | None = None, down: bool = False) -> None:
        self.result = result or GuardResult(True)
        self.down = down
        self.seen: list[str] = []

    def judge(self, text: str) -> GuardResult:
        if self.down:
            raise GuardUnavailableError("Ollama 꺼짐")
        self.seen.append(text)
        return self.result


# ---- D-01 문장 정리 (졸프 normalize_korean·is_jamo_heavy와 같은 동작) ----


def test_normalize_is_nfc_like_capstone() -> None:
    decomposed = unicodedata.normalize("NFD", "잔액")  # 첫가끝 자모로 분해된 한글
    assert decomposed != "잔액"
    assert normalize(decomposed) == "잔액"
    # 키보드 자모는 합치지 않는다 (졸프 원본 동작)
    assert normalize("ㅍㅗㄱㅌㅏㄴ") == "ㅍㅗㄱㅌㅏㄴ"


def test_is_jamo_heavy_threshold_0_2() -> None:
    assert is_jamo_heavy("ㅈㅏㄴㅇㅐㄱ") is True
    assert is_jamo_heavy("잔액 알려줘") is False
    assert is_jamo_heavy("") is False


# ---- D-02 SmoothPPL (졸프 perturb_text·calculate_smooth_stats와 같은 규칙) ----


def test_perturb_text_like_capstone() -> None:
    text = "최근 거래내역 5개 보여줘"  # 14글자 → 잡음 max(1, int(1.4)) = 1개
    samples = perturb_text(text, rng=random.Random(0))
    assert len(samples) == NUM_SAMPLES
    for s in samples:
        assert len(s) == len(text) + 1
        extra = [c for c in s]
        for c in text:
            extra.remove(c)
        assert extra[0] in NOISE_CHARS
    long_text = "가" * 35  # 잡음 3개
    assert all(len(s) == 38 for s in perturb_text(long_text, rng=random.Random(0)))


def test_smooth_stats_mean_and_var() -> None:
    stats = calculate_smooth_stats("잔액 알려줘", FakeScorer(value=10.0))
    assert stats.mean_ppl == 10.0 and stats.var_ppl == 0.0 and stats.jamo_flag is False


def test_smooth_stats_is_reproducible() -> None:
    a = calculate_smooth_stats("이체 한도가 얼마예요?", FakeScorer())
    b = calculate_smooth_stats("이체 한도가 얼마예요?", FakeScorer())
    assert a == b


# ---- D-03 Llama Guard 출력 해석 ----


def test_parse_guard_output() -> None:
    assert parse_guard_output("safe") == GuardResult(True, [], "safe")
    r = parse_guard_output("\n\nunsafe\nS2,S7")
    assert r.safe is False and r.categories == ["S2", "S7"]
    with pytest.raises(GuardUnavailableError):
        parse_guard_output("")
    with pytest.raises(GuardUnavailableError):
        parse_guard_output("I cannot help with that")


def test_ollama_down_is_unavailable() -> None:
    guard = OllamaGuard(url="http://127.0.0.1:9", model="llama-guard3:1b")  # 아무도 듣지 않는 포트
    with pytest.raises(GuardUnavailableError):
        guard.judge("잔액 알려줘")


# ---- D-01~D-04 결합 (spec 4.1, 규칙: 평균 PPL 하나) ----


def test_guard_unsafe_blocks_even_with_low_score() -> None:
    v = Detector(FakeScorer(value=10), FakeGuard(GuardResult(False, ["S2"])), 5000).check("송금 사기 문구")
    assert v.action == "block" and v.guard_categories == ["S2"]


def test_safe_and_low_score_passes() -> None:
    v = Detector(FakeScorer(value=100), FakeGuard(), 5000).check("잔액 알려줘")
    assert v.action == "pass"
    assert v.mean_ppl == 100 and v.guard_safe is True
    assert set(v.timings) == {"smoothppl", "guard"}


def test_safe_and_high_score_reasks_not_blocks() -> None:
    """점수(PPL)만으로는 절대 막지 않는다."""
    v = Detector(FakeScorer(value=9000), FakeGuard(), 5000).check("뷁쉙 똵롹")
    assert v.action == "reask"


def test_variance_is_recorded_but_not_used() -> None:
    class Spiky:
        def __init__(self) -> None:
            self.n = 0

        def ppl(self, text: str) -> float:
            self.n += 1
            return 1.0 if self.n % 2 else 4000.0  # 평균 약 2000, 분산은 매우 큼

    v = Detector(Spiky(), FakeGuard(), 5000).check("잔액")
    assert v.var_ppl is not None and v.var_ppl > 1_000_000
    assert v.action == "pass"


def test_guard_down_is_not_passed() -> None:
    v = Detector(FakeScorer(value=10), FakeGuard(down=True), 5000).check("잔액 알려줘")
    assert v.action == "unavailable" and v.error
    assert MESSAGES["unavailable"].startswith("보안 검사를 할 수 없어")


def test_scorer_failure_is_not_passed() -> None:
    v = Detector(FakeScorer(fail=True), FakeGuard(), 5000).check("잔액 알려줘")
    assert v.action == "unavailable" and "SmoothPPL" in (v.error or "")


def test_guard_sees_normalized_text() -> None:
    guard = FakeGuard()
    Detector(FakeScorer(value=1), guard, 5000).check(unicodedata.normalize("NFD", "잔액"))
    assert guard.seen == ["잔액"]


def test_threshold_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KFG_PPL_THRESHOLD", "5000")
    assert threshold_from_env() == 5000.0
    monkeypatch.setenv("KFG_PPL_THRESHOLD", "")
    with pytest.raises(DetectorConfigError):
        threshold_from_env()
