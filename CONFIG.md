# Configuration Guide

This guide explains every setting in `config.yml` in plain language. You do not need to be a programmer to use it, but you should be comfortable editing a text file and copying numbers from Discord.

## Before You Start

### Which file to edit

- **`example-config.yml`** — Safe template with placeholders. This is what GitHub shows publicly.
- **`config.yml`** — Your real settings. Copy the example file and rename it:

```bash
cp example-config.yml config.yml
```

Never upload `config.yml` to GitHub. It contains your bot token.

### How the file is formatted

`config.yml` uses **YAML** format:

- Use **spaces**, not tabs, for indentation.
- Keep the colon and spacing style the same as the example (`KEY: value`).
- Text in quotes is usually safer when it contains special characters.
- Lists use a dash on each line, like:

```yaml
IGNORED_CHANNEL_IDS:
    - 1234567890123456789
    - 9876543210987654321
```

If the bot fails to start after editing, check for typos, wrong indentation, or missing quotes.

### Finding Discord IDs

Most settings need a **numeric ID** (a long number).

1. Open Discord → **User Settings** → **Advanced**.
2. Turn on **Developer Mode**.
3. Right-click a server, channel, role, or user → **Copy ID**.

Paste that number into `config.yml` with no quotes for plain numbers, or in quotes if the example uses quotes.

**`0` usually means “not set” or “use the default.”** For channel and category IDs, `0` often means the bot picks a sensible default (for example, the channel where the command was used).

---

## General

Controls the bot’s connection to Discord and how it appears online.

