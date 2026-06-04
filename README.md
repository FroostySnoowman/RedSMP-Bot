# RedSMP Bot

RedSMP Bot is a full-featured Discord server management bot built with Python and `discord.py`. It brings together the kinds of tools a community server needs day to day: verification, giveaways, tickets, applications, leveling, automod, anti-spam, and anti-nuke protection.

The project is designed as a practical, production-style Discord bot. Features are split into cogs, persistent data is stored with SQLite, and server-specific behavior is controlled through a YAML configuration file. It is built to be easy to run for a single server while still showing clean organization, async Python patterns, persistent views, slash commands, moderation safeguards, and image generation with Pillow.

## Features

- Verification panel with persistent button support.
- Giveaway system with button entries, SQLite persistence, winner drawing, paginated lists, stop/delete/finish controls, and automatic ending.
- Ticket system with configurable support/report/application flows, modal intake for short forms, text-question intake for longer forms, and private ticket channels.
- Leveling system with exponential XP, anti-spam cooldowns, level-up announcements, leaderboards, and generated rank cards.
- Automod with configurable word filters, regex filters, ignore lists, file logging, optional Discord log channel alerts, and infraction history.
- Security system with anti-spam tracking, audit-log based anti-nuke counters, role removal for compromised moderators/admins, critical logging, and notifications.
- Centralized SQLite database setup using `database.db`.
- Public-safe `example-config.yml` for setup and GitHub distribution.

## Setup

### 1. Install Python

Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/).

Check your version:

```bash
python --version
```

Depending on your system, you may need to use `python3` instead of `python`.

### 2. Clone The Project

```bash
git clone https://github.com/FroostySnoowman/RedSMP-Bot.git
cd "RedSMP Bot"
```

### 3. Create A Virtual Environment

macOS/Linux:

```bash
python -m venv venv
source venv/bin/activate
```

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Create Your Config

Copy the example config:

```bash
cp example-config.yml config.yml
```

On Windows:

```bash
copy example-config.yml config.yml
```

Then edit `config.yml` and fill in:

- `General.TOKEN`
- `General.GUILD_ID`
- role IDs
- channel IDs
- category IDs
- log channel IDs
- feature-specific settings

Keep `config.yml` private. It contains your bot token and server-specific IDs.

For a plain-language explanation of every setting, see [CONFIG.md](CONFIG.md).

## Creating The Discord Bot

### 1. Create An Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**.
3. Give it a name.
4. Open the application.

### 2. Create The Bot User

1. Go to **Bot**.
2. Click **Add Bot** if one does not already exist.
3. Click **Reset Token** or **Copy Token**.
4. Paste the token into `config.yml` under:

```yaml
General:
    TOKEN: "YOUR_BOT_TOKEN"
```

Never commit your real token to GitHub.

### 3. Enable Privileged Gateway Intents

In the Developer Portal, go to **Bot** and enable:

- Server Members Intent
- Message Content Intent
- Presence Intent, if Discord requires it for your selected intents

This bot listens to messages, handles moderation/security events, reads member state, and uses `discord.Intents.all()` in `main.py`.

## Inviting The Bot

1. In the Developer Portal, open your application.
2. Go to **OAuth2**.
3. Open **URL Generator**.
4. Under **Scopes**, select:
   - `bot`
   - `applications.commands`
5. Under **Bot Permissions**, select the permissions your enabled features need.

Recommended permissions:

- Administrator

**OR**

- View Channels
- Send Messages
- Embed Links
- Attach Files
- Read Message History
- Manage Messages
- Manage Channels
- Manage Roles
- Moderate Members
- Kick Members
- Ban Members
- View Audit Log
- Use Slash Commands

Copy the generated URL, open it in your browser, and invite the bot to your server.

Make sure the bot role is high enough in the role list to manage the roles/users it needs to moderate. Anti-nuke role removal can only remove roles below the bot’s top role.

## Running The Bot

Start the bot:

```bash
python main.py
```

The bot will:

- Check/create SQLite tables.
- Load all cogs.
- Sync slash commands.
- Start listening for Discord events.

If slash commands do not appear immediately, restart Discord or wait for command sync. This project syncs commands globally and to the configured guild.

### Production Start Script

