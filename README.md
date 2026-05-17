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