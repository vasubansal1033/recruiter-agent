"""Load profile/*.md and profile/stories/*.md. Tag + keyword retrieval."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path

from recruiter_agent.config import get_settings

_PROFILE_FILES = (
    "profile.md",
    "experience.md",
    "education.md",
    "skills.md",
    "projects.md",
    "preferences.md",
    "contact.md",
)
_INTENTS_FILE = "intents.yaml"

_lookup_query: ContextVar[str] = ContextVar("lookup_query", default="")
_lookup_question: ContextVar[str] = ContextVar("lookup_question", default="")
_retrieved_context: ContextVar[str] = ContextVar("retrieved_context", default="")
_jd_brief: ContextVar[str] = ContextVar("jd_brief", default="")

_cache_key: tuple[tuple[str, int, int], ...] | None = None
_cache_sections: dict[str, str] = {}
_cache_stories: list = []
_cache_intent_aliases: dict[str, tuple[str, ...]] = {}

_TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "profile": ("profile.md",),
    "about": ("profile.md",),
    "bio": ("profile.md",),
    "pitch": ("profile.md",),
    "current role": ("profile.md",),
    "current title": ("profile.md",),
    "title": ("profile.md",),
    "mts": ("profile.md",),
    "mts-3": ("profile.md",),
    "currently": ("profile.md",),
    "right now": ("profile.md",),
    "contact": ("contact.md",),
    "meeting": ("contact.md",),
    "interview": ("contact.md",),
    "schedule": ("contact.md",),
    "call": ("contact.md",),
    "book": ("contact.md",),
    "calendar": ("contact.md",),
    "reach": ("contact.md",),
    "intro": ("contact.md",),
    "github": ("contact.md",),
    "resume": ("contact.md",),
    "cv": ("contact.md",),
    "pdf": ("contact.md",),
    "email": ("contact.md",),
    "linkedin": ("contact.md",),
    "experience": ("experience.md",),
    "work": ("experience.md",),
    "worked": ("experience.md",),
    "role": ("experience.md", "profile.md"),
    "roles": ("experience.md", "preferences.md"),
    "companies": ("experience.md",),
    "company": ("experience.md",),
    "employers": ("experience.md",),
    "employer": ("experience.md",),
    "career": ("experience.md",),
    "history": ("experience.md",),
    "previous": ("experience.md",),
    "industry": ("experience.md", "projects.md"),
    "industries": ("experience.md", "projects.md"),
    "domain": ("experience.md", "projects.md"),
    "years": ("profile.md", "experience.md"),
    "year": ("profile.md",),
    "yoe": ("profile.md",),
    "how long": ("profile.md",),
    "nutanix": ("experience.md", "projects.md"),
    "gojek": ("experience.md", "projects.md"),
    "deloitte": ("experience.md",),
    "education": ("education.md",),
    "degree": ("education.md",),
    "university": ("education.md",),
    "iit": ("education.md",),
    "college": ("education.md",),
    "kanpur": ("education.md",),
    "studied": ("education.md",),
    "alumni": ("education.md",),
    "overview": ("profile.md", "experience.md", "skills.md", "preferences.md"),
    "skills": ("skills.md",),
    "stack": ("skills.md",),
    "tech": ("skills.md",),
    "languages": ("skills.md",),
    "frameworks": ("skills.md",),
    "kubernetes": ("skills.md", "experience.md", "projects.md"),
    "k8s": ("skills.md", "experience.md", "projects.md"),
    "go": ("skills.md", "experience.md"),
    "golang": ("skills.md", "experience.md"),
    "kafka": ("skills.md", "experience.md", "projects.md"),
    "postgres": ("skills.md", "experience.md", "projects.md"),
    "redis": ("skills.md", "experience.md", "projects.md"),
    "helm": ("skills.md", "experience.md", "projects.md"),
    "envoy": ("skills.md", "experience.md", "projects.md"),
    "oidc": ("skills.md", "experience.md", "projects.md"),
    "iam": ("skills.md", "experience.md", "projects.md"),
    "kyc": ("projects.md", "experience.md"),
    "control-plane": ("skills.md", "experience.md", "projects.md"),
    "control plane": ("skills.md", "experience.md", "projects.md"),
    "infra": ("skills.md", "experience.md", "preferences.md"),
    "backend": ("skills.md", "experience.md", "preferences.md"),
    "project": ("projects.md",),
    "projects": ("projects.md",),
    "hardest": ("projects.md",),
    "challenging": ("projects.md",),
    "impact": ("projects.md", "preferences.md"),
    "metrics": ("projects.md", "preferences.md"),
    "sla": ("preferences.md",),
    "preferences": ("preferences.md",),
    "open to": ("preferences.md",),
    "roles wanted": ("preferences.md",),
    "location": ("preferences.md",),
    "based": ("preferences.md",),
    "where": ("preferences.md",),
    "bangalore": ("preferences.md",),
    "bengaluru": ("preferences.md",),
    "india": ("preferences.md",),
    "remote": ("preferences.md",),
    "hybrid": ("preferences.md",),
    "wfo": ("preferences.md",),
    "saturday": ("preferences.md",),
    "weekend": ("preferences.md",),
    "hours": ("preferences.md",),
    "5-day": ("preferences.md",),
    "five-day": ("preferences.md",),
    "work week": ("preferences.md",),
    "relocate": ("preferences.md",),
    "relocation": ("preferences.md",),
    "timezone": ("preferences.md",),
    "geo": ("preferences.md",),
    "culture": ("preferences.md",),
    "leadership": ("preferences.md", "projects.md"),
    "soft skills": ("preferences.md",),
    "learning": ("preferences.md", "profile.md"),
    "notice": ("preferences.md",),
    "compensation": ("preferences.md", "contact.md"),
    "salary": ("preferences.md", "contact.md"),
    "visa": ("preferences.md",),
    "contract": ("preferences.md",),
    "full-time": ("preferences.md",),
    "full time": ("preferences.md",),
    "availability": ("preferences.md", "contact.md"),
    "work history": ("experience.md",),
    "notice period": ("preferences.md",),
}

# Aliases that dump a whole file. Ignored when a specific tech/org is present.
_BROAD_ALIASES = frozenset(
    {
        "profile",
        "about",
        "bio",
        "pitch",
        "contact",
        "experience",
        "work",
        "worked",
        "role",
        "roles",
        "companies",
        "company",
        "employers",
        "employer",
        "career",
        "history",
        "previous",
        "years",
        "year",
        "yoe",
        "how long",
        "overview",
        "skills",
        "stack",
        "tech",
        "languages",
        "education",
        "college",
        "infra",
        "backend",
        "notice",
        "compensation",
        "salary",
        "visa",
        "meeting",
        "interview",
        "schedule",
        "call",
        "book",
        "calendar",
        "reach",
        "intro",
        "resume",
        "cv",
        "pdf",
        "github",
        "project",
        "projects",
        "impact",
        "leadership",
        "learning",
        "culture",
        "remote",
        "hybrid",
        "hours",
        "saturday",
        "availability",
        "current role",
        "title",
    }
)

# Bare words that only count as contact when they are the whole topic.
_AMBIGUOUS_CONTACT = frozenset({"call", "book", "intro", "reach", "contact"})

_OVERVIEW_RE = re.compile(
    r"\b("
    r"overview|background|introduce|introduction|"
    r"elevator\s+pitch|30-second|thirty.second|"
    r"tell\s+me\s+about|who\s+is\s+he|who\s+are\s+you|who\s+is\s+vasu"
    r")\b",
    re.IGNORECASE,
)

_LOCATION_RE = re.compile(
    r"\b(where|based|location|city|country|live[s]?|resides?)\b",
    re.IGNORECASE,
)

_EMPLOYERS_RE = re.compile(
    r"\b("
    r"companies|company|employers?|"
    r"list\s+of\s+companies|"
    r"work(?:ing)?\s+history|"
    r"career(?:\s+(?:history|path|so\s+far))?|"
    r"where\s+(?:have\s+you|has\s+(?:he|she|vasu|the\s+candidate)|"
    r"did\s+(?:you|he|she|vasu))\s+work(?:ed|ing)?|"
    r"(?:previous|prior)\s+(?:companies|employers|jobs|roles)|"
    r"which\s+companies|"
    r"who(?:m)?\s+(?:has\s+)?(?:he|you|vasu)\s+worked\s+(?:for|at)|"
    r"(?:has|have)\s+(?:you|vasu|he)\s+worked|"
    r"worked\s+(?:in|at|for)|"
    r"experience"
    r")\b",
    re.IGNORECASE,
)
_YEARS_RE = re.compile(
    r"\b("
    r"yoe|"
    r"how\s+long\s+(?:have|has|did)\b|"
    r"how\s+many\s+years|"
    r"total\s+years|"
    r"years?\s+of\s+(?:exp(?:erience)?|work)|"
    r"years?\s+(?:of\s+)?experience|"
    r"experience\s+in\s+years|"
    r"(?:total\s+)?years?\s+(?:working|in\s+(?:the\s+)?(?:industry|field))"
    r")\b",
    re.IGNORECASE,
)

_EDU_RE = re.compile(
    r"\b(education|degree|college|university|school|iit|kanpur|studied|alumni)\b",
    re.IGNORECASE,
)

_CONTACT_TOPIC = frozenset(
    {
        "meeting",
        "interview",
        "schedule",
        "call",
        "book",
        "calendar",
        "contact",
        "reach",
        "intro",
        "email",
        "linkedin",
    }
)
_CONTACT_RE = re.compile(
    r"("
    r"\b(?:meeting|interview|schedule|calendar|contact)\b|"
    r"\b(?:book|booking|reach|intro)\b|"
    r"(?:set\s+up|book|schedule)\s+a\s+(?:call|meeting|chat|interview)|"
    r"(?:a|the|intro(?:ductory)?)\s+call|"
    r"hop\s+on\s+a\s+call|"
    r"how\s+can\s+i\s+(?:reach|book|schedule|contact)|"
    r"get\s+in\s+touch"
    r")",
    re.IGNORECASE,
)

_SALARY_RE = re.compile(
    r"\b(salary|compensation|ctc|pay\s+expect|expected\s+pay|pay\s+range|"
    r"comp\s+band|how\s+much\s+do\s+you\s+(?:make|expect))\b",
    re.IGNORECASE,
)

_RESUME_RE = re.compile(r"\b(resume|cv|curriculum\s+vitae|\.pdf)\b", re.IGNORECASE)

_CURRENT_ROLE_RE = re.compile(
    r"("
    r"current\s+(?:role|title|job|position)|"
    r"what(?:'s| is)\s+your\s+(?:title|role)|"
    r"what\s+do\s+you\s+do\s+now|"
    r"\bmts-?3\b|"
    r"where\s+do\s+you\s+work\s+now"
    r")",
    re.IGNORECASE,
)

_LEADERSHIP_RE = re.compile(
    r"("
    r"lead\s+teams|"
    r"people[\s-]manag|"
    r"\bleadership\b|"
    r"manag(?:e|ing)\s+(?:a\s+)?team|"
    r"people\s+manager|"
    r"engineering\s+manager"
    r")",
    re.IGNORECASE,
)

_SOFT_SKILLS_RE = re.compile(
    r"\b(soft\s+skills|communication\s+skills|teamwork|culture[\s-]fit)\b",
    re.IGNORECASE,
)

_CULTURE_RE = re.compile(
    r"\b(company\s+culture|work\s+culture|work\s+style|values\s+fit|culture\s+fit)\b",
    re.IGNORECASE,
)

_LEARNING_RE = re.compile(
    r"("
    r"learn(?:ing)?\s+new|"
    r"how\s+do\s+you\s+learn|"
    r"still\s+learning|"
    r"new\s+tech|"
    r"ai[\s-]adjacent|"
    r"pick\s+up\s+(?:a\s+)?new"
    r")",
    re.IGNORECASE,
)

_PROJECT_RE = re.compile(
    r"("
    r"hardest\s+project|"
    r"challenging\s+project|"
    r"difficult\s+project|"
    r"proud\s+of|"
    r"named\s+project|"
    r"\bkyc\b|"
    r"\biam\b|"
    r"control[\s-]plane|"
    r"tell\s+me\s+about\s+(?:the\s+)?(?:kyc|iam|project)"
    r")",
    re.IGNORECASE,
)

_IMPACT_RE = re.compile(
    r"\b(impact|sla|dollar|\$\s*impact|measurable\s+results|metrics)\b",
    re.IGNORECASE,
)

_CODE_PORTFOLIO_RE = re.compile(
    r"\b(github|git\s+hub|portfolio|repositor(?:y|ies)|where(?:'s| is)\s+(?:your|his)\s+code)\b",
    re.IGNORECASE,
)

_EMPLOYMENT_TYPE_RE = re.compile(
    r"\b(full[\s-]time|contract|freelance|\bft\b|employment\s+type)\b",
    re.IGNORECASE,
)

_AVAILABILITY_RE = re.compile(
    r"\b(availab(?:le|ility)|notice\s+period|start\s+date|when\s+can\s+you\s+start)\b",
    re.IGNORECASE,
)

_REMOTE_RE = re.compile(
    r"\b(remote|hybrid|wfo)\b",
    re.IGNORECASE,
)
_HOURS_RE = re.compile(
    r"\b(saturday|weekend|5[\s-]?day|five[\s-]?day|work\s+week)\b",
    re.IGNORECASE,
)
_RELOCATION_RE = re.compile(
    r"\b(relocat(?:e|ion)|timezone|time\s+zone|geo(?:graphy)?)\b",
    re.IGNORECASE,
)
_PREF_TOPIC = frozenset(
    {
        "location",
        "based",
        "where",
        "bangalore",
        "bengaluru",
        "india",
        "remote",
        "hybrid",
        "wfo",
        "hours",
        "saturday",
        "weekend",
        "5-day",
        "five-day",
        "work week",
        "preferences",
        "open to",
        "relocate",
        "relocation",
        "timezone",
        "geo",
        "visa",
        "notice",
        "notice period",
        "salary",
        "culture",
        "availability",
    }
)

_EMPLOYER_ORGS = frozenset({"nutanix", "gojek", "deloitte"})
_EMPLOYER_INTENT_ALIASES = frozenset(
    {
        "companies",
        "company",
        "employers",
        "employer",
        "career",
        "worked",
        "experience",
        "work",
        "role",
        "roles",
        "about",
        "profile",
        "bio",
        "contact",
        "work history",
        "years",
        "year",
        "yoe",
        "how long",
        "overview",
        "where",
        "history",
        "previous",
        "industry",
        "industries",
    }
)
_EDU_TERMS = frozenset(
    {"education", "iit", "college", "degree", "kanpur", "university", "studied", "alumni"}
)

# Query term → tags that should match a story. Lowercase. Include JD aliases.
_TERM_EXPAND: dict[str, frozenset[str]] = {
    "k8s": frozenset({"k8s", "kubernetes"}),
    "kubernetes": frozenset({"k8s", "kubernetes"}),
    "golang": frozenset({"go", "golang"}),
    "go": frozenset({"go", "golang"}),
    "postgres": frozenset({"postgres", "postgresql"}),
    "postgresql": frozenset({"postgres", "postgresql"}),
    "spring boot": frozenset({"spring boot", "springboot", "spring-boot"}),
    "springboot": frozenset({"spring boot", "springboot", "spring-boot"}),
    "spring-boot": frozenset({"spring boot", "springboot", "spring-boot"}),
    "ruby on rails": frozenset({"ruby on rails", "rails", "ror"}),
    "rails": frozenset({"ruby on rails", "rails", "ror"}),
    "kafka": frozenset({"kafka"}),
    "redis": frozenset({"redis"}),
    "helm": frozenset({"helm"}),
    "envoy": frozenset({"envoy"}),
    "oidc": frozenset({"oidc"}),
    "elk": frozenset({"elk", "elasticsearch"}),
    "iam": frozenset({"iam"}),
    "kyc": frozenset({"kyc"}),
    "control-plane": frozenset({"control-plane", "controlplane", "iam"}),
    "control plane": frozenset({"control-plane", "controlplane", "iam"}),
    "controlplane": frozenset({"control-plane", "controlplane", "iam"}),
    "java": frozenset({"java"}),
    "python": frozenset({"python"}),
    "nutanix": frozenset({"nutanix"}),
    "gojek": frozenset({"gojek"}),
    "deloitte": frozenset({"deloitte"}),
    "work history": frozenset({"work history", "experience", "career"}),
    "notice period": frozenset({"notice period", "notice"}),
    "homelab": frozenset({"homelab", "self-hosting", "selfhosting"}),
}

_MULTIWORD_TERMS = tuple(
    sorted((k for k in _TERM_EXPAND if " " in k), key=len, reverse=True)
)

# Common JD techs (including ones not in the profile) so gaps like GraphQL are cited.
_JD_TECH_VOCAB = frozenset(
    {
        "go",
        "golang",
        "kubernetes",
        "k8s",
        "kafka",
        "postgres",
        "postgresql",
        "redis",
        "helm",
        "envoy",
        "oidc",
        "elk",
        "iam",
        "kyc",
        "java",
        "python",
        "spring boot",
        "springboot",
        "spring-boot",
        "ruby on rails",
        "rails",
        "ror",
        "graphql",
        "gql",
        "react",
        "reactjs",
        "angular",
        "vue",
        "typescript",
        "javascript",
        "nodejs",
        "node.js",
        "aws",
        "gcp",
        "azure",
        "terraform",
        "docker",
        "rust",
        "scala",
        "c++",
        "kotlin",
        "swift",
        "php",
        "ruby",
        "django",
        "flask",
        "fastapi",
        "next.js",
        "nextjs",
        "mongodb",
        "mysql",
        "elasticsearch",
        "cassandra",
        "spark",
        "hadoop",
        "airflow",
        "flink",
        "grpc",
        "protobuf",
        "ansible",
        "jenkins",
        "prometheus",
        "grafana",
        "istio",
        "dynamodb",
        "lambda",
        "eks",
        "gke",
        "aks",
        "csharp",
        "c#",
        ".net",
        "dotnet",
    }
)
_JD_LOCATION_VOCAB = frozenset(
    {
        "india",
        "bangalore",
        "bengaluru",
        "hyderabad",
        "pune",
        "mumbai",
        "delhi",
        "noida",
        "gurgaon",
        "gurugram",
        "remote",
        "hybrid",
        "onsite",
        "on-site",
        "singapore",
        "london",
        "seattle",
    }
)
_JD_SKILL_STOP = frozenset(
    {
        "experience",
        "exp",
        "work",
        "working",
        "the",
        "a",
        "an",
        "in",
        "with",
        "of",
        "and",
        "or",
        "for",
        "as",
        "at",
        "to",
        "on",
        "relevant",
        "strong",
        "hands",
        "proven",
        "solid",
        "overall",
        "total",
        "industry",
        "professional",
        "software",
        "engineering",
        "engineer",
        "development",
        "background",
    }
)
_YEARS_OF_SKILL_RE = re.compile(
    r"(?P<phrase>(?P<n>\d+)\+?\s*years?\s+(?:of\s+)?"
    r"(?:experience\s+(?:in|with|of)\s+)?"
    r"(?P<skill>[A-Za-z][A-Za-z0-9+#]*(?:\.[A-Za-z0-9+#]+)*))",
    re.IGNORECASE,
)
_YEARS_OVERALL_RE = re.compile(
    r"(?P<phrase>\d+\+?\s*years?\s+(?:of\s+)?(?:experience|exp)\b)",
    re.IGNORECASE,
)


@dataclass
class Story:
    filename: str
    title: str
    techs: list[str]
    orgs: list[str]
    kind: str
    body: str
    tags: frozenset[str] = field(default_factory=frozenset)

    def render(self) -> str:
        tech = ", ".join(self.techs) or "(none)"
        org = ", ".join(self.orgs) or "(none)"
        return (
            f"## stories/{self.filename}\n\n"
            f"title: {self.title}\n"
            f"techs: {tech}\n"
            f"orgs: {org}\n"
            f"kind: {self.kind}\n\n"
            f"{self.body.strip()}"
        )


def profile_dir() -> Path:
    return get_settings().resolved_profile_dir


def set_lookup_query(jd: str, question: str) -> Token[str]:
    """Bind JD + question so lookup_profile can add known tech/org terms."""
    _retrieved_context.set("")
    brief = format_jd_requirements_brief(jd) if (jd or "").strip() else ""
    _jd_brief.set(brief)
    _lookup_question.set((question or "").strip())
    parts = [p for p in (jd or "", question or "") if p.strip()]
    return _lookup_query.set("\n".join(parts))


def reset_lookup_query(token: Token[str]) -> None:
    _retrieved_context.set("")
    _jd_brief.set("")
    _lookup_question.set("")
    _lookup_query.reset(token)


def jd_requirements_brief() -> str:
    """Extracted JD phrases + profile coverage for the current turn (empty if no JD)."""
    return _jd_brief.get()


def retrieved_context() -> str:
    """Markdown returned by lookup_profile during the current turn."""
    return _retrieved_context.get()


def _record_retrieved(chunk: str) -> None:
    prev = _retrieved_context.get()
    _retrieved_context.set(f"{prev}\n\n{chunk}".strip() if prev else chunk)


def _story_paths(directory: Path) -> list[Path]:
    stories = directory / "stories"
    if not stories.is_dir():
        return []
    return sorted(
        p for p in stories.glob("*.md") if p.is_file() and not p.name.startswith("_")
    )


def _mtime_key(directory: Path) -> tuple[tuple[str, int, int], ...]:
    keys: list[tuple[str, int, int]] = []
    for name in (*_PROFILE_FILES, _INTENTS_FILE):
        path = directory / name
        if path.is_file():
            stat = path.stat()
            keys.append((name, stat.st_mtime_ns, stat.st_size))
        else:
            keys.append((name, -1, -1))
    for path in _story_paths(directory):
        stat = path.stat()
        keys.append((f"stories/{path.name}", stat.st_mtime_ns, stat.st_size))
    return tuple(keys)


def _parse_intents_yaml(raw: str) -> dict[str, tuple[str, ...]]:
    """Parse theme/files/aliases YAML into alias → profile files."""
    aliases: dict[str, tuple[str, ...]] = {}
    files: list[str] = []
    mode: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0 and stripped.endswith(":"):
            files = []
            mode = None
            continue
        if stripped in {"files:", "aliases:"}:
            mode = stripped[:-1]
            continue
        if mode and stripped.startswith("- "):
            value = stripped[2:].strip().strip("'\"")
            if not value:
                continue
            if mode == "files":
                files.append(value)
            elif mode == "aliases" and files:
                aliases[value.lower()] = tuple(files)
    return aliases


def _parse_scalar_list(raw: str) -> list[str]:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
    if value:
        return [value.strip().strip("'\"")]
    return []


def parse_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    text = raw.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, raw
    rest = text[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end == -1:
        return {}, raw
    fm = rest[:end]
    body = rest[end + 4 :].lstrip("\n")
    meta: dict[str, object] = {}
    for line in fm.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower()
        val = val.strip()
        if key in {"techs", "orgs"}:
            meta[key] = _parse_scalar_list(val)
        else:
            meta[key] = val.strip("'\"")
    return meta, body


def _story_from_path(path: Path) -> Story:
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    techs = [str(t).strip().lower() for t in (meta.get("techs") or []) if str(t).strip()]
    orgs = [str(o).strip() for o in (meta.get("orgs") or []) if str(o).strip()]
    title = str(meta.get("title") or path.stem)
    kind = str(meta.get("kind") or "")
    tags = frozenset(
        {t.lower() for t in techs}
        | {o.lower() for o in orgs}
        | {kind.lower()} - {""}
    )
    return Story(
        filename=path.name,
        title=title,
        techs=techs,
        orgs=orgs,
        kind=kind,
        body=body,
        tags=tags,
    )


def _load_sections(directory: Path) -> dict[str, str]:
    sections: dict[str, str] = {}
    for name in _PROFILE_FILES:
        path = directory / name
        sections[name] = path.read_text(encoding="utf-8") if path.is_file() else ""
    return sections


def _refresh_cache() -> None:
    global _cache_key, _cache_sections, _cache_stories, _cache_intent_aliases
    directory = profile_dir()
    key = _mtime_key(directory)
    if _cache_key != key:
        _cache_sections = _load_sections(directory)
        _cache_stories = [_story_from_path(p) for p in _story_paths(directory)]
        intents_path = directory / _INTENTS_FILE
        _cache_intent_aliases = (
            _parse_intents_yaml(intents_path.read_text(encoding="utf-8"))
            if intents_path.is_file()
            else {}
        )
        _cache_key = key


def _merged_aliases() -> dict[str, tuple[str, ...]]:
    _refresh_cache()
    merged = dict(_TOPIC_ALIASES)
    merged.update(_cache_intent_aliases)
    return merged


def load_profile_files() -> dict[str, str]:
    """Return {filename: markdown}. Reloads when any file mtime/size changes."""
    _refresh_cache()
    return dict(_cache_sections)


def load_stories() -> list[Story]:
    _refresh_cache()
    return list(_cache_stories)


def all_profile_text() -> str:
    parts = []
    for name, text in load_profile_files().items():
        if text.strip():
            parts.append(f"## {name}\n\n{text.strip()}")
    return "\n\n".join(parts)


def identity_facts() -> str:
    """Lead-in from profile.md (before the pitch). Not a second bio."""
    profile = load_profile_files().get("profile.md", "").strip()
    if not profile:
        return "Look up profile/*.md. Do not invent employers, titles, years, or numbers."
    head = profile.split("## Pitch", 1)[0].strip()
    return f"{head}\nLook up anything else; do not recite a full bio."


def extract_focus_terms(text: str) -> frozenset[str]:
    """Known techs, orgs, and topic aliases — not leftover generic tokens."""
    lowered = (text or "").lower()
    found: set[str] = set()
    working = lowered
    aliases = _merged_aliases()
    for phrase in _MULTIWORD_TERMS:
        if phrase in working:
            found.update(_TERM_EXPAND[phrase])
            if phrase in aliases:
                found.add(phrase)
            working = working.replace(phrase, " ")
    for term, expanded in _TERM_EXPAND.items():
        if " " in term:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", working):
            found.update(expanded)
            found.add(term)
    for alias in aliases:
        if " " in alias:
            if alias in lowered:
                found.add(alias)
            continue
        if alias in _AMBIGUOUS_CONTACT and lowered.strip() != alias:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered):
            found.add(alias)
    for story in load_stories():
        for tag in story.tags:
            if tag and re.search(rf"(?<![a-z0-9]){re.escape(tag)}(?![a-z0-9])", lowered):
                found.add(tag)
                found.update(_TERM_EXPAND.get(tag, ()))
    return frozenset(found)


@dataclass(frozen=True)
class JdRequirement:
    """A concrete JD phrase to cite (tech, years, location)."""

    phrase: str
    term: str
    kind: str


def extract_jd_requirements(jd: str) -> list[JdRequirement]:
    """Languages, frameworks, infra, years, location — keep the JD's wording."""
    text = jd or ""
    if not text.strip():
        return []
    found: list[JdRequirement] = []
    seen: set[str] = set()
    occupied: list[tuple[int, int]] = []

    def overlap(start: int, end: int) -> bool:
        return any(start < b and end > a for a, b in occupied)

    def add(phrase: str, term: str, kind: str, start: int, end: int) -> None:
        key = term.lower()
        if not phrase.strip() or key in seen or overlap(start, end):
            return
        seen.add(key)
        occupied.append((start, end))
        found.append(
            JdRequirement(phrase=phrase.strip().rstrip(".,;:"), term=key, kind=kind)
        )

    for match in _YEARS_OF_SKILL_RE.finditer(text):
        skill = match.group("skill")
        skill_l = skill.lower()
        if skill_l in _JD_SKILL_STOP:
            continue
        known = skill_l in _JD_TECH_VOCAB or skill_l in _TERM_EXPAND
        looks_tech = skill[0].isupper() or any(c in skill for c in "+#.")
        if not known and not looks_tech:
            continue
        add(match.group("phrase"), skill, "years_skill", match.start(), match.end())

    for match in _YEARS_OVERALL_RE.finditer(text):
        add(match.group("phrase"), "years", "years", match.start(), match.end())

    vocab = set(_JD_TECH_VOCAB)
    vocab.update(_TERM_EXPAND)
    vocab.update(alias for alias in _merged_aliases() if alias not in _BROAD_ALIASES)
    for story in load_stories():
        vocab.update(story.tags)

    multi = sorted((v for v in vocab if " " in v), key=len, reverse=True)
    for phrase in multi:
        for match in re.finditer(
            rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        ):
            add(match.group(0), phrase, "tech", match.start(), match.end())

    singles = sorted(
        (v for v in vocab if " " not in v and len(v) >= 2),
        key=len,
        reverse=True,
    )
    for term in singles:
        if term in _BROAD_ALIASES:
            continue
        if len(term) <= 2 and term not in {"go", "k8s"}:
            continue
        for match in re.finditer(
            rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        ):
            add(match.group(0), term, "tech", match.start(), match.end())

    for loc in sorted(_JD_LOCATION_VOCAB, key=len, reverse=True):
        for match in re.finditer(
            rf"(?<![A-Za-z0-9]){re.escape(loc)}(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        ):
            add(match.group(0), loc, "location", match.start(), match.end())

    return found


def _profile_mentions(term: str) -> bool:
    expanded = {term.lower()}
    expanded.update(_TERM_EXPAND.get(term.lower(), ()))
    blob = all_profile_text().lower()
    for story in load_stories():
        blob += "\n" + " ".join(story.tags) + "\n" + story.body.lower()
    for token in expanded:
        if not token:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", blob):
            return True
    return False


def _orgs_for_term(term: str) -> list[str]:
    expanded = {term.lower()}
    expanded.update(_TERM_EXPAND.get(term.lower(), ()))
    orgs: list[str] = []
    for story in _matching_stories(frozenset(expanded)):
        for org in story.orgs:
            if org not in orgs:
                orgs.append(org)
    return orgs


def _jd_requirement_evidence(req: JdRequirement) -> str:
    if req.kind == "years":
        return " → I have 5+ years overall. Do not invent a more precise number."
    if req.kind == "location":
        if req.term in {"india", "bangalore", "bengaluru"} or _profile_mentions(req.term):
            return " → listed: I am based in Bangalore, India."
        return " → I am based in Bangalore, India; I don't list that specific city/policy."
    mentioned = _profile_mentions(req.term)
    orgs = _orgs_for_term(req.term)
    if mentioned:
        bits = ["listed in the profile"]
        if orgs:
            bits.append("used at " + " / ".join(orgs))
        if req.kind == "years_skill":
            bits.append("no per-skill year count — do not invent one")
        return " → " + "; ".join(bits)
    return (
        " → not listed in the profile. Say I don't list that. "
        "Do not invent experience or a year count."
    )


def format_jd_requirements_brief(jd: str) -> str:
    """Deterministic JD-term list for the concierge / fit_analyst. Empty JD → empty."""
    if not (jd or "").strip():
        return ""
    reqs = extract_jd_requirements(jd)
    if not reqs:
        return (
            "JD REQUIREMENTS: no concrete languages/frameworks/infra/years/location "
            "extracted. Call assess_fit and map whatever named requirements you see. "
            "Do not invent."
        )
    lines = [
        "JD REQUIREMENTS (cite these exact phrases; for each say match / partial / "
        "not listed using only profile/*.md and stories; never invent):"
    ]
    for req in reqs:
        lines.append(f'- "{req.phrase}"{_jd_requirement_evidence(req)}')
    lines.append(
        "Years on a listed skill: say I have used it (or 5+ years overall). "
        "Do not invent a year number for a technology."
    )
    return "\n".join(lines)


def _specific_terms(terms: frozenset[str]) -> frozenset[str]:
    specific = frozenset(t for t in terms if t not in _BROAD_ALIASES)
    return specific or terms


def _is_overview_query(text: str) -> bool:
    return bool(_OVERVIEW_RE.search(text or ""))


def _is_years_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"years", "year", "yoe", "how long"}:
        return True
    return bool(_YEARS_RE.search(text or ""))


