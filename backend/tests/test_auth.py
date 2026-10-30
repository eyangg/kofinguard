from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import auth
import db
import seed
from main import app
from models import Customer

TEST_SECRET = "test-secret-" + "x" * 32


@pytest.fixture
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("KFG_SESSION_SECRET", TEST_SECRET)
    with Session(engine) as s:
        seed.seed(s)
    auth.sessions.clear()
    with TestClient(app) as c:
        yield c
    auth.sessions.clear()


def login(c: TestClient, login_id: str = "minsu", password: str = seed.DEMO_PASSWORD):  # type: ignore[no-untyped-def]
    return c.post("/api/auth/login", json={"login_id": login_id, "password": password})


def test_login_success_sets_httponly_cookie(client: TestClient) -> None:
    res = login(client)
    assert res.status_code == 200
    assert res.json()["name"] == "김민수"
    set_cookie = res.headers["set-cookie"].lower()
    assert auth.COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == {
        "id": "C-1001",
        "login_id": "minsu",
        "name": "김민수",
        "email": "minsu@example.com",
        "phone": "010-0000-1001",
    }


def test_response_has_no_password_hash(client: TestClient) -> None:
    body = login(client).text + client.get("/api/me").text
    assert "pbkdf2" not in body
    assert "password" not in body


def test_wrong_password_is_401(client: TestClient) -> None:
    res = login(client, password="wrong-password")
    assert res.status_code == 401
    assert res.json()["detail"] == auth.LOGIN_FAILED
    assert auth.COOKIE_NAME not in res.headers.get("set-cookie", "")


def test_unknown_user_is_401_with_same_message(client: TestClient) -> None:
    res = login(client, login_id="nobody")
    assert res.status_code == 401
    assert res.json()["detail"] == auth.LOGIN_FAILED


def test_me_without_login_is_401(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401


def test_tampered_cookie_is_401(client: TestClient) -> None:
    login(client)
    value = client.cookies[auth.COOKIE_NAME]
    sid, _, sig = value.rpartition(".")
    client.cookies.set(auth.COOKIE_NAME, f"{sid}.{'0' * len(sig)}")
    assert client.get("/api/me").status_code == 401


def test_cookie_signed_with_other_secret_is_401(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    monkeypatch.setenv("KFG_SESSION_SECRET", "another-secret-" + "y" * 32)
    assert client.get("/api/me").status_code == 401


def test_old_cookie_after_logout_is_401(client: TestClient) -> None:
    login(client)
    old = client.cookies[auth.COOKIE_NAME]
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set(auth.COOKIE_NAME, old)  # 로그아웃 전 쿠키를 다시 보내 본다
    assert client.get("/api/me").status_code == 401


def test_logout_when_already_logged_out_is_ok(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200


def test_relogin_replaces_old_session(client: TestClient) -> None:
    login(client)
    first = client.cookies[auth.COOKIE_NAME]
    login(client, "seoyeon")
    assert client.get("/api/me").json()["id"] == "C-1002"
    client.cookies.set(auth.COOKIE_NAME, first)
    assert client.get("/api/me").status_code == 401


def test_expired_session_is_401(client: TestClient) -> None:
    login(client)
    sid = auth.read_cookie_value(client.cookies[auth.COOKIE_NAME])
    assert sid is not None
    auth.sessions._items[sid].expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert client.get("/api/me").status_code == 401


def test_db_has_no_plaintext_password(client: TestClient, engine: Engine) -> None:
    with Session(engine) as s:
        for c in s.scalars(select(Customer)):
            assert seed.DEMO_PASSWORD not in c.password_hash


def test_server_does_not_start_without_session_secret(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KFG_SESSION_SECRET", raising=False)
    monkeypatch.setattr(db, "load_env", lambda: None)  # backend/.env를 읽지 않게 한다
    with pytest.raises(auth.SessionConfigError):
        with TestClient(app):
            pass
