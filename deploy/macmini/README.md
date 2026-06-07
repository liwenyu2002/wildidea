# WildIdea Mac mini Deployment

Fastest route: run WildIdea as a local uvicorn service on the Mac mini, then point Hermes at `http://127.0.0.1:8000`.

## 1. Copy Code To Mac Mini

From this machine:

```bash
rsync -az --delete \
  --exclude '.git' \
  --exclude '.pytest_cache' \
  --exclude '.DS_Store' \
  --exclude 'outputs' \
  --exclude 'wildidea.db' \
  /Users/liwenyu/wildidea/ macmini:~/wildidea/
```

Then SSH into the Mac mini:

```bash
ssh macmini
cd ~/wildidea
```

## 2. Bootstrap

```bash
deploy/macmini/bootstrap.sh
```

Edit `.env` and fill the real API key and secret:

```bash
nano .env
```

Also fill SMTP settings in `.env`; registration verification codes are sent by email.

## 3. Start Once

```bash
deploy/macmini/start.sh
```

Check locally on the Mac mini:

```bash
curl http://127.0.0.1:8000/
```

## 4. Keep It Running

In another terminal on the Mac mini:

```bash
deploy/macmini/install_launch_agent.sh
```

Useful commands:

```bash
launchctl list | grep wildidea
tail -f logs/wildidea.err.log
launchctl stop com.wildidea.web
launchctl start com.wildidea.web
```

## 5. Hermes

Give Hermes this upstream:

```text
http://127.0.0.1:8000
```

If Hermes asks for headers, keep or pass:

```text
Host
X-Forwarded-For
X-Forwarded-Proto
```

For HTTPS/domain, let Hermes keep handling TLS and route your domain to the local upstream above.
