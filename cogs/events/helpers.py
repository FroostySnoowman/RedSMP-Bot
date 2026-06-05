import discord

def is_target_guild(guild: discord.Guild | None, guild_id: int) -> bool:
    return guild is not None and guild.id == guild_id

def format_user(user: discord.abc.User) -> str:
    return f"{user.mention} (`{user.id}`)"

def format_roles(roles: list[discord.Role]) -> str:
    filtered = [role for role in roles if not role.is_default()]

    if not filtered:
        return "None"

    return ", ".join(role.mention for role in filtered)

def account_age(user: discord.abc.User) -> str:
    return discord.utils.format_dt(user.created_at, "R")

def member_count(guild: discord.Guild) -> str:
    return str(guild.member_count or len(guild.members))

def audit_executor(entry: discord.AuditLogEntry) -> str:
    if entry.user is None:
        return "Unknown"

    return format_user(entry.user)

def audit_reason(entry: discord.AuditLogEntry) -> str:
    return entry.reason or "No reason provided."