"""비밀번호 해시 (표준 라이브러리 PBKDF2). DB에는 원문을 저장하지 않는다."""

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        rounds = int(iterations)
    except ValueError:
        return False
    if algorithm != ALGORITHM:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), rounds)
    return hmac.compare_digest(digest.hex(), expected)
