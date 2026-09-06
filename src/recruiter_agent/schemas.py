"""Pydantic contracts: structured fit output + HTTP request/response."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JdTermFit(BaseModel):
    """One JD phrase mapped to the profile. Phrase must reuse the JD's wording."""

    phrase: str = Field(
        description="Exact or near-exact wording from the JD (e.g. Kubernetes, 7 years GraphQL)."
    )
    status: Literal["match", "partial", "not_listed"] = Field(
        description="match if the profile lists it; partial if related; not_listed if absent."
    )
    note: str = Field(
        default="",
        description="First-person profile evidence, or I don't list that. No invented years.",
    )


class FitAssessment(BaseModel):
    """Structured JD-vs-profile assessment. Concierge phrases this in human language."""

    overall: str = Field(
        description="One-sentence overall fit (e.g. strong / partial / weak) plus why."
    )
    jd_terms: list[JdTermFit] = Field(
        default_factory=list,
        description="Every concrete JD phrase (lang, framework, infra, years, domain, location).",
    )
    matching_skills: list[str] = Field(
        default_factory=list,
        description="JD phrases that match, tied to a retrieved employer or story. Reuse JD wording.",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="JD phrases not evidenced in the profile. Reuse the JD wording. Do not invent.",
    )
    pitch_points: list[str] = Field(
        default_factory=list,
        description="Recruiter-useful talking points grounded only in listed facts.",
    )


class ChatRequest(BaseModel):
    jd: str = ""
    question: str = ""


class ChatResponse(BaseModel):
    answer: str


class ErrorResponse(BaseModel):
    error: str
