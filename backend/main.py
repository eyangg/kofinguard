"""KoFinGuard 백엔드 (FastAPI).

실행 (backend 폴더에서):
    .\\.venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
"""

from fastapi import FastAPI

app = FastAPI(title="KoFinGuard")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
