# WildIdea

WildIdea Web is a FastAPI web app for generating cross-domain innovation ideas. It includes user accounts, credits, invitation codes, task history, live card progress, feedback collection, admin review, and Excel export.

This repository also carries the original WildIdea agent skill. The skill is not a user-facing CLI: `skill/wildidea/SKILL.md` is the standalone skill entrypoint, `skill/wildidea/references/wildidea-skill.md` is the full workflow spec, and the Python scripts are helper tools an agent may call internally.

## Versions

- Web: 1.4
- Skill spec: 1.3

## Stack

- Backend: Python, FastAPI, SQLAlchemy, Uvicorn
- Frontend: HTML, CSS, JavaScript
- Database: SQLite by default
- Deployment target: Mac mini behind Hermes reverse proxy

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Fill `.env` with server-side API keys, then start:

```bash
deploy/macmini/start.sh
```

Open:

```text
http://127.0.0.1:8000
```

## Standalone Skill

The downloadable skill package lives in:

```text
skill/wildidea/
```

To use it without running the Web app, copy that folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R skill/wildidea ~/.codex/skills/wildidea
```

Then start a new Codex chat and ask:

```text
Use $wildidea to generate cross-domain ideas for ...
```

The standalone skill includes its own card pool, references, poster template, and zero-key web search helper (`scripts/search_helper.py`). Users who want the networking/search version can download this skill folder directly and use it without deploying the website.

## Hermes Deployment

Use Hermes to reverse proxy your domain to the local upstream:

```text
http://127.0.0.1:8000
```

Recommended Hermes commands:

```bash
deploy/macmini/bootstrap.sh
deploy/macmini/start.sh
```

For macOS launch agent auto-start:

```bash
deploy/macmini/install_launch_agent.sh
```

## Environment

Copy `.env.example` or `deploy/macmini/wildidea.env.example` to `.env`.

Registration requires email verification. Configure SMTP in `.env` with `WILDIDEA_SMTP_HOST`, `WILDIDEA_SMTP_USERNAME`, and `WILDIDEA_SMTP_PASSWORD`; otherwise new users cannot request verification codes.

Do not commit `.env`, databases, logs, generated outputs, or zip packages.

## Useful Commands

Run tests:

```bash
python -m pytest -q
```

Run real API smoke test manually:

```bash
WILDIDEA_RUN_REAL_API_SMOKE=1 python -m pytest tests/test_real_api_smoke.py -q -s
```

## Project Layout

```text
skill/wildidea/           Standalone downloadable Codex skill
SKILL.md                  Root mirror of the skill entrypoint
docs/wildidea-skill.md    Root copy of the full skill workflow spec
src/wildidea/web/          Web backend and frontend
src/wildidea/pipeline.py   Idea generation pipeline
references/domains.json    Source mechanism pool
templates/poster.html      Generated poster template
deploy/macmini/            Mac mini and Hermes deployment scripts
tests/                     API, pipeline, and smoke tests
```

## License

MIT
