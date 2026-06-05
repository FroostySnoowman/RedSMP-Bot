import discord
import json
import time
from pathlib import Path

def current_timestamp() -> int:
    return int(time.time())

class EventLogger:
    def __init__(self, bot: discord.Client, config: dict, embed_color: str) -> None:
        self.bot = bot
        self.config = config
        self.embed_color = embed_color
        logging_config = config.get("Logging", {})
        self.enabled = bool(logging_config.get("ENABLED", True))
        self.default_channel_id = int(logging_config.get("DEFAULT_CHANNEL_ID", 0) or 0)
        self.log_to_files = bool(logging_config.get("LOG_TO_FILES", True))
        self.log_directory = Path(logging_config.get("LOG_DIRECTORY", "logs"))
        self.channels = logging_config.get("CHANNELS", {})
        self.files = logging_config.get("FILES", {})
        self.events = logging_config.get("EVENTS", {})
        self.legacy = logging_config.get("LEGACY", {})
        security_logging = logging_config.get("SECURITY", {})
        self.notify_user_ids = set(security_logging.get("NOTIFY_USER_IDS", []) or config.get("Security", {}).get("NOTIFY_USER_IDS", []))
        self.log_directory.mkdir(parents=True, exist_ok=True)

    def is_event_enabled(self, category: str, event: str) -> bool:
        category_events = self.events.get(category.upper(), {})

        if not category_events:
            return True

        return bool(category_events.get(event.upper(), True))

    def resolve_channel_id(self, category: str) -> int:
        category_key = category.upper()
        channel_id = int(self.channels.get(category_key, 0) or 0)

        if channel_id:
            return channel_id

        if self.default_channel_id:
            return self.default_channel_id

        if category_key == "TICKETS" and self.legacy.get("USE_TICKETS_LOG_CHANNEL", True):
            return int(self.config.get("Tickets", {}).get("LOG_CHANNEL_ID", 0) or 0)

        if category_key == "AUTOMOD" and self.legacy.get("USE_AUTOMOD_LOG_CHANNEL", True):
            return int(self.config.get("Automod", {}).get("LOG_CHANNEL_ID", 0) or 0)

        if category_key == "SECURITY" and self.legacy.get("USE_SECURITY_LOG_CHANNEL", True):
            return int(self.config.get("Security", {}).get("LOG_CHANNEL_ID", 0) or 0)

        return 0

    def resolve_file_path(self, category: str) -> Path:
        filename = self.files.get(category.upper(), f"{category.lower()}.log")
        return self.log_directory / filename

    def build_embed(self, title: str, description: str | None = None, fields: list[tuple[str, str, bool]] | None = None, color: discord.Color | None = None) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color or discord.Color.from_str(self.embed_color), timestamp=discord.utils.utcnow())

        for name, value, inline in fields or []:
            embed.add_field(name=name, value=value[:1024], inline=inline)

        return embed

    def write_file_log(self, category: str, payload: dict):
        file_path = self.resolve_file_path(category)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"logged_at": current_timestamp(), **payload}

        with file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def notify_security_users(self, guild: discord.Guild, message: str):
        for user_id in self.notify_user_ids:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)

            if user is None:
                continue

            try:
                await user.send(f"Security alert in **{guild.name}**: {message}")
            except discord.HTTPException:
                pass

    async def log(self, category: str, event: str, title: str, description: str | None = None, fields: list[tuple[str, str, bool]] | None = None, color: discord.Color | None = None, file: discord.File | None = None, payload: dict | None = None, guild: discord.Guild | None = None, notify_critical: bool = False):
        if not self.enabled or not self.is_event_enabled(category, event):
            return

        log_payload = {
            "category": category.upper(),
            "event": event.upper(),
            "title": title,
            "description": description,
            "fields": {name: value for name, value, _inline in (fields or [])},
            **(payload or {}),
        }

        if self.log_to_files:
            self.write_file_log(category, log_payload)

        channel_id = self.resolve_channel_id(category)

        if channel_id:
            channel = self.bot.get_channel(channel_id)

            if channel is not None:
                embed = self.build_embed(title, description, fields, color)

                try:
                    await channel.send(embed=embed, file=file)
                except discord.HTTPException:
                    pass

        if notify_critical and guild is not None and description:
            await self.notify_security_users(guild, description)