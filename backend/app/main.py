"""FastAPI application. In the final build it also serves the compiled React app,
so one process on http://localhost:8000 is the whole planner."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST
from .db import init_db
from .routers import auth, checkins, commitments, data, evaluation, insights, models_info, preferences, schedules, simulate, tasks



@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Circadia: Energy-Aware Life Planner", version="0.1.0", lifespan=lifespan)
app.add_middleware(  # only used in development, when Vite runs on port 5173
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

for r in (auth, tasks, commitments, checkins, preferences, schedules, models_info, data, insights, simulate, evaluation):
    app.include_router(r.router)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "ERROR", "message": str(exc.detail)}
    return JSONResponse(detail, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(x) for x in first.get("loc", [])[1:])
    msg = str(first.get("msg", "Invalid input")).removeprefix("Value error, ")
    return JSONResponse({"code": "INVALID", "message": msg, "field": field or None}, status_code=422)


@app.get("/api/health")
def health():
    return {"ok": True}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, {"code": "NOT_FOUND", "message": "Unknown API route."})
        f = FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
