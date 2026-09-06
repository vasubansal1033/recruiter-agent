---
name: update-recruiter-profile
description: >-
  Add or update Vasu Bansal recruiter-agent experience at story/incident
  granularity. Copies profile/stories/_template.md, fills YAML frontmatter
  (techs/orgs/kind), and updates profile/*.md. Use when adding work experience,
  a production incident, a project story, new skills, or when the user says
  update recruiter profile, add a story, or tag a tech for JD matching.
---

# Update recruiter profile

Project root: the `recruiter-agent` repo. Context lives in markdown. Drop a new `.md` file — no code change.

Never invent metrics, dates, team sizes, SLAs, salary, certs, visa, or notice period.

Write recruiter-facing first person or factual bullets. First person as Vasu.

## Add a new story

Copy this checklist:

```
- [ ] Copy template
- [ ] Fill frontmatter
- [ ] Write only user-provided facts
- [ ] Sanity-check lookup
```

1. Copy `profile/stories/_template.md` to `profile/stories/<slug>.md` (do not start the filename with `_`; `_template.md` is skipped at load time).
2. Fill frontmatter `techs` / `orgs` / `kind`. Write only user-provided facts.
3. Body: what happened, what you did, outcome. Only facts the user wrote. No invented metrics.
4. Sanity-check (command below).

Frontmatter shape:

```md
---
title: Kafka consumer lag incident
techs: [kafka, postgres, kubernetes]
orgs: [Gojek]
kind: incident
---
```

`kind` is one of: `incident`, `project`, `role`. Add another only if the user names it.

## Choose tags that will match JDs

- Lowercase in `techs`.
- Common aliases: e.g. list both `k8s` and `kubernetes` if relevant. Same for `go` / `golang`, `postgres` / `postgresql`, `spring-boot` / `springboot`.
- `orgs` use the company name as written in `profile/experience.md` (`Gojek`, `Nutanix`, `Deloitte`).
- Retrieval is **tag + keyword** on the recruiter question **and** the pasted JD. If Kafka is in the JD or they ask about Kafka, every story tagged `kafka` is eligible.
- If nothing matches, the agent returns general profile only — do not invent a story.

## Put FAQ facts in the right file

| File | When |
|---|---|
| `profile/profile.md` | Current role (MTS-3 Nutanix), short bio, years (5+), pitch |
| `profile/experience.md` | Companies, titles, periods — Nutanix, Gojek, Deloitte only |
| `profile/education.md` | IIT Kanpur, degrees, 2016–21 |
| `profile/skills.md` | Stack and programming languages |
| `profile/projects.md` | Named work (KYC, IAM). No fake metrics, SLAs, or $ impact |
| `profile/preferences.md` | Open-to roles, Bangalore/India, remote, hybrid WFO, 5-day week, no Saturdays, learning/AI, honest unknowns (salary, visa, notice, lead teams, FT/contract, culture, soft skills). Slice by heading — never dump the whole file. |
| `profile/contact.md` | Email, LinkedIn, calendar booking (Meet), GitHub, resume PDF |
| `profile/intents.yaml` | Question theme → files + aliases. Add an alias when a new FAQ phrasing should hit existing files |
| `profile/stories/` | Incident/project granularity with techs/orgs tags |

Meeting / interview / schedule / call / book / calendar / contact / reach / intro always belong in `contact.md` with all three as Markdown labeled links (no bare URLs in spoken sentences):

1. Email: [email](mailto:vasubansal1998@gmail.com) or [email me](mailto:vasubansal1998@gmail.com)
2. LinkedIn: [LinkedIn](https://www.linkedin.com/in/vasub-iitk/)
3. Book a Google Meet: [book a Google Meet](https://calendar.app.google/BXzB9rtHZ8mZFWbD9) (Calendar appointment page — do not invent a meet.google.com URL)

Do not invent employers, titles, years, or impact numbers. If the user did not give a number, omit it.

Stories are for incident/project granularity. Role summaries stay in `experience.md`. Named project summaries also go in `projects.md`.

## Sanity-check after adding

Lookup (no API key):

```bash
uv run python -c "from recruiter_agent.context import lookup_sections; print(lookup_sections('TECH'))"
```

Replace `TECH` with a tag you added (e.g. `kafka`) or a FAQ theme (`contact`, `schedule`, `education`, `salary`). The matching file or `stories/<slug>.md` block must appear.

CLI question mentioning that tech should surface the story (needs `.env` key):

```bash
uv run python -m recruiter_agent.cli -q "What TECH work has he done?"
```

If lookup does not print the story: fix tags (add JD aliases) or add an alias in `profile/intents.yaml`, then rerun the lookup command. Do not invent body text to force a match.