def _is_employers_query(text: str) -> bool:
    if _is_years_query(text) or _is_contact_query(text):
        return False
    if not _EMPLOYERS_RE.search(text or ""):
        return False
    focus = extract_focus_terms(text)
    techish = focus - _BROAD_ALIASES - _EMPLOYER_INTENT_ALIASES - _EMPLOYER_ORGS
    return not techish


def _is_education_query(text: str) -> bool:
    if not _EDU_RE.search(text or ""):
        return False
    if _is_employers_query(text):
        return False
    focus = extract_focus_terms(text)
    techish = focus - _BROAD_ALIASES - _EDU_TERMS
    return not techish


def _is_location_query(text: str) -> bool:
    if _is_contact_query(text) or _is_employers_query(text):
        return False
    if _is_remote_query(text) or _is_hours_query(text) or _is_relocation_query(text):
        return False
    t = (text or "").strip().lower()
    if t in {"location", "based", "where", "bangalore", "bengaluru", "india"}:
        return True
    if not _LOCATION_RE.search(text or ""):
        return False
    focus = extract_focus_terms(text)
    techish = focus - _BROAD_ALIASES - {
        "location",
        "based",
        "where",
        "preferences",
        "open to",
        "roles wanted",
        "bangalore",
        "bengaluru",
        "india",
    }
    return not techish