For a timestamped runtime log on Linux or a VPS, use:

```bash
chmod +x start.sh
./start.sh
```

Logs are written to:

```text
logs/main/YYYYMMDDHHMMSS-main.log
logs/error.log
```

`start.sh` activates `venv/`, runs `main.py`, and keeps the process in the foreground from systemd’s perspective by waiting on the Python process.

## VPS Deployment

These steps assume a Linux VPS (Ubuntu or Debian).

### 1. Install System Packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### 2. Create A Deploy User

```bash
sudo useradd -r -m -s /bin/bash redsmp
```

### 3. Install The Bot

```bash
sudo mkdir -p /bots/redsmp-bot
sudo chown redsmp:redsmp /bots/redsmp-bot
sudo -u redsmp git clone <your-repository-url> /bots/redsmp-bot
cd /bots/redsmp-bot
```

Set up the virtual environment and config as the deploy user:

```bash
sudo -u redsmp python3 -m venv venv
sudo -u redsmp venv/bin/pip install -r requirements.txt
sudo -u redsmp cp example-config.yml config.yml
sudo -u redsmp nano config.yml
```

Fill in `config.yml` with your bot token, guild ID, and server-specific IDs.

### 4. Install The Systemd Service

Edit `redsmp-bot.service` if your install path or user is different. The defaults assume:

- Install directory: `/bots/redsmp-bot`
- Service user: `redsmp`

```bash
sudo cp redsmp-bot.service /etc/systemd/system/redsmp-bot.service
sudo chmod +x /bots/redsmp-bot/start.sh
sudo chown -R redsmp:redsmp /bots/redsmp-bot
sudo systemctl daemon-reload
```

### 5. Enable And Start

```bash
sudo systemctl enable redsmp-bot
sudo systemctl start redsmp-bot
sudo systemctl status redsmp-bot
```

### 6. View Logs

Runtime output from `start.sh`:

```bash
ls -lt /bots/redsmp-bot/logs/main/
tail -f /bots/redsmp-bot/logs/main/<latest-log-file>
```

Startup errors:

```bash
tail -f /bots/redsmp-bot/logs/error.log
```

Service control:

```bash
sudo systemctl restart redsmp-bot
sudo systemctl stop redsmp-bot
sudo journalctl -u redsmp-bot -f
```

### 7. Update After Pulling Changes

```bash
cd /bots/redsmp-bot
sudo -u redsmp git pull
sudo -u redsmp venv/bin/pip install -r requirements.txt
sudo systemctl restart redsmp-bot
```

## Configuration Notes

### General

`General` controls the bot token, guild ID, embed color, status, and activity.

### Tickets

`Tickets` controls support/report/application ticket types. Ticket types can have any number of questions:

- 5 or fewer questions use a Discord modal.
- More than 5 questions use text-based questions in the created ticket channel.

### Leveling

`Leveling` controls XP gain, cooldowns, level-up announcements, ignored roles/channels, and rank card colors.

### Automod

`Automod` controls content filters:

- Word filters
- Regex filters
- Message deletion
- Warnings
- Timeouts
- File logs
- Optional Discord log channel

### Security

`Security` controls behavior-based protection:

- Anti-spam message tracking
- Duplicate message tracking
- Mention spam tracking
- Anti-nuke audit-log tracking
- Critical role removal
- Timeouts
- File logs
- Optional Discord log channel
- Optional direct notifications

## Database

The bot uses SQLite and creates `database.db` automatically.

`database.db` is ignored by Git and should not be uploaded. It contains server data such as giveaway entries, ticket records, leveling data, automod infractions, and security events.

## Logs

`start.sh` writes bot runtime output to:

```text
logs/main/YYYYMMDDHHMMSS-main.log
logs/error.log
```

Automod and security can write logs to:

```text
logs/automod.log
logs/security.log
```

The `logs/` directory should not be committed if it contains real moderation data.

## Development Notes

- Add new Discord features as cogs under `cogs/commands/`.
- Add database setup in `cogs/functions/sqlite.py`.
- Keep secrets in `config.yml`.
- Keep public defaults in `example-config.yml`.
- Run a syntax check before deploying:

```bash
python -m py_compile main.py cogs/functions/sqlite.py cogs/commands/*.py
```