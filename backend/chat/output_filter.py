"""답변 안전 처리 (spec 4.4 D-08). ON의 모든 답변에 적용한다.

실제 사례(2026년 7월 유럽 은행)에서 은행이 한 수정과 같이, 답변 속 HTML 특수문자를 인코딩해서
글자로만 보이게 한다. 외부 링크·이미지 문법을 지우고 계좌번호 가운데를 가린다.
무엇을 바꿨는지 근거 패널에 쓰도록 변경 내역을 함께 돌려준다.
"""

import html
import re
from dataclasses import dataclass, field

# D-09 시스템 프롬프트 유출 차단: 답변에 내부 지침 조각이 2개 이상 그대로 있으면 유출로 본다.
# (고객에게 정상적으로 할 말이 아닌, 시스템 프롬프트에만 있는 문구들)
PROMPT_LEAK_MARKERS = ["고객 상담 챗봇입니다", "본인 것만", "짧고 정확하게", "마크다운 표"]
PROMPT_LEAK_REFUSAL = "내부 운영 지침은 안내해 드릴 수 없습니다."


def detect_prompt_leak(reply: str) -> bool:
    return sum(1 for m in PROMPT_LEAK_MARKERS if m in reply) >= 2

# 마크다운 이미지 ![..](http...) 와 링크 [..](http...)
_IMAGE = re.compile(r"!\[[^\]]*\]\((https?://[^)]*)\)", re.IGNORECASE)
_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)]*)\)", re.IGNORECASE)
# 눈에 보이는 외부 URL
_URL = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
# 계좌번호 형태 111-1001-0001 (가운데 묶음을 가린다)
_ACCOUNT = re.compile(r"\b(\d{3})-(\d{2,4})-(\d{3,4})\b")


@dataclass
class FilterResult:
    text: str
    changes: list[str] = field(default_factory=list)


def _mask_account(m: re.Match[str]) -> str:
    return f"{m.group(1)}-{'*' * len(m.group(2))}-{m.group(3)}"


def filter_reply(reply: str) -> FilterResult:
    changes: list[str] = []

    images = len(_IMAGE.findall(reply))
    text = _IMAGE.sub("", reply)
    if images:
        changes.append(f"이미지 {images}개 제거")

    links = len(_LINK.findall(text))
    text = _LINK.sub(r"\1", text)  # 링크는 글자만 남긴다
    if links:
        changes.append(f"링크 {links}개 제거")

    bare_urls = len(_URL.findall(text))
    text = _URL.sub("[외부 링크 제거됨]", text)
    if bare_urls:
        changes.append(f"외부 URL {bare_urls}개 제거")

    accounts = len(_ACCOUNT.findall(text))
    text = _ACCOUNT.sub(_mask_account, text)
    if accounts:
        changes.append(f"계좌번호 {accounts}개 마스킹")

    # 남은 HTML 특수문자를 인코딩한다. onerror 같은 코드가 있어도 글자로만 보인다.
    if re.search(r"[<>]", text):
        tags = len(re.findall(r"<[^>]+>", text))
        changes.append(f"HTML 태그 {tags}개 인코딩" if tags else "HTML 특수문자 인코딩")
    text = html.escape(text, quote=False)

    return FilterResult(text=text, changes=changes)