def _is_remote_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"remote", "hybrid", "wfo"}:
        return True
    return bool(_REMOTE_RE.search(text or ""))


def _is_hours_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"hours", "saturday", "weekend", "5-day", "five-day", "work week"}:
        return True
    return bool(_HOURS_RE.search(text or ""))


def _is_relocation_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"relocate", "relocation", "timezone", "geo"}:
        return True
    return bool(_RELOCATION_RE.search(text or ""))


def _is_contact_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in _CONTACT_TOPIC:
        return True
    return bool(_CONTACT_RE.search(text or ""))


def _is_salary_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"salary", "compensation", "ctc", "pay"}:
        return True
    return bool(_SALARY_RE.search(text or ""))


def _is_resume_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"resume", "cv", "pdf"}:
        return True
    return bool(_RESUME_RE.search(text or ""))


def _is_current_role_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"current role", "current title", "title", "mts", "mts-3", "currently"}:
        return True
    return bool(_CURRENT_ROLE_RE.search(text or ""))


def _is_leadership_query(text: str) -> bool:
    return bool(_LEADERSHIP_RE.search(text or ""))


def _is_soft_skills_query(text: str) -> bool:
    return bool(_SOFT_SKILLS_RE.search(text or ""))


def _is_culture_query(text: str) -> bool:
    return bool(_CULTURE_RE.search(text or ""))


