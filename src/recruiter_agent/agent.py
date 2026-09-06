"""Recruiter concierge: JD + question in, human-language fit answer out."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    Runner,
    function_tool,
    input_guardrail,
    output_guardrail,
)

from recruiter_agent.config import get_settings
from recruiter_agent.context import (
    all_profile_text,
    format_jd_requirements_brief,
    identity_facts,
    jd_requirements_brief,
    load_stories,
    lookup_sections,
    reset_lookup_query,
    retrieved_context,
    set_lookup_query,
)
from recruiter_agent.errors import MSG_MISSING_PROFILE, error_http_status
from recruiter_agent.model_factory import build_model
from recruiter_agent.schemas import FitAssessment, JdTermFit

_REFUSAL = (
    "I only answer hiring questions about my experience — roles, stack, "
    "companies, and fit for a role. I can't help with general questions or code."
)

_ABUSE_RE = re.compile(
    r"\b("
    r"fuck(?:ing|er|ed)?|shit(?:ty)?|asshole|bitch|cunt|bastard|"
    r"motherfucker|dickhead|slut|whore|"
    r"nigg(?:er|a)|faggot|retard(?:ed)?|"
    r"kill\s+yourself|kys|go\s+die"
    r")\b",
    re.IGNORECASE,
)
_JAILBREAK_RE = re.compile(
    r"("
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions|"
    r"disregard\s+(your|all)\s+(instructions|rules)|"
    r"you\s+are\s+now\s+(dan|jailbroken|unfiltered)|"
    r"\bdan\s+mode\b|"
    r"jailbreak|"
    r"pretend\s+you\s+(have\s+no|are\s+not\s+bound)|"
    r"reveal\s+(your\s+)?(system\s+prompt|hidden\s+instructions)|"
    r"developer\s+mode"
    r")",
    re.IGNORECASE,
)
_HOMEWORK_RE = re.compile(
    r"("
    r"do\s+my\s+homework|"
    r"write\s+(my|an|a)\s+(essay|term\s+paper|lab\s+report)|"
    r"solve\s+(for\s+x|this\s+equation)|"
    r"prove\s+that\b|"
    r"calculus\s+homework|"
    r"help\s+me\s+with\s+my\s+(math|physics|chemistry)\s+(homework|assignment)"
    r")",
    re.IGNORECASE,
)
_RECIPE_RE = re.compile(
    r"("
    r"recipe\s+for\s+(?!success|disaster|hiring).{0,40}"
    r"(cake|pasta|chicken|soup|cookie|bread|pizza)|"
    r"how\s+to\s+cook\b|"
    r"\bingredients\s*:"
    r")",
    re.IGNORECASE,
)
_TRIVIA_RE = re.compile(
    r"("
    r"what(?:'s| is)\s+the\s+capital\s+of|"
    r"who\s+won\s+the\s+(world\s+cup|super\s+bowl|oscar)|"
    r"unrelated\s+trivia"
    r")",
    re.IGNORECASE,
)
_CODE_RE = re.compile(
    r"("
    r"(?:write|give|show|generate|create|provide)\s+(?:me\s+)?"
    r"(?:a\s+|an\s+|some\s+|the\s+)?"
    r"(?:python|javascript|typescript|java|golang|go|rust|c\+\+|sql|bash)?\s*"
    r"(?:code|function|class|script|program|snippet|module)\b|"
    r"(?:write|give|show|generate|create|provide)\s+(?:me\s+)?(?:some\s+)?code\b|"
    r"implement\s+(?:a\s+|an\s+)?(?:function|class|algorithm)|"
    r"debug\s+(?:this|my|the)\s+(?:code|function|script|program)|"
    r"fix\s+(?:this|my)\s+(?:code|bug|function)|"
    r"\bleetcode\b|"
    r"how\s+do\s+i\s+(?:write|code|implement)\s+a\s+|"
    r"write\s+(?:me\s+)?(?:some\s+|a\s+|an\s+)?"
    r"(?:python|javascript|typescript|java|golang|go|rust|c\+\+|sql|bash)\b"
    r")",
    re.IGNORECASE,
)
_MATH_RE = re.compile(
    r"("
    r"what(?:'s|\s+is)\s+\d+\s*[\+\*/x×÷]\s*\d+"
    r"|what(?:'s|\s+is)\s+\d+\s+[\+\-\*/]\s+\d+"
    r"|what(?:'s|\s+is)\s+\d+\s+(?:plus|minus|times|over|divided\s+by)\s+\d+"
    r"|(?:calculate|compute|evaluate)\s+\d+"
    r"|\b\d+\s*[\+\*/x×÷]\s*\d+"
    r"|\b\d+\s+[\+\-\*/]\s+\d+\b"
    r")",
    re.IGNORECASE,
)
_CREATIVE_RE = re.compile(
    r"("
    r"write\s+(me\s+)?(a\s+|an\s+)?(poem|sonnet|haiku|limerick|song|novel|short\s+story)|"
    r"compose\s+a\s+(poem|song)"
    r")",
    re.IGNORECASE,
)
_NEWS_RE = re.compile(
    r"("
    r"what(?:'s| is)\s+the\s+(latest\s+)?news|"
    r"today'?s\s+news|"
    r"current\s+events\b"
    r")",
    re.IGNORECASE,
)

_cached_agent: Any = None
_cached_model_name: str | None = None

_ANALYST_INSTRUCTIONS = """\
You assess a job description against my profile (Vasu Bansal). Write in first person.
Use lookup_profile with a narrow topic for each named JD requirement (not "everything").
Fill jd_terms for every concrete JD phrase (languages, frameworks, infra, years, domain, location).
Each jd_terms item: phrase = the JD's wording; status = match | partial | not_listed;
note = a first-person profile fact or "I don't list that."
matching_skills must reuse JD phrases and tie them to a retrieved employer or story.
gaps must reuse the JD's wording for anything not listed.
Use only facts present in the tool results or in the text you were given.
Never invent employers, titles, years-on-a-skill, certs, team lead, SLAs, metrics, or dates.
If a tech is listed without a year count, say I've used it — do not invent "N years of X".
If overall years are retrieved, use that figure — not a fake per-skill year.
Return a FitAssessment only.
"""

_CONCIERGE_PREFIX = """\
You are Vasu Bansal. Answer recruiters in first person ("I've…", "I have…"). Never "Vasu Bansal has…".
Facts come only from lookup_profile / assess_fit (profile/*.md). Do not invent a second bio.

How to retrieve:
- Call lookup_profile with a topic from the question (a tech, a company, "companies", "years", "experience", "location", "remote", "hours", "saturday", "education", "skills", "contact", "schedule", "salary", "resume", or "overview").
- Years / how long / total experience: lookup "years". Use the retrieved year figure. Do not invent a more precise number or a per-skill year count.
- Companies / list of companies / where I have worked: lookup "companies".
- Meeting / interview / schedule / call / book / calendar / contact / reach / intro: lookup "contact" or "schedule".
- Never pass "everything" or the full JD as the topic. Never use the filler word "about" as the topic.
- Quote or paraphrase only retrieved sections that match the question.

How to answer:
- First person.
- Lead with the answer. 2–5 sentences unless they asked for a full pitch or overview.
- Companies / employers / where I worked: list retrieved employers in one short sentence. IIT Kanpur is education, not an employer — mention it only if they ask school, or label it as education.
- Years of experience / how long: use the retrieved overall years. Do not calculate a different number from dates.
- A short pitch is OK when they asked for an overview ("tell me about you").
- Meeting / interview / intro call / schedule / book / reach me: always offer all three as Markdown labeled links only — [email](mailto:vasubansal1998@gmail.com), [LinkedIn](https://www.linkedin.com/in/vasub-iitk/), and [book a Google Meet](https://calendar.app.google/BXzB9rtHZ8mZFWbD9). Do not paste https://… as visible text. The URL belongs only inside the Markdown parentheses. Do not also write the raw URL after the label. The chat widget turns [label](url) into a clickable label. That booking page creates a Meet link. Do not invent a meet.google.com URL. These are listed — never say they are missing or "not in the profile."
- Salary / CTC / compensation: I do not list a range. Say that in first person, offer to discuss on a call, and include [book a Google Meet](https://calendar.app.google/BXzB9rtHZ8mZFWbD9). Do not invent a number.
- Notice period, visa, lead teams, soft-skill ratings, certifications, SLA / dollar impact, team size: "I don't list that here." Point to [email](mailto:vasubansal1998@gmail.com) or [book a Google Meet](https://calendar.app.google/BXzB9rtHZ8mZFWbD9) when useful.
- Never invent employers, titles, years, metrics, SLAs, team sizes, dates, impact numbers, or preferences.
- Preferences: only state facts in the retrieved slice. Never invent visa, notice, salary, culture, travel, timezones, Sunday, on-call, or overtime. If a preference is not in the retrieved text: "I don't list that here."
- Remote / hybrid: lookup "remote". I am open to remote and hybrid WFO. Do not mention Saturday unless they asked about hours or Saturday.
- Location / where based: lookup "location". Bangalore; I prefer Bangalore.
- Hours / Saturday: lookup "hours" or "saturday". I do not work Saturdays. A 5-day week works. Do not add Sunday, on-call, or overtime.
- Do not say "the profile does not specify" or "it is not in the profile."
- Off-topic (math, code, poems, homework, news, jailbreaks): do not answer them. Say you only answer hiring questions about your experience. That is a hiring-only refuse — not "I don't list that here."

When a JOB DESCRIPTION is present:
- For fit / why-hire / mapping / strengths / gaps: you MUST call assess_fit before answering.
- Lead with mapped JD requirements, not a generic bio. Quote or reuse the JD's wording.
- For each relevant JD term: match / partial / not listed, using only retrieved profile facts.
- Honest gaps: "Your JD mentions [X]; I don't list that."
- Years on a skill: use retrieved overall years. If a tech is listed without a year count, say I've used it. Never invent a year number.
- Narrow FAQ with a JD also pasted (contact, salary, companies, years, education): answer the FAQ; do not dump a full fit pitch.

When there is no JOB DESCRIPTION:
- Current Q&A. Do not force a fit pitch or mention every stack token.

When to use assess_fit:
- Whenever a JOB DESCRIPTION is present and they ask about fit, mapping, strengths/gaps, or why hire.
- For a standalone factual question with no JD (location, companies, years, a technology), do not call assess_fit.

Question types (lookup the topic; use retrieved text only):
- Current role / companies / years / education / stack / location / remote: lookup, then answer from retrieved facts.
- Leadership / soft skills / culture: honest unknown unless retrieved. Project-lead on a migration is not "I lead teams."
- Learning new tech / AI: use retrieved preferences.
- Hard / named project / impact: retrieved stories only — no fake metrics.
- Code / GitHub / resume PDF: labeled Markdown links from contact — no bare URLs.
- FT vs contract / notice / visa / relocate / timezone / culture: "I don't list that here" plus labeled email/calendar links if useful.
- Contact / schedule interview: [email](mailto:…), [LinkedIn](https://…), [book a Google Meet](https://…) — do not paste https://… as visible text.
- Salary: graceful, no range, offer a call + labeled booking link.
- Tech/org / fit / gaps: map to retrieved profile.
- Overview / "tell me about you": a short pitch is OK.

Identity (not exhaustive — look up more):

"""

_CONCIERGE_SUFFIX = """

Answer the last question only. Do not add a generic fit pitch after a factual answer.
"""

_JD_CONCIERGE_BLOCK = """
A JOB DESCRIPTION is in this turn. You MUST call assess_fit for fit/why-hire questions.
Lead with the mapped JD requirements below — quote their wording. Not a generic bio.
"""

_STRICT_RETRY = """

STRICT RETRY — your previous reply invented facts that are not in the profile.
Answer in first person with retrieved profile facts only.
If a hiring detail is missing: "I don't list that here. Email me if you need it."
Never invent employers, titles, years, metrics, SLAs, team sizes, dates, impact numbers, or preferences.
"""

_FAMOUS_ORGS = frozenset(
    {
        "google",
        "amazon",
        "meta",
        "facebook",
        "microsoft",
        "netflix",
        "uber",
        "stripe",
        "airbnb",
        "apple",
        "tesla",
        "openai",
        "anthropic",
        "spotify",
        "twitter",
        "salesforce",
        "oracle",
        "ibm",
        "intel",
        "nvidia",
        "snowflake",
        "databricks",
        "cloudflare",
    }
)

_METRIC_RE = re.compile(
    r"("
    r"\b\d+(?:\.\d+)?\s*%|"
    r"\$\s*\d[\d,]*(?:\.\d+)?|"
    r"\b\d+\s*(?:ms|million|billion|engineers?|people|members)\b|"
    r"\bteam of \d+"
    r")",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r"\b(staff engineer|principal engineer|distinguished engineer|"
    r"cto|vice president|\bvp\b|director of|fellow)\b",
    re.IGNORECASE,
)


class AgentNotConfiguredError(Exception):
    """Raised when answer_question is called without a usable model/key."""


class AgentRunError(Exception):
    """Raised when the model/run fails after being configured."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def is_ready() -> bool:
    """True when settings.is_configured."""
    return get_settings().is_configured


@function_tool
def lookup_profile(topic: str) -> str:
    """Retrieve stories and sliced profile sections. Use a topic such as a tech, an org, "companies", "years", "experience", "location", "remote", "hours", "saturday", "education", "skills", "contact", "schedule", "salary", "resume", or "overview". The bound JD is also scanned for those techs so matching stories/skills are retrieved. Do not invent preferences or facts. Do not pass "about" as the topic."""
    return lookup_sections(topic)


def _input_as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return str(value)
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
            continue
        if isinstance(item, dict):
            content = item.get("content", item.get("text", ""))
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        parts.append(str(block.get("text") or block.get("content") or ""))
                    else:
                        parts.append(str(block))
            continue
        content = getattr(item, "content", None)
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.append(str(item))
    return "\n".join(p for p in parts if p)


def _question_portion(text: str) -> str:
    marker = "RECRUITER QUESTION:"
    idx = text.upper().find(marker)
    if idx == -1:
        return text
    return text[idx + len(marker) :]


def _guardrail_reason(text: str) -> str | None:
    if _ABUSE_RE.search(text) or _JAILBREAK_RE.search(text):
        return "abuse_or_jailbreak"
    question = _question_portion(text)
    if (
        _HOMEWORK_RE.search(question)
        or _RECIPE_RE.search(question)
        or _TRIVIA_RE.search(question)
        or _CODE_RE.search(question)
        or _MATH_RE.search(question)
        or _CREATIVE_RE.search(question)
        or _NEWS_RE.search(question)
    ):
        return "off_topic"
    return None


async def _recruiter_input_guardrail(
    ctx: Any, agent: Any, input: Any
) -> GuardrailFunctionOutput:
    reason = _guardrail_reason(_input_as_text(input))
    return GuardrailFunctionOutput(
        output_info=reason,
        tripwire_triggered=reason is not None,
    )


recruiter_input_guardrail = input_guardrail(run_in_parallel=False)(
    _recruiter_input_guardrail
)


def _format_jd_term(item: JdTermFit | str) -> str:
    if isinstance(item, str):
        return item
    note = (item.note or "").strip()
    if note:
        return f"{item.phrase} — {item.status}: {note}"
    return f"{item.phrase} — {item.status}"


def _format_assessment(assessment: FitAssessment) -> str:
    lines = [assessment.overall.strip()]
    if assessment.jd_terms:
        lines.append(
            "JD terms: " + "; ".join(_format_jd_term(t) for t in assessment.jd_terms)
        )
    if assessment.matching_skills:
        lines.append("Matching skills: " + "; ".join(assessment.matching_skills))
    if assessment.gaps:
        lines.append("Gaps: " + "; ".join(assessment.gaps))
    if assessment.pitch_points:
        lines.append("Pitch points: " + "; ".join(assessment.pitch_points))
    return "\n".join(lines)


def _final_output_as_str(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, FitAssessment):
        return _format_assessment(output)
    return str(output)


async def _extract_fit_output(run_result: Any) -> str:
    return _final_output_as_str(getattr(run_result, "final_output", run_result))


def _concierge_instructions(context: Any, agent: Any) -> str:
    brief = jd_requirements_brief()
    jd_block = f"{_JD_CONCIERGE_BLOCK}{brief}\n" if brief else ""
    return _CONCIERGE_PREFIX + jd_block + identity_facts() + _CONCIERGE_SUFFIX


def _allowed_fact_text() -> str:
    parts = [retrieved_context(), all_profile_text()]
    for story in load_stories():
        parts.append(story.render())
    return "\n".join(p for p in parts if p)


def _invented_facts(answer: str) -> bool:
    allowed = _allowed_fact_text().lower()
    blob = answer.lower()
    for org in _FAMOUS_ORGS:
        if re.search(rf"\b{re.escape(org)}\b", blob) and org not in allowed:
            return True
    for match in _TITLE_RE.finditer(answer):
        if match.group(0).lower() not in allowed:
            return True
    for match in _METRIC_RE.finditer(answer):
        snippet = match.group(0).lower()
        if snippet in allowed:
            continue
        nums = re.findall(r"\d+(?:\.\d+)?", snippet)
        if nums and all(n in allowed for n in nums):
            continue
        return True
    return False


def _output_guardrail_reason(answer: str) -> str | None:
    if not answer.strip():
        return "empty"
    if _invented_facts(answer):
        return "invented_facts"
    return None


async def _recruiter_output_guardrail(
    ctx: Any, agent: Any, output: Any
) -> GuardrailFunctionOutput:
    text = _final_output_as_str(output)
    reason = _output_guardrail_reason(text)
    return GuardrailFunctionOutput(
        output_info=reason,
        tripwire_triggered=reason is not None,
    )


recruiter_output_guardrail = output_guardrail(name="recruiter_specificity")(
    _recruiter_output_guardrail
)


def _build_concierge(settings) -> Any:
    model = build_model(settings)
    fit_analyst = Agent(
        name="fit_analyst",
        instructions=_ANALYST_INSTRUCTIONS,
        model=model,
        output_type=FitAssessment,
        tools=[lookup_profile],
    )
    analyze_kwargs = {
        "tool_name": "assess_fit",
        "tool_description": (
            "Assess a pasted JD against the profile. Call whenever a JOB DESCRIPTION "
            "is present and the question is about fit, mapping, strengths, or gaps. "
            "Map each JD phrase to match / partial / not_listed. Do not invent."
        ),
    }
    assess_fit = fit_analyst.as_tool(
        **analyze_kwargs,
        custom_output_extractor=_extract_fit_output,
    )
    return Agent(
        name="recruiter_concierge",
        instructions=_concierge_instructions,
        model=model,
        tools=[lookup_profile, assess_fit],
        input_guardrails=[recruiter_input_guardrail],
        output_guardrails=[recruiter_output_guardrail],
    )


def get_agent():
    """Build/cache the concierge Agent with current settings model."""
    global _cached_agent, _cached_model_name
    settings = get_settings()
    if _cached_agent is None or _cached_model_name != settings.agent_model:
        _cached_agent = _build_concierge(settings)
        _cached_model_name = settings.agent_model
    return _cached_agent


_NOT_CONFIGURED = (
    "No usable model/key. Set GEMINI_API_KEY, ANTHROPIC_API_KEY, or "
    "OPENAI_API_KEY, or use an ollama/ AGENT_MODEL for local dev."
)

_TEXT_DELTA_TYPES = frozenset(
    {
        "response.output_text.delta",
        "response.text.delta",
        "output_text.delta",
    }
)
_TOOL_EVENT_NAMES = frozenset(
    {
        "tool_called",
        "tool_output",
        "tool_search_called",
        "tool_search_output_created",
    }
)
_TOOL_ITEM_TYPES = frozenset({"tool_call_item", "tool_call_output_item"})


def _user_text(jd: str, question: str) -> str:
    if not jd:
        return question
    brief = format_jd_requirements_brief(jd)
    parts = [f"JOB DESCRIPTION:\n{jd}"]
    if brief:
        parts.append(brief)
    parts.append(f"RECRUITER QUESTION:\n{question}")
    return "\n\n".join(parts)


def _require_ready() -> None:
    if not is_ready():
        raise AgentNotConfiguredError(_NOT_CONFIGURED)


def _guardrail_trip_reason(exc: OutputGuardrailTripwireTriggered) -> str:
    info = getattr(getattr(exc, "guardrail_result", None), "output", None)
    return getattr(info, "output_info", None) or "generic_pitch"


def _wrap_run_error(exc: Exception) -> AgentRunError:
    return AgentRunError(
        f"{type(exc).__name__}: {exc}",
        status_code=error_http_status(exc, status=getattr(exc, "status_code", None)),
    )


def _is_tool_boundary(event: Any) -> bool:
    name = getattr(event, "name", None)
    if name in _TOOL_EVENT_NAMES:
        return True
    item = getattr(event, "item", None)
    return getattr(item, "type", None) in _TOOL_ITEM_TYPES


def _assistant_text_delta(event: Any) -> str | None:
    """Assistant token text only — skip tools, guardrails, and LiteLLM internals."""
    ev_type = getattr(event, "type", None)
    data: Any
    if ev_type == "raw_response_event":
        data = getattr(event, "data", None)
    elif ev_type in _TEXT_DELTA_TYPES:
        data = event
    else:
        return None
    if data is None:
        return None
    if isinstance(data, dict):
        dtype = data.get("type")
        delta = data.get("delta", data.get("text"))
    else:
        dtype = getattr(data, "type", ev_type)
        delta = getattr(data, "delta", None)
        if delta is None:
            delta = getattr(data, "text", None)
    if dtype not in _TEXT_DELTA_TYPES:
        return None
    if not isinstance(delta, str) or not delta:
        return None
    return delta


def _looks_like_internal_json(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


async def _stream_once(user_text: str) -> AsyncIterator[str]:
    result = Runner.run_streamed(get_agent(), user_text)
    displayed = ""
    async for event in result.stream_events():
        if _is_tool_boundary(event):
            displayed = ""
            continue
        delta = _assistant_text_delta(event)
        if not delta:
            continue
        displayed += delta
        if displayed.strip() and not _looks_like_internal_json(displayed):
            yield displayed
    final = _final_output_as_str(getattr(result, "final_output", None))
    if final:
        yield final


async def _run_once(user_text: str) -> Any:
    return await Runner.run(get_agent(), user_text)


async def stream_answer(jd: str, question: str) -> AsyncIterator[str]:
    """
    Yield growing assistant text, then the final sanitized answer.

    Live tokens come from `response.output_text.delta` only. Tool JSON, guardrail
    internals, and LiteLLM noise are skipped. After the run (and any specificity
    retry), the last yield is the same guarded string `answer_question` would
    return. Never yields `str(exception)`.
    """
    _require_ready()
    user_text = _user_text(jd, question)
    if _guardrail_reason(user_text):
        yield _REFUSAL
        return

    token = set_lookup_query(jd, question)
    try:
        try:
            async for chunk in _stream_once(user_text):
                yield chunk
        except OutputGuardrailTripwireTriggered as trip:
            reason = _guardrail_trip_reason(trip)
            try:
                async for chunk in _stream_once(
                    user_text + _STRICT_RETRY + f"\nIssue: {reason}\n"
                ):
                    yield chunk
            except OutputGuardrailTripwireTriggered:
                yield MSG_MISSING_PROFILE
    except InputGuardrailTripwireTriggered:
        yield _REFUSAL
    except AgentNotConfiguredError:
        raise
    except Exception as exc:
        raise _wrap_run_error(exc) from exc
    finally:
        reset_lookup_query(token)


async def answer_question(jd: str, question: str) -> str:
    """
    Run recruiter_concierge.
    - If not is_ready(): raise AgentNotConfiguredError
    - Build user text: if jd: "JOB DESCRIPTION:\\n{jd}\\n\\nRECRUITER QUESTION:\\n{question}" else question
    - If input guardrail trips: return a short refusal string (do NOT raise)
    - On model/SDK failure: raise AgentRunError
    - Return final_output as a string (if FitAssessment sneaks through, format it as prose)
    """
    _require_ready()
    user_text = _user_text(jd, question)
    if _guardrail_reason(user_text):
        return _REFUSAL

    token = set_lookup_query(jd, question)
    try:
        try:
            result = await _run_once(user_text)
        except OutputGuardrailTripwireTriggered as trip:
            reason = _guardrail_trip_reason(trip)
            try:
                result = await _run_once(
                    user_text + _STRICT_RETRY + f"\nIssue: {reason}\n"
                )
            except OutputGuardrailTripwireTriggered:
                return MSG_MISSING_PROFILE
    except InputGuardrailTripwireTriggered:
        return _REFUSAL
    except AgentNotConfiguredError:
        raise
    except Exception as exc:
        raise _wrap_run_error(exc) from exc
    finally:
        reset_lookup_query(token)

    return _final_output_as_str(getattr(result, "final_output", result))