| Setting | What it does |
|--------|----------------|
| `TOKEN` | Your bot’s secret password from the [Discord Developer Portal](https://discord.com/developers/applications). **Never share this.** |
| `ACTIVITY` | What type of status activity the bot shows. |
| `DOING_ACTIVITY` | The text shown next to the activity (for example, “RedSMP”). |
| `STREAMING_ACTIVITY_TWITCH_URL` | Only used when `ACTIVITY` is `streaming`. Must be a Twitch link like `https://twitch.tv/yourname`. |
| `STATUS` | The colored dot: online, idle, dnd, or invisible. |
| `EMBED_COLOR` | Default color for bot embeds, as a hex code like `#9C27B0`. |
| `GUILD_ID` | The ID of **your Discord server** the bot is built for. |

### `ACTIVITY` options

| Value | What members see |
|--------|------------------|
| `playing` | Playing … |
| `watching` | Watching … |
| `listening` | Listening to … |
| `streaming` | Streaming … (requires Twitch URL) |

### `STATUS` options

| Value | Meaning |
|--------|---------|
| `online` | Green |
| `idle` | Yellow |
| `dnd` | Red (Do Not Disturb) |
| `invisible` | Appears offline |

### Example

```yaml
General:
    TOKEN: "paste_your_bot_token_here"
    ACTIVITY: "watching"
    DOING_ACTIVITY: "RedSMP"
    STREAMING_ACTIVITY_TWITCH_URL: ""
    STATUS: "online"
    EMBED_COLOR: "#9C27B0"
    GUILD_ID: 1234567890123456789
```

---

## Roles

Used by features that need to know about member roles.

| Setting | What it does |
|--------|----------------|
| `MEMBERS_ROLE_ID` | Role given when someone uses the **verification** button. Usually your “Member” or “Verified” role. |

### Example

```yaml
Roles:
    MEMBERS_ROLE_ID: 1234567890123456789
```

---

## Tickets

Lets members open private ticket channels by clicking buttons on a panel. Staff can see those channels and help.

| Setting | What it does |
|--------|----------------|
| `STAFF_ROLE_IDS` | Roles that can see and manage all ticket channels. List one or more role IDs. |
| `LOG_CHANNEL_ID` | Channel where ticket close events are logged. `0` = disabled. |
| `DEFAULT_CATEGORY_ID` | Category where new tickets are created if a ticket type does not set its own. `0` = no category. |
| `TYPES` | The different ticket buttons (support, report, application, etc.). |

### Each ticket type (`TYPES`)

Under `TYPES`, each block (like `support:`) is one button on the ticket panel.

| Setting | What it does |
|--------|----------------|
| `LABEL` | Button label members see. |
| `DESCRIPTION` | Short text on the panel embed under that button. |
| `BUTTON_STYLE` | Button color: `green`, `red`, `blurple`, `gray`, or `grey`. |
| `CATEGORY_ID` | Category for this ticket type only. `0` = use `DEFAULT_CATEGORY_ID`. |
| `CHANNEL_PREFIX` | Start of the channel name (for example `support-username`). |
| `QUESTIONS` | Questions asked before the ticket opens. |

### How questions work

- **5 or fewer questions** → shown in a pop-up form (modal).
- **More than 5 questions** → asked one at a time in the new ticket channel.

You can add or remove ticket types by copying a block and changing the name (for example `billing:`).

### Example

```yaml
Tickets:
    STAFF_ROLE_IDS:
        - 1111111111111111111
    LOG_CHANNEL_ID: 2222222222222222222
    DEFAULT_CATEGORY_ID: 3333333333333333333

    TYPES:
        support:
            LABEL: "General Support"
            DESCRIPTION: "Get help from staff."
            BUTTON_STYLE: "green"
            CATEGORY_ID: 0
            CHANNEL_PREFIX: "support"
            QUESTIONS:
                - "What do you need help with?"
```

**Staff command:** `/tickets panel` (admin) posts the panel.

---

## Leveling

Members earn XP by chatting. They level up over time, get rank cards, and can earn roles at certain levels.

| Setting | What it does |
|--------|----------------|
| `ENABLED` | `true` = leveling on, `false` = off. |
| `MIN_XP_PER_MESSAGE` | Smallest XP amount per valid message. |
| `MAX_XP_PER_MESSAGE` | Largest XP amount per valid message (bot picks randomly between min and max). |
| `COOLDOWN_SECONDS` | Seconds between XP gains per user (stops spam-for-XP). |
| `BASE_XP` | XP needed for early levels; works with multiplier below. |
| `XP_MULTIPLIER` | How much harder each level gets. Higher = slower progression. |
| `LEVEL_UP_CHANNEL_ID` | Channel for level-up announcements. `0` = announce in the channel they leveled up in. |
| `IGNORED_CHANNEL_IDS` | Channels where chatting does **not** give XP. |
| `IGNORED_ROLE_IDS` | Roles that do **not** earn XP. |
| `REMOVE_PREVIOUS_LEVEL_ROLES` | If `true`, when someone earns a new level role, older level roles from this list are removed. |
| `LEVEL_ROLES` | Roles given at specific levels. |
| `RANK_CARD` | Colors and size of the `/level rank` image. |

### Level roles (`LEVEL_ROLES`)

Map a **level number** to a **role ID**:

```yaml
LEVEL_ROLES:
    5: 1111111111111111111
    10: 2222222222222222222
    25: 3333333333333333333
```

Use `0` as the role ID to skip that level (no role for level 10 in the example above).

### Rank card colors (`RANK_CARD`)

All colors use hex format like `#1f1f2e`.

| Setting | What it controls |
|--------|-------------------|
| `WIDTH` / `HEIGHT` | Image size in pixels. |
| `BACKGROUND_COLOR` | Card background. |
| `ACCENT_COLOR` | XP bar fill color. |
| `TEXT_COLOR` | Main text. |
| `MUTED_TEXT_COLOR` | Secondary text. |
| `BAR_BACKGROUND_COLOR` | Empty part of the XP bar. |

### Commands

- `/level rank` — Your rank card (or someone else’s).
- `/level leaderboard` — Top members by level.

---

## Automod

Automatically checks messages for blocked words or patterns and can delete messages, warn, timeout, or log.

| Setting | What it does |
|--------|----------------|
| `ENABLED` | Master switch for automod. |
| `LOG_FILE` | File on disk for automod logs (usually leave as `logs/automod.log`). |
| `LOG_CHANNEL_ID` | Discord channel for automod alerts. `0` = no channel alerts. |
| `BYPASS_ADMINS` | If `true`, server administrators are not filtered. |
| `BYPASS_MANAGE_MESSAGES` | If `true`, people with “Manage Messages” are not filtered. |
| `IGNORED_CHANNEL_IDS` | Channels automod does not check. |
| `IGNORED_ROLE_IDS` | Roles automod does not check. |
| `IGNORED_USER_IDS` | Specific users automod never checks. |
| `WORD_FILTERS` | List of word-based rules. |
| `REGEX_FILTERS` | List of pattern-based rules (advanced). |

### Word filter (`WORD_FILTERS`)

Each rule is one block in the list.

| Setting | What it does |
|--------|----------------|
| `NAME` | Label for logs (for example “Blocked Words”). |
| `MODE` | How to match words (see table below). |
| `WORDS` | List of words or phrases to match. |
| `ACTIONS` | What happens when matched (see below). |
| `TIMEOUT_SECONDS` | How long to timeout if `TIMEOUT` is enabled. |

**`MODE` options:**

| Mode | Meaning |
|------|---------|
| `exact` | Whole word only ( “bad” won’t match “badly” ). |
| `contains` | Message contains the text anywhere. |
| `normalized_contains` | Like contains, but ignores accents and similar tricks. |

**`ACTIONS` options (each `true` or `false`):**

| Action | Effect |
|--------|--------|
| `DELETE` | Delete the message. |
| `WARN` | Send a short warning in the channel. |
| `TIMEOUT` | Timeout the member. |
| `LOG` | Write to log file and log channel (if set). |

### Regex filter (`REGEX_FILTERS`)

For advanced users. Uses a **pattern** instead of a plain word list.

| Setting | What it does |
|--------|----------------|
| `NAME` | Label for logs. |
| `PATTERN` | Pattern to match (leave unchanged unless you know regex). |
| `FLAGS` | Usually `i` for case-insensitive. |
| `ACTIONS` | Same as word filters. |
| `TIMEOUT_SECONDS` | Timeout length if timeout is enabled. |

The default rule blocks Discord invite links.

### Commands

- `/automod status` — Shows if automod is on and how many rules exist.
- `/automod infractions @member` — Recent automod history for a member.

---

## Security

Protects the server from chat spam and from moderators or compromised accounts doing too many destructive actions too quickly (“anti-nuke”).

| Setting | What it does |
|--------|----------------|
| `ENABLED` | Master switch for the security system. |
| `LOG_FILE` | File on disk for security logs. |
| `LOG_CHANNEL_ID` | Channel for security alerts. `0` = disabled. |
| `NOTIFY_USER_IDS` | User IDs to DM when a critical security event happens. |
| `TRUSTED_USER_IDS` | Users who are never punished by security. |
| `TRUSTED_ROLE_IDS` | Roles that are never punished by security. |
| `IGNORED_CHANNEL_IDS` | Channels where anti-spam does not run. |
| `EXEMPT_OWNERS` | If `true`, bot owners are trusted. |

### Anti-spam (`ANTI_SPAM`)

Stops users from flooding chat.

| Setting | What it does |
|--------|----------------|
| `ENABLED` | Turn anti-spam on or off. |
| `WINDOW_SECONDS` | Time window to measure spam (for example 10 seconds). |
| `MAX_MESSAGES` | Max messages allowed in that window. |
| `DUPLICATE_MESSAGE_LIMIT` | How many identical messages in a row trigger spam. |
| `MAX_MENTIONS` | Max @mentions in one message before it counts as spam. |
| `DELETE_MESSAGE` | Delete the spam message. |
| `TIMEOUT` | Timeout the user. |
| `TIMEOUT_SECONDS` | Length of timeout in seconds. |

### Anti-nuke (`ANTI_NUKE`)

Tracks dangerous moderation actions (bans, kicks, deleting channels, etc.). If someone does too many in a short time, the bot can remove their roles and timeout them.

| Setting | What it does |
|--------|----------------|
| `ENABLED` | Turn anti-nuke on or off. |
| `WINDOW_SECONDS` | Time window to count actions (for example 60 seconds). |
| `REMOVE_ROLES` | Remove all roles the bot can remove from the offender. |
| `TIMEOUT` | Timeout the offender. |
| `TIMEOUT_SECONDS` | How long the timeout lasts (3600 = 1 hour). |
| `THRESHOLDS` | How many of each action is allowed before triggering. |

**`THRESHOLDS` — what each name means:**

| Name | Counts when someone… |
|------|----------------------|
| `MEMBER_BAN` | Bans members |
| `MEMBER_KICK` | Kicks members |
| `MEMBER_TIMEOUT` | Times out members |
| `CHANNEL_DELETE` | Deletes channels |
| `CHANNEL_CREATE` | Creates channels |
| `ROLE_DELETE` | Deletes roles |
| `ROLE_CREATE` | Creates roles |
| `ROLE_UPDATE` | Edits roles |
| `WEBHOOK_CREATE` | Creates webhooks |
| `BOT_ADD` | Adds a bot to the server |

Lower numbers = stricter (triggers sooner). Example: `CHANNEL_DELETE: 2` means deleting 2 channels within the window can trigger protection.

**Important:** The bot needs a high role position and permissions such as **View Audit Log**, **Manage Roles**, and **Moderate Members** for this to work.

### Commands

- `/security status` — Overview of security settings.
- `/security events @member` — Recent security events (optional member filter).

---

## Quick reference: common values

| You want… | Set this to… |
|-----------|----------------|
| Disable a channel setting | `0` |
| Empty list | `[]` |
| Turn a feature off | `ENABLED: false` |
| Trust your mods’ role | Add role ID under `TRUSTED_ROLE_IDS` or `STAFF_ROLE_IDS` |
| Stricter anti-nuke | Lower the numbers under `THRESHOLDS` |
| Slower leveling | Raise `XP_MULTIPLIER` or raise `COOLDOWN_SECONDS` |
| Faster leveling | Lower `XP_MULTIPLIER` or raise `MAX_XP_PER_MESSAGE` |

---

## After changing config

1. Save `config.yml`.
2. Restart the bot (stop and start `main.py`, or `sudo systemctl restart redsmp-bot` on a VPS).
3. If something does not work, double-check IDs and that the bot’s role is high enough in the role list.

For installation and VPS deployment, see [README.md](README.md).