def _is_learning_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"learning", "learn", "new tech", "still learning"}:
        return True
    return bool(_LEARNING_RE.search(text or ""))


def _is_project_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"project", "projects", "hardest", "challenging", "kyc", "iam"}:
        return True
    return bool(_PROJECT_RE.search(text or ""))


def _is_impact_query(text: str) -> bool:
    return bool(_IMPACT_RE.search(text or ""))


def _is_code_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"github", "code", "portfolio"}:
        return True
    return bool(_CODE_PORTFOLIO_RE.search(text or ""))


def _is_employment_type_query(text: str) -> bool:
    return bool(_EMPLOYMENT_TYPE_RE.search(text or ""))


def _is_availability_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in {"availability", "available", "notice", "notice period"}:
        return True
    return bool(_AVAILABILITY_RE.search(text or ""))


def _section_matches(text: str, terms: frozenset[str]) -> bool:
    blob = text.lower()
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", blob):
            return True
    return False


def _slice_markdown(text: str, terms: frozenset[str]) -> str:
    """Keep ## heading blocks that mention a focus term."""
    if not text.strip() or not terms:
        return ""
    chunks = re.split(r"(?m)(?=^## )", text)
    kept: list[str] = []
    for chunk in chunks:
        stripped = chunk.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and not stripped.startswith("##"):
            title, _, rest = stripped.partition("\n")
            if rest.strip() and _section_matches(rest, terms):
                kept.append(stripped)
            continue
        if _section_matches(stripped, terms):
            kept.append(stripped)
    return "\n\n".join(kept)


