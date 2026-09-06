"""FastAPI proxy matching the blog recruiter-chat worker contract."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import gradio as gr
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from recruiter_agent.agent import answer_question, is_ready, stream_answer
from recruiter_agent.config import (
    MAX_JD_CHARS,
    MAX_QUESTION_CHARS,
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW_S,
    get_settings,
)
from recruiter_agent.errors import (
    MSG_BUSY,
    MSG_JD_TOO_LONG,
    MSG_QUESTION_REQUIRED,
    MSG_QUESTION_TOO_LONG,
    MSG_UNAVAILABLE,
    MSG_UNKNOWN,
    error_http_status,
    friendly_error,
)
from recruiter_agent.schemas import ChatRequest, ChatResponse, ErrorResponse
from recruiter_agent.ui import GRADIO_CSS, GRADIO_HEAD, GRADIO_JS, demo as gradio_demo

app = FastAPI(title="Recruiter agent", version="0.1.0")

_UI_PREFIX = "/ui"
_STATIC_DIR = Path(__file__).resolve().parent / "static"

_hits_by_ip: dict[str, list[float]] = {}


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse(ErrorResponse(error=message).model_dump(), status_code=status)


def _allowed_origins() -> list[str]:
    return get_settings().origins_list


def _cors_headers(origin: str | None) -> dict[str, str]:
    headers = {
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
    }
    allowed = _allowed_origins()
    if origin and origin in allowed:
        headers["Access-Control-Allow-Origin"] = origin
    return headers


def _apply_cors(response: Response, origin: str | None) -> Response:
    for key, value in _cors_headers(origin).items():
        response.headers[key] = value
    return response


def _is_ui_path(path: str) -> bool:
    return path == _UI_PREFIX or path.startswith(f"{_UI_PREFIX}/")


def _is_static_path(path: str) -> bool:
    return path == "/static" or path.startswith("/static/")


def _same_origin(request: Request, origin: str) -> bool:
    host = request.headers.get("host")
    if not host:
        return False
    return origin in {f"http://{host}", f"https://{host}"}


def _origin_ok(request: Request, origin: str | None, path: str) -> bool:
    if path == "/health" or _is_ui_path(path) or _is_static_path(path):
        return True
    if not origin:
        return True
    if origin in _allowed_origins():
        return True
    return _same_origin(request, origin)


def _apply_embed_headers(response: Response) -> Response:
    """Keep /ui embeddable for local tests; the blog widget does not iframe it."""
    if "x-frame-options" in response.headers:
        del response.headers["x-frame-options"]
    ancestors = " ".join(["'self'", *_allowed_origins()])
    frame_directive = f"frame-ancestors {ancestors}"
    existing = response.headers.get("content-security-policy")
    if existing:
        parts = [p.strip() for p in existing.split(";") if p.strip()]
        parts = [p for p in parts if not p.lower().startswith("frame-ancestors")]
        parts.append(frame_directive)
        response.headers["Content-Security-Policy"] = "; ".join(parts)
    else:
        response.headers["Content-Security-Policy"] = frame_directive
    return response


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip and cf_ip.strip():
        return cf_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _hits_by_ip.get(ip, []) if now - t < RATE_LIMIT_WINDOW_S]
    if len(recent) >= RATE_LIMIT_MAX:
        _hits_by_ip[ip] = recent
        return True
    recent.append(now)
    _hits_by_ip[ip] = recent
    return False


@app.middleware("http")
async def cors_and_origin(request: Request, call_next):  # type: ignore[no-untyped-def]
    origin = request.headers.get("origin")
    path = request.url.path
    if not _origin_ok(request, origin, path):
        return _apply_embed_headers(_apply_cors(_error(MSG_UNKNOWN, 403), origin))
    if request.method == "OPTIONS" and not _is_ui_path(path):
        return _apply_embed_headers(_apply_cors(Response(status_code=204), origin))
    response = await call_next(request)
    return _apply_embed_headers(_apply_cors(response, origin))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _parse_chat_request(payload: Any) -> ChatRequest | JSONResponse:
    if not isinstance(payload, dict):
        return _error(MSG_UNKNOWN, 400)
    question = str(payload.get("question") or "").strip()
    jd = str(payload.get("jd") or "").strip()
    body = ChatRequest(jd=jd, question=question)
    if not body.question:
        return _error(MSG_QUESTION_REQUIRED, 400)
    if len(body.question) > MAX_QUESTION_CHARS:
        return _error(MSG_QUESTION_TOO_LONG, 400)
    if len(body.jd) > MAX_JD_CHARS:
        return _error(MSG_JD_TOO_LONG, 400)
    if not is_ready():
        return _error(MSG_UNAVAILABLE, 503)
    return body


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/chat")
async def chat(request: Request) -> JSONResponse:
    try:
        payload: Any = await request.json()
    except Exception:
        return _error(MSG_UNKNOWN, 400)

    body = _parse_chat_request(payload)
    if isinstance(body, JSONResponse):
        return body

    if _rate_limited(_client_ip(request)):
        return _error(MSG_BUSY, 429)

    try:
        answer = await answer_question(body.jd, body.question)
    except Exception as exc:
        return _error(friendly_error(exc), error_http_status(exc))

    return JSONResponse(ChatResponse(answer=answer).model_dump())


@app.post("/chat/stream", response_model=None)
async def chat_stream(request: Request) -> JSONResponse | StreamingResponse:
    try:
        payload: Any = await request.json()
    except Exception:
        return _error(MSG_UNKNOWN, 400)

    body = _parse_chat_request(payload)
    if isinstance(body, JSONResponse):
        return body

    if _rate_limited(_client_ip(request)):
        return _error(MSG_BUSY, 429)

    async def events() -> AsyncIterator[str]:
        try:
            async for text in stream_answer(body.jd, body.question):
                yield _sse({"text": text})
            yield _sse({"done": True})
        except Exception as exc:
            yield _sse({"error": friendly_error(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

gr.mount_gradio_app(
    app,
    gradio_demo,
    path=_UI_PREFIX,
    footer_links=[],
    css=GRADIO_CSS,
    js=GRADIO_JS,
    head=GRADIO_HEAD,
    allowed_paths=[str(_STATIC_DIR)],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=get_settings().port)
