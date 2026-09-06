"""LiteLLM model construction for the OpenAI Agents SDK."""

from __future__ import annotations

import os

from agents.extensions.models.litellm_model import LitellmModel


def build_model(settings):
    if str(settings.agent_model).lower().startswith("ollama/"):
        os.environ["OLLAMA_API_BASE"] = settings.ollama_api_base
    return LitellmModel(model=settings.agent_model, api_key=settings.api_key_for_model)
