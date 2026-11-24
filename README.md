# Week 5: CI/CD pipeline and a self-hosted LLM chat

A web chat where users talk to a language model that runs on my own CSC cPouta server (server A).
Every push to `main` is linted, tested and deployed automatically with GitHub Actions.

- Chat: http://195.148.21.16/viikko5/
- Documentation: http://195.148.21.16/viikko5/docs
- Health: http://195.148.21.16/viikko5/health (returns the commit SHA of the running version)

```
Browser → Nginx :80 (location /viikko5/) → Gunicorn + Flask 127.0.0.1:8005 (user viikko5)
                                              ├→ Ollama 127.0.0.1:11434 (gemma3:1b)
                                              └→ MariaDB, database viikko5chat
```

## Repository

| Path | Purpose |
|---|---|
| `chat/` | Flask application (`__init__.py`), Ollama client (`llm.py`), MariaDB storage (`store.py`), templates and static files |
| `wsgi.py` | Gunicorn entry point |
| `tests/` | pytest tests; the model and the database are mocked |
| `.github/workflows/ci-cd.yml` | CI (ruff + pytest on every push and PR) and CD (deploy on push to `main`) |
| `deploy/deploy.sh` | Deployment script, installed as `/usr/local/sbin/viikko5-deploy` |
| `deploy/viikko5.service` | systemd unit, runs the app as the non-login user `viikko5` |
| `deploy/nginx-viikko5.conf` | Nginx location for `/viikko5/`, installed as `/etc/nginx/snippets/viikko5.conf` |
| `deploy/sudoers-viikko5-deploy` | The only sudo rule of the `deploy` user |
| `deploy/viikko5.env.example` | Environment file template (the real one is only on the server) |
| `db/schema.sql` | Database and table |
| `db/users.example.sql` | Database user with `SELECT, INSERT` only (password is a placeholder) |
| `docs/evidence/` | Command output shown on the documentation page |

## Run the tests locally

```bash
python3 -m venv venv && . venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest -v
```

## One-time server setup (Ubuntu 26.04, as `ubuntu`)

```bash
# 0. Check resources and ports that are already in use
free -h; df -h /
sudo ss -ltnp
systemctl list-units --type=service --state=running

# 1. Ollama (listens on 127.0.0.1:11434 by default) and the model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3:1b

# 2. Users
sudo useradd --system --user-group --home-dir /opt/viikko5 --shell /usr/sbin/nologin viikko5
sudo adduser --disabled-password --gecos "" deploy
sudo -u deploy mkdir -p /home/deploy/incoming/viikko5

# 3. Database (schema + user with SELECT, INSERT only)
sudo mariadb < db/schema.sql
sudo mariadb      # then run db/users.example.sql with a real password

# 4. Environment file, readable only by root and the service user
sudo install -d -o root -g viikko5 -m 750 /etc/viikko5
sudo install -o root -g viikko5 -m 640 deploy/viikko5.env.example /etc/viikko5/viikko5.env
sudo nano /etc/viikko5/viikko5.env      # set DB_PASSWORD

# 5. Deployment script and sudo rule
sudo install -o root -g root -m 755 deploy/deploy.sh /usr/local/sbin/viikko5-deploy
sudo visudo -cf deploy/sudoers-viikko5-deploy
sudo install -o root -g root -m 440 deploy/sudoers-viikko5-deploy /etc/sudoers.d/viikko5-deploy

# 6. One line in the existing Nginx site, inside its server { } block:
#        include snippets/viikko5.conf;
sudo nano /etc/nginx/sites-available/default

# 7. SSH key pair only for GitHub Actions
ssh-keygen -t ed25519 -N "" -C "github-actions-viikko5" -f ~/gha_deploy
sudo install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
echo "restrict $(cat ~/gha_deploy.pub)" | sudo tee /home/deploy/.ssh/authorized_keys
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys && sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

GitHub → *Settings → Secrets and variables → Actions*:

| Name | Type | Value |
|---|---|---|
| `SSH_PRIVATE_KEY` | secret | contents of `~/gha_deploy` (then delete the file from the server) |
| `SSH_KNOWN_HOSTS` | secret | `195.148.21.16 ` + contents of `/etc/ssh/ssh_host_ed25519_key.pub` |
| `SERVER_HOST` | secret | `195.148.21.16` |
| `DEPLOY_ENABLED` | variable | `true` (turns on the deploy job once the server is ready) |

## Deployment

Push to `main`. The workflow runs ruff and pytest; if they pass, the deploy job copies the code with
rsync, runs `sudo /usr/local/sbin/viikko5-deploy <sha>` and checks that `/viikko5/health` returns the
new SHA. A failing test or a failing health check makes the run red and nothing is deployed.

Manual check on the server:

```bash
systemctl status viikko5 ollama --no-pager
curl -s http://127.0.0.1/viikko5/health
journalctl -u viikko5 -n 30 --no-pager
```

## Not in this repository

Passwords, the real environment file, private keys and SQL dumps are never committed (`.gitignore`).
If a secret ends up in a commit it is treated as leaked: it is replaced and the old one is removed from the server.
