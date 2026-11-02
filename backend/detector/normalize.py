"""D-01 문장 정리 (보조 레이어).

졸프 이식: capstone_ref/SmoothPPL_Qwen_졸프코드추정.ipynb 셀 3 — normalize_korean, is_jamo_heavy (원본 그대로).

졸프 원본은 NFC 정규화만 한다.
- 첫가끝 자모(U+1100대, PDF 추출 등에서 생기는 분해된 한글)는 완성형으로 합쳐진다.
- 키보드 자모(ㄱ, ㅏ 같은 U+3130대)는 합치지 않는다. 졸프 주석('ㅍㅗㄱㅌㅏㄴ → 폭탄')과 실제 동작이 다르다.
나중에 진짜 졸프 전처리(또는 자모 결합 모델)로 바꿀 때는 normalize()만 교체한다.
"""

import unicodedata

JAMO_HEAVY_THRESHOLD = 0.2  # 졸프 Qwen 노트북 값


def normalize_korean(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def is_jamo_heavy(text: str, threshold: float = JAMO_HEAVY_THRESHOLD) -> bool:
    """키보드 자모 비율이 threshold를 넘으면 True (기록용. 이것만으로 막지 않는다)."""
    jamo_chars = [c for c in text if "㄰" <= c <= "㆏"]
    if len(text) == 0:
        return False
    return len(jamo_chars) / len(text) > threshold


# 파이프라인이 부르는 이름. 교체할 때 여기만 바꾼다.
normalize = normalize_korean
