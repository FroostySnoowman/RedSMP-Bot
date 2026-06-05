import discord
import unicodedata
import aiosqlite
import yaml
import json
import time
import re
from datetime import timedelta
from pathlib import Path
from discord import app_commands
from discord.ext import commands
from cogs.functions.sqlite import DATABASE_PATH, automod

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
automod_config = data.get("Automod", {})

def current_timestamp() -> int:
    return int(time.time())

def normalize_text(content: str) -> str:
    normalized = unicodedata.normalize("NFKD", content)
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return normalized.casefold()

def regex_flags(value: str) -> int:
    flags = 0

    if "i" in value:
        flags |= re.IGNORECASE

    if "m" in value:
        flags |= re.MULTILINE

    if "s" in value:
        flags |= re.DOTALL

    return flags

class InfractionsView(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.page = 0
        self.previous_page.disabled = True
        self.next_page.disabled = len(embeds) <= 1

    def update_buttons(self):
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= len(self.embeds) - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

class AutomodCog(commands.Cog):
    automod_group = app_commands.Group(name="automod", description="View automod settings and infractions.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = automod_config
        self.enabled = bool(self.config.get("ENABLED", True))
        self.log_file = Path(self.config.get("LOG_FILE", "logs/automod.log"))
        self.log_channel_id = int(self.config.get("LOG_CHANNEL_ID", 0))
        self.bypass_admins = bool(self.config.get("BYPASS_ADMINS", True))
        self.bypass_manage_messages = bool(self.config.get("BYPASS_MANAGE_MESSAGES", True))
        self.ignored_channel_ids = set(self.config.get("IGNORED_CHANNEL_IDS", []))
        self.ignored_role_ids = set(self.config.get("IGNORED_ROLE_IDS", []))
        self.ignored_user_ids = set(self.config.get("IGNORED_USER_IDS", []))
        self.word_filters = self.config.get("WORD_FILTERS", [])
        self.regex_filters = self.compile_regex_filters(self.config.get("REGEX_FILTERS", []))

    async def initialize(self):
        await automod()
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def base_embed(self, title: str, description: str | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=discord.Color.from_str(embed_color))

    def compile_regex_filters(self, filters: list[dict]) -> list[dict]:
        compiled_filters = []

        for automod_filter in filters:
            try:
                compiled = re.compile(
                    automod_filter.get("PATTERN", ""),
                    regex_flags(str(automod_filter.get("FLAGS", ""))),
                )
            except re.error:
                continue

            copied_filter = dict(automod_filter)
            copied_filter["COMPILED_PATTERN"] = compiled
            compiled_filters.append(copied_filter)

        return compiled_filters

    def should_ignore_message(self, message: discord.Message) -> bool:
        if not self.enabled or message.guild is None or message.author.bot:
            return True

        if message.author.id in self.ignored_user_ids or message.channel.id in self.ignored_channel_ids:
            return True

        if not isinstance(message.author, discord.Member):
            return True

        if self.bypass_admins and message.author.guild_permissions.administrator:
            return True

        if self.bypass_manage_messages and message.author.guild_permissions.manage_messages:
            return True

        return any(role.id in self.ignored_role_ids for role in message.author.roles)

    def word_matches(self, content: str, automod_filter: dict) -> tuple[str, str] | None:
        mode = str(automod_filter.get("MODE", "exact")).lower()
        words = [str(word) for word in automod_filter.get("WORDS", [])]
        normalized_content = normalize_text(content)

        for word in words:
            normalized_word = normalize_text(word)

            if mode == "contains" and word.casefold() in content.casefold():
                return word, word

            if mode == "normalized_contains" and normalized_word in normalized_content:
                return word, word

            if mode == "exact" and re.search(rf"\b{re.escape(normalized_word)}\b", normalized_content):
                return word, word

        return None

    def find_match(self, content: str) -> dict | None:
        for automod_filter in self.word_filters:
            match = self.word_matches(content, automod_filter)

            if match is not None:
                matched_value, display_value = match
                return {
                    "filter_type": "word",
                    "filter_name": automod_filter.get("NAME", "Word Filter"),
                    "matched_value": matched_value,
                    "display_value": display_value,
                    "actions": automod_filter.get("ACTIONS", {}),
                    "timeout_seconds": int(automod_filter.get("TIMEOUT_SECONDS", 300)),
                }

        for automod_filter in self.regex_filters:
            match = automod_filter["COMPILED_PATTERN"].search(content)

            if match is not None:
                return {
                    "filter_type": "regex",
                    "filter_name": automod_filter.get("NAME", "Regex Filter"),
                    "matched_value": match.group(0),
                    "display_value": match.group(0),
                    "actions": automod_filter.get("ACTIONS", {}),
                    "timeout_seconds": int(automod_filter.get("TIMEOUT_SECONDS", 300)),
                }

        return None

    def action_summary(self, actions: dict) -> str:
        enabled_actions = [name.lower() for name, enabled in actions.items() if enabled]
        return ", ".join(enabled_actions) if enabled_actions else "log"

    async def apply_actions(self, message: discord.Message, match: dict) -> str:
        actions = match["actions"]
        action_summary = self.action_summary(actions)

        if actions.get("DELETE", False):
            try:
                await message.delete()
            except discord.HTTPException:
                pass

        if actions.get("TIMEOUT", False) and isinstance(message.author, discord.Member):
            try:
                await message.author.timeout(timedelta(seconds=match["timeout_seconds"]), reason=f"Automod: {match['filter_name']}")
            except discord.HTTPException:
                pass

        if actions.get("WARN", False):
            try:
                await message.channel.send(f"{message.author.mention}, your message was flagged by automod.", delete_after=10)
            except discord.HTTPException:
                pass

        return action_summary

    async def save_infraction(self, message: discord.Message, match: dict, action: str):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("INSERT INTO automod_infractions (guild_id, user_id, channel_id, message_id, filter_type, filter_name, matched_value, action, content, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (message.guild.id, message.author.id, message.channel.id, message.id, match["filter_type"], match["filter_name"], match["matched_value"], action, message.content, current_timestamp()))
            await db.commit()

    async def handle_match(self, message: discord.Message, match: dict):
        action = await self.apply_actions(message, match)
        await self.save_infraction(message, match, action)

        if match["actions"].get("LOG", True):
            await self.bot.event_logger.log(
                "AUTOMOD",
                "FILTER_MATCH",
                "Automod Alert",
                f"{message.author.mention} triggered **{match['filter_name']}**.",
                fields=[
                    ("User", f"{message.author.mention} (`{message.author.id}`)", False),
                    ("Channel", message.channel.mention, True),
                    ("Filter", f"{match['filter_name']} ({match['filter_type']})", True),
                    ("Action", action, True),
                    ("Match", str(match["display_value"])[:1024], False),
                    ("Content", message.content[:1024] or "No content.", False),
                ],
                payload={
                    "guild_id": message.guild.id,
                    "channel_id": message.channel.id,
                    "message_id": message.id,
                    "user_id": message.author.id,
                    "filter_type": match["filter_type"],
                    "filter_name": match["filter_name"],
                    "matched_value": match["matched_value"],
                    "action": action,
                    "content": message.content,
                },
                guild=message.guild,
            )

    async def get_infractions(self, guild_id: int, user_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM automod_infractions WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 50", (guild_id, user_id)) as cursor:
                return await cursor.fetchall()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.should_ignore_message(message):
            return

        match = self.find_match(message.content)

        if match is None:
            return

        await self.handle_match(message, match)

    @automod_group.command(name="status", description="Show automod status.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def status(self, interaction: discord.Interaction):
        embed = self.base_embed("Automod Status")
        embed.add_field(name="Enabled", value=str(self.enabled), inline=True)
        embed.add_field(name="Word Filters", value=str(len(self.word_filters)), inline=True)
        embed.add_field(name="Regex Filters", value=str(len(self.regex_filters)), inline=True)
        logger = self.bot.event_logger
        automod_channel_id = logger.resolve_channel_id("AUTOMOD")
        embed.add_field(name="Log File", value=str(logger.resolve_file_path("AUTOMOD")), inline=False)
        embed.add_field(name="Log Channel", value=f"<#{automod_channel_id}>" if automod_channel_id else "Not configured", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod_group.command(name="infractions", description="List recent automod infractions for a member.")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(member="The member to view infractions for.")
    async def infractions(self, interaction: discord.Interaction, member: discord.Member):
        rows = await self.get_infractions(interaction.guild_id, member.id)

        if not rows:
            await interaction.response.send_message("That member has no automod infractions.", ephemeral=True)
            return

        embeds = []

        for index in range(0, len(rows), 5):
            page_rows = rows[index:index + 5]
            page_number = (index // 5) + 1
            page_count = ((len(rows) - 1) // 5) + 1
            embed = self.base_embed(f"Automod Infractions: {member.display_name}")
            embed.set_footer(text=f"Page {page_number}/{page_count}")

            for row in page_rows:
                embed.add_field(name=f"#{row['id']} - {row['filter_name']}", value=f"Type: {row['filter_type']}\nAction: {row['action']}\nMatch: {row['matched_value'][:200]}\nWhen: <t:{row['created_at']}:R>", inline=False)

            embeds.append(embed)

        await interaction.response.send_message(embed=embeds[0], view=InfractionsView(embeds), ephemeral=True)

async def setup(bot):
    cog = AutomodCog(bot)
    await cog.initialize()
    await bot.add_cog(cog, guilds=[discord.Object(id=guild_id)])