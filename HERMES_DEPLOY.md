# Hermes Deploy

Use this repository as a Python/FastAPI website.

## Install

```bash
deploy/macmini/bootstrap.sh
```

## Start

```bash
deploy/macmini/start.sh
```

## Upstream

```text
http://127.0.0.1:8000
```

Set secrets in `.env` on the server. Do not commit `.env`.

Registration requires SMTP settings in `.env`:

```text
WILDIDEA_SMTP_HOST=
WILDIDEA_SMTP_USERNAME=
WILDIDEA_SMTP_PASSWORD=
WILDIDEA_SMTP_FROM_EMAIL=
```
