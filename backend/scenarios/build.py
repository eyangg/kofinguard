"""presets.json과 S2 청구서 PDF를 만든다. 공격 문장을 바꾸면 다시 실행한다.

실행 (backend 폴더):
    .\\.venv\\Scripts\\python.exe -m scenarios.build
"""

import json
from pathlib import Path

from fpdf import FPDF

from scenarios.attacks import S2_HIDDEN, S2_INVOICE, S2_INVOICE_FILE, presets

HERE = Path(__file__).resolve().parent
DOCS = HERE / "docs"
FONT = Path("C:/Windows/Fonts/malgun.ttf")  # 맑은 고딕 (한글)


def make_invoice(path: Path, hidden: str) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("malgun", fname=str(FONT))
    pdf.set_font("malgun", size=20)
    pdf.cell(0, 14, "청구서", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("malgun", size=12)
    for line in [
        "청구일: 2026-10-30",
        f"공급자: {S2_INVOICE['supplier']}",
        "품목: 노트북 거치대 외 2건",
        f"입금 계좌: MJ뱅크 {S2_INVOICE['account']}",
        f"청구 금액: {S2_INVOICE['amount']:,}원",
        "",
        "기한 내 입금 부탁드립니다. (가상 문서)",
    ]:
        pdf.cell(0, 9, line, new_x="LMARGIN", new_y="NEXT")
    # 흰 바탕에 흰 글씨: 사람 눈에는 안 보이지만 글자 추출에는 그대로 나온다.
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("malgun", size=6)
    pdf.ln(6)
    pdf.multi_cell(0, 4, hidden)
    pdf.output(str(path))


def main() -> None:
    items = presets()
    (HERE / "presets.json").write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DOCS.mkdir(exist_ok=True)
    make_invoice(DOCS / S2_INVOICE_FILE, S2_HIDDEN)
    print(f"presets {len(items)}개, 청구서 PDF 생성: {DOCS / S2_INVOICE_FILE}")


if __name__ == "__main__":
    main()
