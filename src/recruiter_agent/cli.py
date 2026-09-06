"""CLI: python -m recruiter_agent.cli --question 'Why a fit?' [--jd '...']"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recruiter-agent",
        description="Ask the recruiter agent a question about Vasu Bansal.",
    )
    parser.add_argument("--jd", default="", help="Job description (optional)")
    parser.add_argument(
        "-q",
        "--question",
        default=None,
        help="Recruiter question. Required unless a question is piped on stdin.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override AGENT_MODEL for this run (e.g. gemini/gemini-2.0-flash).",
    )
    return parser


def _read_question(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.question is not None:
        question = str(args.question).strip()
    elif not sys.stdin.isatty():
        question = sys.stdin.read().strip()
    else:
        parser.error("--question/-q is required unless you pipe a question on stdin")
    if not question:
        print("error: question required", file=sys.stderr)
        raise SystemExit(2)
    return question


def _apply_model_override(model: str) -> None:
    os.environ["AGENT_MODEL"] = model
    from recruiter_agent.config import reload_settings

    reload_settings()


def _not_configured() -> None:
    print(
        "Not configured. Copy .env.example to .env and set GEMINI_API_KEY "
        "(or ANTHROPIC_API_KEY / OPENAI_API_KEY). For local models, "
        "set AGENT_MODEL=ollama/<name>.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _ensure_configured() -> None:
    from recruiter_agent.agent import is_ready

    if not is_ready():
        _not_configured()


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.model:
        _apply_model_override(args.model)
    question = _read_question(args, parser)
    _ensure_configured()

    from recruiter_agent.agent import (
        AgentNotConfiguredError,
        AgentRunError,
        answer_question,
    )

    try:
        answer = asyncio.run(answer_question(args.jd or "", question))
    except AgentNotConfiguredError:
        print(
            "Not configured. Copy .env.example to .env and set an API key.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    except AgentRunError:
        print("model failed", file=sys.stderr)
        raise SystemExit(1) from None

    print(answer)


if __name__ == "__main__":
    main()
