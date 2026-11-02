"""D-03 위험 판정: Ollama의 Llama Guard 3 (기본 llama-guard3:8b, 느리면 llama-guard3:1b).

졸프 노트북에는 Guard 로딩 코드가 없어서 새로 작성했다. 판정 방식은 졸프 4_20 노트북의 check_llama_guard처럼
모델 출력 첫 줄이 'unsafe'면 위험으로 본다. 출력을 해석할 수 없거나 Ollama에 연결할 수 없으면 '판정 불가'로 올려서
파이프라인이 통과시키지 않게 한다.
"""

import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama-guard3:8b"
TIMEOUT_SECONDS = 120.0

# Llama Guard 3 위험 분류 (MLCommons)
CATEGORIES = {
    "S1": "폭력 범죄",
    "S2": "비폭력 범죄",
    "S3": "성범죄",
    "S4": "아동 성착취",
    "S5": "명예훼손",
    "S6": "전문 조언",
    "S7": "개인정보 침해",
    "S8": "지식재산권",
    "S9": "대량살상무기",
    "S10": "혐오",
    "S11": "자해",
    "S12": "성적 콘텐츠",
    "S13": "선거",
    "S14": "코드 인터프리터 악용",
}


class GuardUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class GuardResult:
    safe: bool
    categories: list[str] = field(default_factory=list)
    raw: str = ""


class Guard(Protocol):
    model: str

    def judge(self, text: str) -> GuardResult: ...


def parse_guard_output(raw: str) -> GuardResult:
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        raise GuardUnavailableError("Llama Guard 출력이 비어 있습니다")
    head = lines[0].lower()
    if head == "safe":
        return GuardResult(True, [], raw)
    if head == "unsafe":
        cats = [c.strip() for c in lines[1].split(",")] if len(lines) > 1 else []
        return GuardResult(False, [c for c in cats if c], raw)
    raise GuardUnavailableError(f"Llama Guard 출력을 해석할 수 없습니다: {raw[:80]!r}")


class OllamaGuard:
    def __init__(self, url: str | None = None, model: str | None = None) -> None:
        self.url = (url or os.environ.get("KFG_OLLAMA_URL") or DEFAULT_URL).rstrip("/")
        self.model = model or os.environ.get("KFG_GUARD_MODEL") or DEFAULT_MODEL

    def judge(self, text: str) -> GuardResult:
        try:
            res = httpx.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": text}],
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=TIMEOUT_SECONDS,
            )
            res.raise_for_status()
            raw = res.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise GuardUnavailableError(f"Ollama Llama Guard를 쓸 수 없습니다 ({type(e).__name__})") from None
        return parse_guard_output(raw)
