"""문서 첨부 (spec 3.5): 파일은 backend/uploads/, 정보는 attachments 테이블.

PDF는 글자를 그대로 추출한다. 흰 글씨처럼 화면에 안 보이는 글자도 추출되는데,
실제 사례(2026년 7월 유럽 은행 챗봇)의 공격 경로가 바로 이것이다.
"""

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from auth import CurrentUser, DbSession
from models import Attachment

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
MAX_BYTES = 1024 * 1024
UNSUPPORTED = "지원하지 않는 파일입니다"
CONTENT_TYPES = {".pdf": "application/pdf", ".txt": "text/plain"}


class AttachmentError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class AttachmentInfo(BaseModel):
    id: int
    filename: str
    size: int
    content_type: str


def extract_text(data: bytes, suffix: str) -> str:
    if suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except PdfReadError:
            raise AttachmentError(UNSUPPORTED) from None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    raise AttachmentError(UNSUPPORTED)


def _validate(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in CONTENT_TYPES or not data or len(data) > MAX_BYTES:
        raise AttachmentError(UNSUPPORTED)
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise AttachmentError(UNSUPPORTED)
    extract_text(data, suffix)  # 읽을 수 없는 파일은 저장하지 않는다
    return suffix


def save_attachment(db: DbSession, customer_id: str, filename: str, data: bytes) -> Attachment:
    suffix = _validate(filename, data)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"  # 사용자가 준 파일명은 경로에 쓰지 않는다
    path.write_bytes(data)
    attachment = Attachment(
        customer_id=customer_id,
        filename=Path(filename).name[:255],
        path=path.name,
        size=len(data),
        content_type=CONTENT_TYPES[suffix],
    )
    db.add(attachment)
    db.commit()
    return attachment


def load_attachment_text(db: DbSession, customer_id: str, attachment_id: int) -> tuple[Attachment, str]:
    """올린 본인만 쓸 수 있다. 남의 첨부는 있는지조차 알려 주지 않는다."""
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.customer_id != customer_id:
        raise AttachmentError("첨부 파일을 찾을 수 없습니다", 404)
    data = (UPLOAD_DIR / attachment.path).read_bytes()
    return attachment, extract_text(data, Path(attachment.path).suffix)


router = APIRouter(prefix="/api", tags=["attachments"])


@router.post("/attachments")
async def upload_attachment(file: UploadFile, user: CurrentUser, db: DbSession) -> AttachmentInfo:
    data = await file.read(MAX_BYTES + 1)
    try:
        a = save_attachment(db, user.id, file.filename or "", data)
    except AttachmentError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.message) from None
    return AttachmentInfo(id=a.id, filename=a.filename, size=a.size, content_type=a.content_type)