def _keep_matching_lines(text: str, terms: frozenset[str]) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip() and _section_matches(ln, terms)]
    return "\n".join(lines)


def _slice_profile_file(name: str, text: str, terms: frozenset[str]) -> str:
    if not text.strip():
        return ""
    if name == "profile.md":
        loc_terms = {"location", "based", "india"}
        year_terms = {"years", "year", "yoe", "how long", "experience", "5+"}
        role_terms = {"current role", "title", "mts", "mts-3", "currently", "right now"}
        if terms & loc_terms:
            sliced = _keep_matching_lines(text, terms | loc_terms | {"india"})
            return sliced
        if terms & year_terms:
            sliced = _keep_matching_lines(text, year_terms)
            if sliced:
                return sliced
        if terms & role_terms or terms & {
            "profile",
            "about",
            "bio",
            "overview",
            "pitch",
        }:
            return text
        return ""
    if name == "contact.md":
        return text
    if name == "education.md":
        return text
    if name == "projects.md":
        sliced = _slice_markdown(text, terms)
        return sliced or text
    if name == "preferences.md":
        sliced = _slice_markdown(text, terms)
        if sliced:
            return sliced
        return _keep_matching_lines(text, terms)
    if name == "experience.md":
        sliced = _slice_markdown(text, terms)
        if sliced:
            return sliced
        if terms & _EMPLOYER_INTENT_ALIASES or terms & _EMPLOYER_ORGS:
            return _employer_sections(text)
        return ""
    sliced = _slice_markdown(text, terms)
    if sliced:
        return sliced
    if name == "skills.md" and terms:
        return _keep_matching_lines(text, terms) or text
    return ""


