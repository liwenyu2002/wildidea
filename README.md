# WildIdea Web

WildIdea Web is a FastAPI web app for generating cross-domain innovation ideas. It includes user accounts, credits, invitation codes, task history, live card progress, feedback collection, admin review, and Excel export.

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
src/wildidea/web/          Web backend and frontend
src/wildidea/pipeline.py   Idea generation pipeline
references/domains.json    Source mechanism pool
templates/poster.html      Generated poster template
deploy/macmini/            Mac mini and Hermes deployment scripts
tests/                     API, pipeline, and smoke tests
```

## License

MIT
