"""졸프 한국어 탈옥 탐지 파이프라인 (보조 레이어, spec 4.1 D-01~D-04).

부품별로 나눠 두었다. 졸프 원본 파일을 새로 찾으면 해당 부품만 바꿔 끼운다.
- normalize.py : D-01 문장 정리
- smoothppl.py : D-02 SmoothPPL 점수
- guard.py     : D-03 Llama Guard 위험 판정
- router.py    : D-01~D-04를 묶어 통과 / 차단 / 다시 묻기 결정
"""