def _matching_profile_files(needle: str, terms: frozenset[str]) -> list[str]:
    names: list[str] = []
    specific = _specific_terms(terms)
    has_specific = specific != terms or bool(terms - _BROAD_ALIASES)
    for alias, files in _merged_aliases().items():
        if has_specific and alias in _BROAD_ALIASES:
            continue
        hit = alias in terms or alias in specific
        if not hit and " " in alias and alias in needle:
            hit = True
        if not hit and " " not in alias:
            hit = bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", needle))
            if hit and alias in _BROAD_ALIASES and has_specific:
                continue
        if hit:
            for filename in files:
                if filename not in names:
                    names.append(filename)
    return names


def _matching_stories(terms: frozenset[str]) -> list[Story]:
    if not terms:
        return []
    matched: list[Story] = []
    for story in load_stories():
        story_vocab = set(story.tags)
        for tag in list(story.tags):
            story_vocab.update(_TERM_EXPAND.get(tag, ()))
        title_l = story.title.lower()
        if story_vocab & terms:
            matched.append(story)
            continue
        if any(t in title_l for t in terms if len(t) >= 3):
            matched.append(story)
    return matched


def _no_match_payload(label: str) -> str:
    return (
        f"{identity_facts()}\n\n"
        f"No specific story tagged {label}. "
        "Do not invent a story or pad with unrelated employers, education, or metrics."
    )


