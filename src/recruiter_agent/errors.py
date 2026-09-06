"""Map failures to recruiter-safe one-liners. Raw detail stays in logs."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MSG_BUSY = "I'm getting a lot of questions right now. Please try again in a minute."
MSG_UNAVAILABLE = "Chat isn't available at the moment. Email is best."
MSG_RETRY = "I couldn't complete that just now. Please try again."
MSG_UNKNOWN = "Something went wrong. Please try again or email."
MSG_MISSING_PROFILE = "I don't list that here. Email me if you need it."

MSG_QUESTION_REQUIRED = "Please ask a question."
MSG_QUESTION_TOO_LONG = "That question is too long."
MSG_JD_TOO_LONG = "That job description is too long."

_BUSY = (
    "429",
    "ratelimit",
    "rate_limit",
    "rate limit",
    "quota",
    "resource_exhausted",
    "resource exhausted",
    "too many requests",
)
_UNAVAILABLE = (
    "503",
    "not configured",
    "api_key",
    "api key",
    "apikey",
    "missing key",
    "no usable model",
    "authenticationerror",
    "authentication error",
    "unauthorized",
)
_RETRY = (
    "502",
    "timeout",
    "timed out",
    "litellm",
    "bad gateway",
    "service unavailable",
    "connection error",
    "connecterror",
    "apierror",
    "internalservererror",
)


def _exc_blob(exc: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(type(current).__name__)
        parts.append(str(current))
        current = current.__cause__ or current.__context__
    return " ".join(parts).lower()


def _looks_like(blob: str, needles: tuple[str, ...]) -> bool:
    return any(n in blob for n in needles)


def classify_error(
    exc: BaseException | None = None, *, status: int | None = None
) -> int:
    """Return 429, 503, 502, or 0 (unknown). Uses status + exception text for routing only."""
    blob = _exc_blob(exc) if exc is not None else ""
    name = type(exc).__name__ if exc is not None else ""

    if name == "AgentNotConfiguredError" or status == 503:
        if _looks_like(blob, _BUSY):
            return 429
        return 503
    if status == 429 or _looks_like(blob, _BUSY):
        return 429
    if _looks_like(blob, _UNAVAILABLE):
        return 503
    if status == 502 or name == "AgentRunError" or _looks_like(blob, _RETRY):
        return 502
    return 0


def error_http_status(
    exc: BaseException | None = None, *, status: int | None = None
) -> int:
    code = classify_error(exc, status=status)
    return code if code in (429, 502, 503) else 502


def friendly_message(code: int) -> str:
    if code == 429:
        return MSG_BUSY
    if code == 503:
        return MSG_UNAVAILABLE
    if code == 502:
        return MSG_RETRY
    return MSG_UNKNOWN


def friendly_error(
    exc: BaseException | None = None,
    *,
    status: int | None = None,
    log: bool = True,
) -> str:
    """Log the real failure; return one short line for Gradio / JSON `error`."""
    if log and exc is not None:
        logger.exception("recruiter chat failed", exc_info=exc)
    if status is None and exc is not None:
        status = getattr(exc, "status_code", None)
    return friendly_message(error_http_status(exc, status=status))
