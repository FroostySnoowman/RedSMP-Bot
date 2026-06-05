import discord
import yaml
from discord.ext import commands
from cogs.events.helpers import account_age, format_roles, format_user, is_target_guild, member_count

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
ignore_bots = bool(data.get("Logging", {}).get("IGNORE_BOTS", True))

class MemberEventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ignore_bots = ignore_bots

    def should_ignore(self, user: discord.abc.User) -> bool:
        return self.ignore_bots and user.bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not is_target_guild(member.guild, guild_id) or self.should_ignore(member):
            return

        await self.bot.event_logger.log(
            "MEMBERS",
            "JOIN",
            "Member Joined",
            f"{member.mention} joined the server.",
            fields=[
                ("Member", format_user(member), True),
                ("Account Created", account_age(member), True),
                ("Member Count", member_count(member.guild), True),
            ],
            color=discord.Color.green(),
            payload={
                "guild_id": member.guild.id,
                "user_id": member.id,
                "member_count": member.guild.member_count,
            },
            guild=member.guild,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not is_target_guild(member.guild, guild_id) or self.should_ignore(member):
            return

        await self.bot.event_logger.log(
            "MEMBERS",
            "LEAVE",
            "Member Left",
            f"{member.mention} left the server.",
            fields=[
                ("Member", format_user(member), True),
                ("Roles", format_roles(member.roles), False),
                ("Member Count", member_count(member.guild), True),
                ("Joined", discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown", True),
            ],
            color=discord.Color.orange(),
            payload={
                "guild_id": member.guild.id,
                "user_id": member.id,
                "role_ids": [role.id for role in member.roles if not role.is_default()],
                "member_count": member.guild.member_count,
            },
            guild=member.guild,
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if not is_target_guild(guild, guild_id) or self.should_ignore(user):
            return

        await self.bot.event_logger.log(
            "MEMBERS",
            "BAN",
            "Member Banned",
            f"{user.mention} was banned.",
            fields=[
                ("Member", format_user(user), True),
                ("Account Created", account_age(user), True),
            ],
            color=discord.Color.red(),
            payload={
                "guild_id": guild.id,
                "user_id": user.id,
            },
            guild=guild,
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if not is_target_guild(guild, guild_id) or self.should_ignore(user):
            return

        await self.bot.event_logger.log(
            "MEMBERS",
            "UNBAN",
            "Member Unbanned",
            f"{user.mention} was unbanned.",
            fields=[
                ("Member", format_user(user), True),
                ("Account Created", account_age(user), True),
            ],
            color=discord.Color.green(),
            payload={
                "guild_id": guild.id,
                "user_id": user.id,
            },
            guild=guild,
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not is_target_guild(after.guild, guild_id) or self.should_ignore(after):
            return

        added_roles = [role for role in after.roles if role not in before.roles and not role.is_default()]
        removed_roles = [role for role in before.roles if role not in after.roles and not role.is_default()]

        if added_roles:
            await self.bot.event_logger.log(
                "MEMBERS",
                "ROLE_ADD",
                "Roles Added",
                f"{after.mention} received new roles.",
                fields=[
                    ("Member", format_user(after), True),
                    ("Roles Added", format_roles(added_roles), False),
                    ("Current Roles", format_roles(after.roles), False),
                ],
                color=discord.Color.blurple(),
                payload={
                    "guild_id": after.guild.id,
                    "user_id": after.id,
                    "added_role_ids": [role.id for role in added_roles],
                },
                guild=after.guild,
            )

        if removed_roles:
            await self.bot.event_logger.log(
                "MEMBERS",
                "ROLE_REMOVE",
                "Roles Removed",
                f"{after.mention} lost roles.",
                fields=[
                    ("Member", format_user(after), True),
                    ("Roles Removed", format_roles(removed_roles), False),
                    ("Current Roles", format_roles(after.roles), False),
                ],
                color=discord.Color.orange(),
                payload={
                    "guild_id": after.guild.id,
                    "user_id": after.id,
                    "removed_role_ids": [role.id for role in removed_roles],
                },
                guild=after.guild,
            )

        if before.timed_out_until != after.timed_out_until:
            now = discord.utils.utcnow()

            if after.timed_out_until and after.timed_out_until > now:
                await self.bot.event_logger.log(
                    "MEMBERS",
                    "TIMEOUT_ADD",
                    "Member Timed Out",
                    f"{after.mention} was timed out.",
                    fields=[
                        ("Member", format_user(after), True),
                        ("Expires", discord.utils.format_dt(after.timed_out_until, "F"), True),
                        ("Expires In", discord.utils.format_dt(after.timed_out_until, "R"), True),
                    ],
                    color=discord.Color.red(),
                    payload={
                        "guild_id": after.guild.id,
                        "user_id": after.id,
                        "timed_out_until": int(after.timed_out_until.timestamp()),
                    },
                    guild=after.guild,
                )
            else:
                await self.bot.event_logger.log(
                    "MEMBERS",
                    "TIMEOUT_REMOVE",
                    "Member Timeout Removed",
                    f"{after.mention} is no longer timed out.",
                    fields=[
                        ("Member", format_user(after), True),
                    ],
                    color=discord.Color.green(),
                    payload={
                        "guild_id": after.guild.id,
                        "user_id": after.id,
                    },
                    guild=after.guild,
                )

        if before.nick != after.nick:
            await self.bot.event_logger.log(
                "MEMBERS",
                "NICKNAME_CHANGE",
                "Nickname Changed",
                f"{after.mention} changed their nickname.",
                fields=[
                    ("Member", format_user(after), True),
                    ("Before", before.nick or before.name, True),
                    ("After", after.nick or after.name, True),
                ],
                payload={
                    "guild_id": after.guild.id,
                    "user_id": after.id,
                    "before_nick": before.nick,
                    "after_nick": after.nick,
                },
                guild=after.guild,
            )

        if before.premium_since != after.premium_since and after.premium_since is not None:
            await self.bot.event_logger.log(
                "MEMBERS",
                "BOOST",
                "Server Boosted",
                f"{after.mention} boosted the server.",
                fields=[
                    ("Member", format_user(after), True),
                    ("Boosting Since", discord.utils.format_dt(after.premium_since, "F"), True),
                ],
                color=discord.Color.fuchsia(),
                payload={
                    "guild_id": after.guild.id,
                    "user_id": after.id,
                    "premium_since": int(after.premium_since.timestamp()),
                },
                guild=after.guild,
            )

async def setup(bot):
    await bot.add_cog(MemberEventsCog(bot), guilds=[discord.Object(id=guild_id)])