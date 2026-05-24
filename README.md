# Botec

Telegram bot for managing user bills and payment reminders.

## Local Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

Fill `.env` locally before running:

```env
BOT_TOKEN=your_token_here
ADMIN_IDS=123456789
CURRENCY=RUB
DB_PATH=data/db.json
```

Never commit `.env`, local databases, virtual environments, logs, or Python cache files.

## Server Deployment

Deployment flow:

```text
local laptop -> GitHub main branch -> GitHub Actions -> VPS -> systemd
```

The bot runs on the server as:

```text
botec.service
```

Server secrets live outside the repository:

```text
/etc/telegram-bots/botec.env
```

Persistent data lives under:

```text
/opt/telegram-bots/apps/botec/shared/db.json
```

Useful commands:

```bash
sudo systemctl status botec
sudo journalctl -u botec -f
sudo systemctl restart botec
```