def _files_payload(*names: str) -> str:
    sections = load_profile_files()
    parts: list[str] = []
    for name in names:
        text = sections.get(name, "").strip()
        if text:
            parts.append(f"## {name}\n\n{text}")
    return "\n\n".join(parts) or identity_facts()


def _overview_payload() -> str:
    base = _files_payload("profile.md", "experience.md", "skills.md")
    prefs = _pref_slice_payload(
        "backend",
        "infra",
        "data",
        "ai-adjacent",
        "agentic",
        "bangalore",
        "india",
        "location",
        "remote",
        "hybrid",
    )
    parts = [p for p in (base, prefs) if p]
    return "\n\n".join(parts) or identity_facts()


def _pref_slice_payload(*needles: str, extra_files: tuple[str, ...] = ()) -> str:
    """Return only matching ## blocks from preferences.md — never the whole file."""
    sections = load_profile_files()
    prefs = sections.get("preferences.md", "")
    terms = frozenset(n.lower() for n in needles)
    sliced = _slice_markdown(prefs, terms)
    if not sliced:
        sliced = _keep_matching_lines(prefs, terms)
    parts: list[str] = []
    if sliced:
        parts.append(f"## preferences.md\n\n{sliced}")
    for name in extra_files:
        text = sections.get(name, "").strip()
        if not text:
            continue
        if name == "profile.md":
            loc = _keep_matching_lines(text, frozenset({"location", "india", "bangalore"}))
            if loc:
                parts.append(f"## profile.md\n\n{loc}")
            continue
        parts.append(f"## {name}\n\n{text}")
    return "\n\n".join(parts) or identity_facts()


