import discord
import aiosqlite
import yaml
import json
import time
from collections import defaultdict, deque
from datetime import timedelta, timezone
from pathlib import Path
from discord import app_commands
from discord.ext import commands
from cogs.functions.sqlite import DATABASE_PATH, security

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
security_config = data.get("Security", {})

def current_timestamp() -> int:
    return int(time.time())

def threshold_reached(count: int, threshold: int) -> bool:
    return threshold > 0 and count >= threshold

class SecurityEventsView(discord.ui.View):
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

class SecurityCog(commands.Cog):
    security_group = app_commands.Group(name="security", description="View security settings and events.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = security_config
        self.enabled = bool(self.config.get("ENABLED", True))
        self.log_file = Path(self.config.get("LOG_FILE", "logs/security.log"))
        self.log_channel_id = int(self.config.get("LOG_CHANNEL_ID", 0))
        self.notify_user_ids = set(self.config.get("NOTIFY_USER_IDS", []))
        self.trusted_user_ids = set(self.config.get("TRUSTED_USER_IDS", []))
        self.trusted_role_ids = set(self.config.get("TRUSTED_ROLE_IDS", []))
        self.ignored_channel_ids = set(self.config.get("IGNORED_CHANNEL_IDS", []))
        self.exempt_owners = bool(self.config.get("EXEMPT_OWNERS", True))
        self.spam_config = self.config.get("ANTI_SPAM", {})
        self.nuke_config = self.config.get("ANTI_NUKE", {})
        self.spam_windows = defaultdict(deque)

    async def initialize(self):
        await security()
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def base_embed(self, title: str, description: str | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=discord.Color.from_str(embed_color))

    async def is_trusted(self, member: discord.Member | discord.User) -> bool:
        if member.id in self.trusted_user_ids or member.id == self.bot.user.id:
            return True

        if self.exempt_owners and await self.bot.is_owner(member):
            return True

        if isinstance(member, discord.Member):
            return any(role.id in self.trusted_role_ids for role in member.roles)

        return False

    async def should_ignore_message(self, message: discord.Message) -> bool:
        if not self.enabled or not self.spam_config.get("ENABLED", True) or message.guild is None or message.author.bot:
            return True

        if message.channel.id in self.ignored_channel_ids:
            return True

        if not isinstance(message.author, discord.Member):
            return True

        return await self.is_trusted(message.author)

    def prune_spam_window(self, user_id: int, now: int, window_seconds: int):
        window = self.spam_windows[user_id]

        while window and now - window[0]["created_at"] > window_seconds:
            window.popleft()

        return window

    def spam_match(self, user_id: int, content: str, mention_count: int) -> str | None:
        now = current_timestamp()
        window_seconds = int(self.spam_config.get("WINDOW_SECONDS", 10))
        max_messages = int(self.spam_config.get("MAX_MESSAGES", 6))
        duplicate_limit = int(self.spam_config.get("DUPLICATE_MESSAGE_LIMIT", 3))
        max_mentions = int(self.spam_config.get("MAX_MENTIONS", 5))
        window = self.prune_spam_window(user_id, now, window_seconds)
        normalized = content.strip().casefold()
        window.append({"created_at": now, "content": normalized})

        if threshold_reached(len(window), max_messages):
            return "MESSAGE_SPAM"

        if normalized:
            duplicate_count = sum(1 for item in window if item["content"] == normalized)

            if threshold_reached(duplicate_count, duplicate_limit):
                return "DUPLICATE_SPAM"

        if threshold_reached(mention_count, max_mentions):
            return "MENTION_SPAM"

        return None

    async def increment_counter(self, guild_id: int, user_id: int, event_type: str, window_seconds: int) -> tuple[int, bool]:
        now = current_timestamp()

        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM security_counters WHERE guild_id = ? AND user_id = ? AND event_type = ?", (guild_id, user_id, event_type)) as cursor:
                row = await cursor.fetchone()

            if row is None or now - row["window_started_at"] > window_seconds:
                count = 1
                await db.execute("INSERT OR REPLACE INTO security_counters (guild_id, user_id, event_type, count, window_started_at) VALUES (?, ?, ?, ?, ?)", (guild_id, user_id, event_type, count, now))
            else:
                count = row["count"] + 1
                await db.execute("UPDATE security_counters SET count = ? WHERE guild_id = ? AND user_id = ? AND event_type = ?", (count, guild_id, user_id, event_type))

            await db.commit()

        threshold = int(self.nuke_config.get("THRESHOLDS", {}).get(event_type, 0))
        return count, threshold_reached(count, threshold)

    async def save_event(self, guild_id: int, user_id: int, event_type: str, target_id: int | None, action_taken: str, details: dict):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("INSERT INTO security_events (guild_id, user_id, event_type, target_id, action_taken, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (guild_id, user_id, event_type, target_id, action_taken, json.dumps(details, ensure_ascii=False), current_timestamp()))
            await db.commit()

    async def write_file_log(self, payload: dict):
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        with self.log_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    async def send_log_embed(self, guild: discord.Guild, title: str, description: str, payload: dict):
        channel = self.bot.get_channel(self.log_channel_id) if self.log_channel_id else None

        if channel is not None:
            embed = self.base_embed(title, description)
            embed.add_field(name="Event", value=payload.get("event_type", "Unknown"), inline=True)
            embed.add_field(name="Action", value=payload.get("action_taken", "None"), inline=True)
            embed.add_field(name="User ID", value=str(payload.get("user_id")), inline=True)
            await channel.send(embed=embed)

        for user_id in self.notify_user_ids:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)

            if user is not None:
                try:
                    await user.send(f"Security alert in **{guild.name}**: {description}")
                except discord.HTTPException:
                    pass

    async def log_security_event(self, guild: discord.Guild, user_id: int, event_type: str, target_id: int | None, action_taken: str, details: dict, critical: bool = False):
        payload = {
            "created_at": current_timestamp(),
            "guild_id": guild.id,
            "user_id": user_id,
            "event_type": event_type,
            "target_id": target_id,
            "action_taken": action_taken,
            "details": details,
            "critical": critical,
        }
        await self.save_event(guild.id, user_id, event_type, target_id, action_taken, details)
        await self.write_file_log(payload)
        await self.send_log_embed(guild, "Security Alert" if critical else "Security Event", f"`{event_type}` triggered for <@{user_id}>.", payload)

    async def remove_member_roles(self, member: discord.Member) -> list[int]:
        removed_roles = []

        for role in member.roles:
            if role.is_default() or role.managed:
                continue

            if role >= member.guild.me.top_role:
                continue

            try:
                await member.remove_roles(role, reason="Security anti-nuke threshold reached")
                removed_roles.append(role.id)
            except discord.HTTPException:
                pass

        return removed_roles

    async def apply_critical_action(self, member: discord.Member, event_type: str, details: dict) -> str:
        actions = []

        if self.nuke_config.get("REMOVE_ROLES", True):
            removed_roles = await self.remove_member_roles(member)
            actions.append(f"removed_roles:{len(removed_roles)}")
            details["removed_role_ids"] = removed_roles

        if self.nuke_config.get("TIMEOUT", True):
            try:
                await member.timeout(timedelta(seconds=int(self.nuke_config.get("TIMEOUT_SECONDS", 3600))), reason=f"Security anti-nuke threshold reached: {event_type}")
                actions.append("timeout")
            except discord.HTTPException:
                actions.append("timeout_failed")

        return ", ".join(actions) if actions else "logged"

    async def find_audit_entry(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int | None = None):
        try:
            async for entry in guild.audit_logs(limit=6, action=action):
                age = (discord.utils.utcnow() - entry.created_at.astimezone(timezone.utc)).total_seconds()

                if age > 15:
                    continue

                if target_id is not None and getattr(entry.target, "id", None) != target_id:
                    continue

                return entry
        except discord.HTTPException:
            return None

        return None

    async def process_nuke_event(self, guild: discord.Guild, event_type: str, action: discord.AuditLogAction, target_id: int | None = None, extra_details: dict | None = None):
        if not self.enabled or not self.nuke_config.get("ENABLED", True):
            return

        entry = await self.find_audit_entry(guild, action, target_id)

        if entry is None or entry.user is None:
            return

        member = guild.get_member(entry.user.id)

        if member is None or await self.is_trusted(member):
            return

        window_seconds = int(self.nuke_config.get("WINDOW_SECONDS", 60))
        count, triggered = await self.increment_counter(guild.id, member.id, event_type, window_seconds)
        details = extra_details or {}
        details["count"] = count
        details["audit_reason"] = entry.reason
        details["target_id"] = target_id

        if triggered:
            action_taken = await self.apply_critical_action(member, event_type, details)
            await self.log_security_event(guild, member.id, event_type, target_id, action_taken, details, True)
        else:
            await self.log_security_event(guild, member.id, event_type, target_id, "tracked", details)

    async def handle_spam_event(self, message: discord.Message, event_type: str):
        actions = []

        if self.spam_config.get("DELETE_MESSAGE", True):
            try:
                await message.delete()
                actions.append("delete")
            except discord.HTTPException:
                actions.append("delete_failed")

        if self.spam_config.get("TIMEOUT", True) and isinstance(message.author, discord.Member):
            try:
                await message.author.timeout(
                    timedelta(seconds=int(self.spam_config.get("TIMEOUT_SECONDS", 300))),
                    reason=f"Security anti-spam triggered: {event_type}",
                )
                actions.append("timeout")
            except discord.HTTPException:
                actions.append("timeout_failed")

        details = {
            "content": message.content,
            "channel_id": message.channel.id,
            "mention_count": len(message.mentions) + len(message.role_mentions),
        }
        await self.log_security_event(message.guild, message.author.id, event_type, message.id, ", ".join(actions) if actions else "tracked", details, True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if await self.should_ignore_message(message):
            return

        mention_count = len(message.mentions) + len(message.role_mentions)
        event_type = self.spam_match(message.author.id, message.content, mention_count)

        if event_type is not None:
            await self.handle_spam_event(message, event_type)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self.process_nuke_event(guild, "MEMBER_BAN", discord.AuditLogAction.ban, user.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.process_nuke_event(member.guild, "MEMBER_KICK", discord.AuditLogAction.kick, member.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.timed_out_until == after.timed_out_until:
            return

        await self.process_nuke_event(after.guild, "MEMBER_TIMEOUT", discord.AuditLogAction.member_update, after.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self.process_nuke_event(channel.guild, "CHANNEL_DELETE", discord.AuditLogAction.channel_delete, channel.id, {"channel_name": channel.name})

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self.process_nuke_event(channel.guild, "CHANNEL_CREATE", discord.AuditLogAction.channel_create, channel.id, {"channel_name": channel.name})

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self.process_nuke_event(role.guild, "ROLE_DELETE", discord.AuditLogAction.role_delete, role.id, {"role_name": role.name})

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self.process_nuke_event(role.guild, "ROLE_CREATE", discord.AuditLogAction.role_create, role.id, {"role_name": role.name})

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        await self.process_nuke_event(after.guild, "ROLE_UPDATE", discord.AuditLogAction.role_update, after.id, {"role_name": after.name})

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await self.process_nuke_event(channel.guild, "WEBHOOK_CREATE", discord.AuditLogAction.webhook_create, None, {"channel_id": channel.id})

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return

        await self.process_nuke_event(member.guild, "BOT_ADD", discord.AuditLogAction.bot_add, member.id)

    async def fetch_events(self, guild_id: int, user_id: int | None = None):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row

            if user_id is None:
                async with db.execute("SELECT * FROM security_events WHERE guild_id = ? ORDER BY created_at DESC LIMIT 50", (guild_id,)) as cursor:
                    return await cursor.fetchall()

            async with db.execute("SELECT * FROM security_events WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 50", (guild_id, user_id)) as cursor:
                return await cursor.fetchall()

    @security_group.command(name="status", description="Show security system status.")
    @app_commands.checks.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        embed = self.base_embed("Security Status")
        embed.add_field(name="Enabled", value=str(self.enabled), inline=True)
        embed.add_field(name="Anti-Spam", value=str(self.spam_config.get("ENABLED", True)), inline=True)
        embed.add_field(name="Anti-Nuke", value=str(self.nuke_config.get("ENABLED", True)), inline=True)
        embed.add_field(name="Log File", value=str(self.log_file), inline=False)
        embed.add_field(name="Log Channel", value=f"<#{self.log_channel_id}>" if self.log_channel_id else "Not configured", inline=False)
        embed.add_field(name="Notify Users", value=str(len(self.notify_user_ids)), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="events", description="List recent security events.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Optional member to filter events by.")
    async def events(self, interaction: discord.Interaction, member: discord.Member | None = None):
        rows = await self.fetch_events(interaction.guild_id, member.id if member else None)

        if not rows:
            await interaction.response.send_message("No security events found.", ephemeral=True)
            return

        embeds = []

        for index in range(0, len(rows), 5):
            page_rows = rows[index:index + 5]
            page_number = (index // 5) + 1
            page_count = ((len(rows) - 1) // 5) + 1
            embed = self.base_embed("Security Events")
            embed.set_footer(text=f"Page {page_number}/{page_count}")

            for row in page_rows:
                embed.add_field(name=f"#{row['id']} - {row['event_type']}", value=f"User: <@{row['user_id']}>\nAction: {row['action_taken']}\nWhen: <t:{row['created_at']}:R>", inline=False)

            embeds.append(embed)

        await interaction.response.send_message(embed=embeds[0], view=SecurityEventsView(embeds), ephemeral=True)

async def setup(bot):
    cog = SecurityCog(bot)
    await cog.initialize()
    await bot.add_cog(cog, guilds=[discord.Object(id=guild_id)])