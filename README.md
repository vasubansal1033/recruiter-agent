# Recruiter agent

Local or hostable agent that answers recruiter questions about Vasu Bansal. Paste a JD, ask a question, get a human-language fit answer grounded in `profile/*.md` (no invented metrics).

The blog Ask widget `POST`s `/chat` `{ "jd", "question" }` → `{ "answer" }`. Gradio `/ui` is the standalone test page.

## 1. Run locally (about 3 minutes)

1. Copy env and add a key (Gemini is the default model):

```bash
cd recruiter-agent
cp .env.example .env
# edit .env — set GEMINI_API_KEY
```

2. Install:

```bash
uv sync
```

3. Start the API:

```bash
uv run uvicorn recruiter_agent.server:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl -s http://127.0.0.1:8000/health
```

Chat (needs a real key in `.env`):

```bash
curl -s http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"jd":"Backend engineer, Go, Kubernetes","question":"Why a fit?"}'
```

CLI:

```bash
uv run python -m recruiter_agent.cli --help
uv run python -m recruiter_agent.cli -q "Summarize backend and infra experience"
uv run python -m recruiter_agent.cli --model gemini/gemini-2.0-flash --jd "Go backend" -q "Why hire him?"
```

Gradio UI is mounted on the same FastAPI process at `/ui` (standalone test page, not the blog embed):

```bash
# same uvicorn as above — open http://127.0.0.1:8000/ui
```

Standalone (own process):

```bash
uv run python -m recruiter_agent.ui
```

## 2. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_MODEL` | `gemini/gemini-2.5-flash` | LiteLLM model string |
| `GEMINI_API_KEY` | empty | Required for `gemini/...` |
| `ANTHROPIC_API_KEY` | empty | Required for `anthropic/...` |
| `OPENAI_API_KEY` | empty | Required for `openai/...` |
| `OPENAI_AGENTS_DISABLE_TRACING` | `1` | Keep off unless you want Agents SDK traces (uses `OPENAI_API_KEY`) |
| `OLLAMA_API_BASE` | `http://localhost:11434` | Local Ollama only |
| `ALLOWED_ORIGINS` | GitHub Pages + local Astro | Comma-separated CORS allowlist |
| `PORT` | `8000` | Bind port (Spaces / Cloud Run / Render inject this) |
| `PROFILE_DIR` | `<repo>/profile` | Override markdown directory |

Model examples:

- `gemini/gemini-2.5-flash` — Gemini; needs `GEMINI_API_KEY`
- `anthropic/claude-3-5-haiku-latest` — Anthropic; needs `ANTHROPIC_API_KEY`
- `openai/gpt-4o-mini` — OpenAI; needs `OPENAI_API_KEY`
- `ollama/qwen2.5:7b` — Ollama; **local-dev only**, no cloud key

Never commit `.env` or API keys.

## 3. Update the profile (no code change)

Edit any file in `profile/`:

- `profile.md` — bio, contact, pitch
- `experience.md` — roles and education
- `skills.md` — stack
- `preferences.md` — open-to roles, location

The agent reloads markdown when file mtimes change. Do not invent employers, titles, years, metrics, SLAs, team sizes, dates, or impact numbers in these files.

### Update experience (stories)

Incident- and project-level facts live in `profile/stories/*.md` (one file per story, YAML frontmatter with `techs` / `orgs` / `kind`). Drop a new file — no code change. `_template.md` is the copy source and is not loaded.

Retrieval is tag + keyword: if the JD or question mentions a tagged tech (e.g. Kafka), matching stories are returned with the relevant profile sections. No match → general profile only; nothing is invented.

Cursor skill (copy template, tag aliases, sanity-check): `.cursor/skills/update-recruiter-profile/SKILL.md`.

After adding a story, replace `TECH` with a tag you set:

```bash
uv run python -c "from recruiter_agent.context import lookup_sections; print(lookup_sections('TECH'))"
```

## 4. Wire the blog widget

Do **not** edit the blog repo from this project. On the blog side, set `chatProxyUrl` in `src/data/recruiter.ts` (the Ask widget `POST`s this URL):

- Local: `http://127.0.0.1:8000/chat`
- Prod: `https://<your-host>/chat`

CORS allowlist must include the blog origin (`https://vasubansal1033.github.io` and/or `http://localhost:4321`).

HTTP contract:

- `POST /chat` `{ "jd": "...", "question": "..." }` → `{ "answer": "..." }`
- `POST /chat/stream` same body → SSE `data: {"text":"<growing answer>"}` then `data: {"done":true}` (or `data: {"error":"..."}`)
- `GET /health` → `{ "status": "ok" }`
- Caps: question ≤ 2000 chars, jd ≤ 12000 chars
- Rate limit: 10 requests / 60s per IP
- Missing key → 503 `{ "error": "Chat isn't available at the moment. Email is best." }`
- Rate limit → 429 `{ "error": "I'm getting a lot of questions right now. Please try again in a minute." }`
- Model failure → 502 `{ "error": "I couldn't complete that just now. Please try again." }`

## 5. Hosting

Production model must be Gemini, Anthropic, or OpenAI. Do not point a hosted instance at Ollama.

Free-tier caveat: the first request after idle can be a **cold start** (tens of seconds). The blog widget may time out; retry once.

### Hugging Face Spaces (recommended)

1. Create a Docker Space.
2. Push this repo (or the image).
3. In Space secrets, set `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) and optionally `AGENT_MODEL`.
4. Set `ALLOWED_ORIGINS` to include `https://vasubansal1033.github.io`.
5. Spaces provides `PORT`. App listens on `0.0.0.0:$PORT`.
6. Blog `chatProxyUrl` = `https://<space>.hf.space/chat`.

### Cloud Run

```bash
docker build -t recruiter-agent .
# push to Artifact Registry, then:
gcloud run deploy recruiter-agent \
  --image <image> \
  --port 8000 \
  --set-env-vars AGENT_MODEL=gemini/gemini-2.0-flash,ALLOWED_ORIGINS=https://vasubansal1033.github.io \
  --set-secrets GEMINI_API_KEY=gemini-key:latest
```

### Render

1. New Web Service from this repo.
2. Docker runtime. `PORT` is injected.
3. Add `GEMINI_API_KEY` (secret) and `ALLOWED_ORIGINS`.
4. Blog `chatProxyUrl` = `https://<service>.onrender.com/chat`.

## 6. Docker locally

```bash
docker build -t recruiter-agent .
docker run --rm -p 8000:8000 --env-file .env recruiter-agent
```

## Layout

```
profile/*.md                 # bio, roles, skills, preferences
profile/stories/*.md         # tagged stories (one file each)
src/recruiter_agent/agent.py # concierge + fit_analyst tool + guardrail
src/recruiter_agent/server.py
src/recruiter_agent/cli.py
src/recruiter_agent/ui.py
```