def _location_payload() -> str:
    return _pref_slice_payload(
        "location",
        "bangalore",
        "bengaluru",
        "based",
        "india",
        "prefer",
        extra_files=("profile.md",),
    )


def _remote_payload() -> str:
    return _pref_slice_payload("remote", "hybrid", "wfo")


def _hours_payload() -> str:
    return _pref_slice_payload("hours", "saturday", "weekend", "5-day", "five-day")


def _unlisted_pref_payload(*extra_files: str) -> str:
    return _pref_slice_payload(
        "don't list",
        "do not list",
        "salary",
        "visa",
        "notice",
        "relocation",
        "culture",
        "contract",
        "full-time",
        extra_files=extra_files,
    )


def _years_payload() -> str:
    sections = load_profile_files()
    profile = sections.get("profile.md", "")
    year_terms = frozenset({"year", "years", "experience", "5+"})
    sliced = _keep_matching_lines(profile, year_terms)
    if sliced:
        return f"## profile.md\n\n{sliced}"
    return identity_facts()


def _employer_sections(text: str) -> str:
    return _slice_markdown(text, _EMPLOYER_ORGS)


def _employers_payload() -> str:
    sections = load_profile_files()
    exp = sections.get("experience.md", "")
    sliced = _employer_sections(exp)
    if sliced:
        return f"## experience.md\n\n{sliced}"
    return exp.strip() or identity_facts()


def _education_payload() -> str:
    return _files_payload("education.md")


def _contact_payload() -> str:
    return _files_payload("contact.md")


def _salary_payload() -> str:
    return _unlisted_pref_payload("contact.md")


def _projects_payload() -> str:
    stories = _matching_stories(frozenset({"kyc", "iam", "kubernetes", "kafka"}))
    parts = [_files_payload("projects.md")]
    for story in stories:
        parts.append(story.render())
    return "\n\n".join(parts)


def _intent_payload(topic_s: str, extra_s: str, vague_topic: bool) -> str | None:
    """Return a dedicated FAQ payload, or None to fall through to term matching."""

    question_s = _lookup_question.get() or extra_s

    def hit(pred) -> bool:
        return pred(topic_s) or (vague_topic and extra_s and pred(extra_s))

    def pref_hit(pred) -> bool:
        if pred(topic_s):
            return True
        topic_l = topic_s.strip().lower()
        if topic_l in _PREF_TOPIC and question_s and pred(question_s):
            return True
        return False

    if hit(_is_years_query):
        return _years_payload()
    if hit(_is_contact_query):
        return _contact_payload()
    if hit(_is_salary_query):
        return _salary_payload()
    if hit(_is_resume_query):
        return _contact_payload()
    if hit(_is_code_query):
        return _contact_payload()
    if hit(_is_current_role_query):
        return _files_payload("profile.md")
    if hit(_is_leadership_query):
        return _unlisted_pref_payload("projects.md")
    if hit(_is_soft_skills_query) or hit(_is_culture_query):
        return _unlisted_pref_payload()
    if hit(_is_employment_type_query) or hit(_is_availability_query):
        return _unlisted_pref_payload("contact.md")
    if hit(_is_employers_query):
        return _employers_payload()
    if pref_hit(_is_hours_query):
        return _hours_payload()
    if pref_hit(_is_remote_query):
        return _remote_payload()
    if pref_hit(_is_relocation_query):
        return _unlisted_pref_payload()
    if pref_hit(_is_location_query):
        return _location_payload()
    if hit(_is_education_query):
        return _education_payload()
    if hit(_is_learning_query):
        roles = _pref_slice_payload("learning", "ai-adjacent", "ai", "backend", "agentic")
        profile = _files_payload("profile.md")
        return "\n\n".join(p for p in (roles, profile) if p)
    if hit(_is_impact_query) or hit(_is_project_query):
        return _projects_payload()
    if hit(_is_overview_query):
        return _overview_payload()
    return None


def lookup_sections(topic: str) -> str:
    """Retrieve matching stories + sliced profile files. Does not invent."""
    extra = _lookup_query.get()
    topic_s = (topic or "").strip()
    extra_s = extra.strip()
    combined_for_intent = "\n".join(p for p in (topic_s, extra_s) if p)

    if not combined_for_intent:
        result = identity_facts()
        _record_retrieved(result)
        return result

    topic_focus = extract_focus_terms(topic_s) if topic_s else frozenset()
    extra_focus = extract_focus_terms(extra_s) if extra_s else frozenset()
    jd_specific = extra_focus - _BROAD_ALIASES
    vague_topic = not (topic_focus - _BROAD_ALIASES)

    dedicated = _intent_payload(topic_s, extra_s, vague_topic)
    if dedicated is not None:
        _record_retrieved(dedicated)
        return dedicated

    # Fold JD techs into retrieval so Go/K8s stories surface when a JD names them.
    if topic_focus - _BROAD_ALIASES:
        terms = _specific_terms(topic_focus | jd_specific)
    elif jd_specific:
        terms = _specific_terms(extra_focus | topic_focus)
    elif topic_focus:
        terms = topic_focus
    else:
        terms = extra_focus

    needle = topic_s.lower() if topic_s else extra_s.lower()
    stories = _matching_stories(terms)
    names = _matching_profile_files(needle, terms)

    parts: list[str] = []
    sections = load_profile_files()
    for name in names:
        sliced = _slice_profile_file(name, sections.get(name, ""), terms)
        if sliced:
            parts.append(f"## {name}\n\n{sliced}")

    for story in stories:
        parts.append(story.render())

    if not parts:
        label = topic_s or ", ".join(sorted(terms)[:4]) or "that topic"
        result = _no_match_payload(label)
        _record_retrieved(result)
        return result

    if not stories:
        label = topic_s or next(iter(sorted(terms)), "that topic")
        parts.append(f"No specific story tagged {label}.")

    result = "\n\n".join(parts)
    _record_retrieved(result)
    return result
