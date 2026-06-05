import discord
import yaml
from discord.ext import commands
from cogs.events.helpers import audit_executor, audit_reason, format_user, is_target_guild

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]

AUDIT_EVENT_MAP = {
    discord.AuditLogAction.kick: ("MEMBER_KICK", "Member Kicked", discord.Color.orange()),
    discord.AuditLogAction.ban: ("MEMBER_BAN", "Member Banned", discord.Color.red()),
    discord.AuditLogAction.unban: ("MEMBER_UNBAN", "Member Unbanned", discord.Color.green()),
    discord.AuditLogAction.member_role_update: ("MEMBER_ROLE_UPDATE", "Member Roles Updated", discord.Color.blurple()),
    discord.AuditLogAction.member_update: ("MEMBER_UPDATE", "Member Updated", discord.Color.blurple()),
    discord.AuditLogAction.channel_create: ("CHANNEL_CREATE", "Channel Created", discord.Color.green()),
    discord.AuditLogAction.channel_delete: ("CHANNEL_DELETE", "Channel Deleted", discord.Color.red()),
    discord.AuditLogAction.channel_update: ("CHANNEL_UPDATE", "Channel Updated", discord.Color.gold()),
    discord.AuditLogAction.role_create: ("ROLE_CREATE", "Role Created", discord.Color.green()),
    discord.AuditLogAction.role_delete: ("ROLE_DELETE", "Role Deleted", discord.Color.red()),
    discord.AuditLogAction.role_update: ("ROLE_UPDATE", "Role Updated", discord.Color.gold()),
    discord.AuditLogAction.message_delete: ("MESSAGE_DELETE", "Message Deleted", discord.Color.orange()),
    discord.AuditLogAction.message_bulk_delete: ("MESSAGE_BULK_DELETE", "Messages Bulk Deleted", discord.Color.red()),
    discord.AuditLogAction.invite_create: ("INVITE_CREATE", "Invite Created", discord.Color.green()),
    discord.AuditLogAction.invite_delete: ("INVITE_DELETE", "Invite Deleted", discord.Color.orange()),
    discord.AuditLogAction.webhook_create: ("WEBHOOK_CREATE", "Webhook Created", discord.Color.red()),
    discord.AuditLogAction.webhook_update: ("WEBHOOK_UPDATE", "Webhook Updated", discord.Color.gold()),
    discord.AuditLogAction.webhook_delete: ("WEBHOOK_DELETE", "Webhook Deleted", discord.Color.red()),
    discord.AuditLogAction.emoji_create: ("EMOJI_CREATE", "Emoji Created", discord.Color.green()),
    discord.AuditLogAction.emoji_update: ("EMOJI_UPDATE", "Emoji Updated", discord.Color.gold()),
    discord.AuditLogAction.emoji_delete: ("EMOJI_DELETE", "Emoji Deleted", discord.Color.red()),
    discord.AuditLogAction.overwrite_create: ("OVERWRITE_CREATE", "Permission Overwrite Created", discord.Color.blurple()),
    discord.AuditLogAction.overwrite_update: ("OVERWRITE_UPDATE", "Permission Overwrite Updated", discord.Color.gold()),
    discord.AuditLogAction.overwrite_delete: ("OVERWRITE_DELETE", "Permission Overwrite Deleted", discord.Color.orange()),
    discord.AuditLogAction.member_move: ("MEMBER_MOVE", "Member Moved", discord.Color.blurple()),
    discord.AuditLogAction.member_disconnect: ("MEMBER_DISCONNECT", "Member Disconnected", discord.Color.orange()),
    discord.AuditLogAction.bot_add: ("BOT_ADD", "Bot Added", discord.Color.red()),
    discord.AuditLogAction.thread_create: ("THREAD_CREATE", "Thread Created", discord.Color.green()),
    discord.AuditLogAction.thread_delete: ("THREAD_DELETE", "Thread Deleted", discord.Color.red()),
    discord.AuditLogAction.thread_update: ("THREAD_UPDATE", "Thread Updated", discord.Color.gold()),
    discord.AuditLogAction.guild_update: ("GUILD_UPDATE", "Server Updated", discord.Color.gold()),
    discord.AuditLogAction.sticker_create: ("STICKER_CREATE", "Sticker Created", discord.Color.green()),
    discord.AuditLogAction.sticker_update: ("STICKER_UPDATE", "Sticker Updated", discord.Color.gold()),
    discord.AuditLogAction.sticker_delete: ("STICKER_DELETE", "Sticker Deleted", discord.Color.red()),
}

class AuditEventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def target_label(self, entry: discord.AuditLogEntry) -> str:
        target = entry.target

        if target is None:
            return "Unknown"

        if isinstance(target, (discord.Member, discord.User)):
            return format_user(target)

        if isinstance(target, discord.Object):
            return f"`{target.id}`"

        return str(target)

    def change_summary(self, entry: discord.AuditLogEntry) -> str:
        if not entry.changes:
            return "No change details available."

        lines = []

        for change in entry.changes:
            before = change.old_value
            after = change.new_value
            lines.append(f"**{change.attribute}:** `{before}` → `{after}`")

        return "\n".join(lines[:12]) or "No change details available."

    def extra_fields(self, entry: discord.AuditLogEntry) -> list[tuple[str, str, bool]]:
        fields = [
            ("Executor", audit_executor(entry), True),
            ("Target", self.target_label(entry), True),
            ("Reason", audit_reason(entry), False),
        ]

        if entry.action == discord.AuditLogAction.message_bulk_delete and entry.extra:
            fields.append(("Count", str(getattr(entry.extra, "count", "Unknown")), True))

        if entry.action in {discord.AuditLogAction.message_delete, discord.AuditLogAction.message_bulk_delete} and entry.extra:
            channel = getattr(entry.extra, "channel", None)

            if channel is not None:
                fields.append(("Channel", channel.mention, True))

        if entry.changes:
            fields.append(("Changes", self.change_summary(entry), False))

        return fields

    def is_timeout_change(self, entry: discord.AuditLogEntry) -> bool:
        if entry.action != discord.AuditLogAction.member_update:
            return False

        return any(change.attribute == "timed_out_until" for change in entry.changes)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        if not is_target_guild(entry.guild, guild_id):
            return

        if entry.user is not None and entry.user.id == self.bot.user.id:
            return

        if entry.action == discord.AuditLogAction.member_update and self.is_timeout_change(entry):
            event = "MEMBER_TIMEOUT"
            title = "Member Timed Out"
            color = discord.Color.red()
            target = entry.target
            description = f"{format_user(target)} was timed out by staff." if isinstance(target, discord.Member) else "A member was timed out."

            await self.bot.event_logger.log(
                "AUDIT",
                event,
                title,
                description,
                fields=self.extra_fields(entry),
                color=color,
                payload={
                    "guild_id": entry.guild.id,
                    "audit_action": entry.action.name,
                    "executor_id": entry.user.id if entry.user else None,
                    "target_id": getattr(entry.target, "id", None),
                    "reason": entry.reason,
                },
                guild=entry.guild,
            )
            return

        mapped = AUDIT_EVENT_MAP.get(entry.action)

        if mapped is None:
            return

        event, title, color = mapped
        target = entry.target
        description = f"{title} in **{entry.guild.name}**."

        if isinstance(target, (discord.Member, discord.User)):
            description = f"{format_user(target)} was affected by **{entry.action.name.replace('_', ' ')}**."

        await self.bot.event_logger.log(
            "AUDIT",
            event,
            title,
            description,
            fields=self.extra_fields(entry),
            color=color,
            payload={
                "guild_id": entry.guild.id,
                "audit_action": entry.action.name,
                "executor_id": entry.user.id if entry.user else None,
                "target_id": getattr(entry.target, "id", None),
                "reason": entry.reason,
            },
            guild=entry.guild,
        )

async def setup(bot):
    await bot.add_cog(AuditEventsCog(bot), guilds=[discord.Object(id=guild_id)])