import discord
import yaml
from discord import app_commands
from discord.ext import commands

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
members_role_id = data.get("Roles", {}).get("MEMBERS_ROLE_ID", 0)
moderation_config = data.get("Moderation", {})
lockchat_config = moderation_config.get("LOCKCHAT", {})
purge_config = moderation_config.get("PURGE", {})

SEND_LOCK_DENY = {
    "send_messages": False,
    "send_messages_in_threads": False,
    "create_public_threads": False,
    "create_private_threads": False,
}

SEND_LOCK_CLEAR = {
    "send_messages": None,
    "send_messages_in_threads": None,
    "create_public_threads": None,
    "create_private_threads": None,
}

STAFF_SEND_ALLOW = {
    "view_channel": True,
    "read_message_history": True,
    "send_messages": True,
    "send_messages_in_threads": True,
}

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.members_role_id = members_role_id
        self.lockchat_enabled = lockchat_config.get("ENABLED", True)
        self.lock_allowed_role_ids = lockchat_config.get("ALLOWED_ROLE_IDS", [])
        self.lock_deny_everyone = lockchat_config.get("DENY_EVERYONE", True)
        self.lock_deny_members_role = lockchat_config.get("DENY_MEMBERS_ROLE", True)
        self.lock_staff_role_ids = lockchat_config.get("STAFF_ROLE_IDS", [])
        self.purge_enabled = purge_config.get("ENABLED", True)
        self.purge_allowed_role_ids = purge_config.get("ALLOWED_ROLE_IDS", [])
        self.purge_min_amount = purge_config.get("MIN_AMOUNT", 1)
        self.purge_max_amount = purge_config.get("MAX_AMOUNT", 100)
        self.purge_delete_pinned = purge_config.get("DELETE_PINNED", False)

    def base_embed(self, title: str, description: str | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=discord.Color.from_str(embed_color))

    def has_allowed_role(self, member: discord.Member, allowed_role_ids: list) -> bool:
        if not allowed_role_ids:
            return False

        allowed_ids = set(allowed_role_ids)
        return any(role.id in allowed_ids for role in member.roles)

    def can_use_lockchat(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True

        if self.lock_allowed_role_ids:
            return self.has_allowed_role(member, self.lock_allowed_role_ids)

        return member.guild_permissions.manage_channels

    def can_use_purge(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True

        if self.purge_allowed_role_ids:
            return self.has_allowed_role(member, self.purge_allowed_role_ids)

        return member.guild_permissions.manage_messages

    def staff_roles(self, guild: discord.Guild) -> list[discord.Role]:
        roles = []

        for role_id in self.lock_staff_role_ids:
            role = guild.get_role(role_id)

            if role is not None:
                roles.append(role)

        return roles

    def members_role(self, guild: discord.Guild) -> discord.Role | None:
        if not self.members_role_id:
            return None

        return guild.get_role(self.members_role_id)

    def can_edit_role(self, guild: discord.Guild, target: discord.Role | discord.Member) -> bool:
        if isinstance(target, discord.Member):
            return True

        if target.is_default():
            return guild.me.guild_permissions.manage_permissions

        return guild.me.top_role > target and guild.me.guild_permissions.manage_permissions

    def apply_overwrite_values(self, overwrites: dict, guild: discord.Guild, target: discord.Role | discord.Member, values: dict) -> str | None:
        if not self.can_edit_role(guild, target):
            name = getattr(target, "name", str(target))
            return name

        overwrite = overwrites.get(target, discord.PermissionOverwrite())

        for permission, value in values.items():
            setattr(overwrite, permission, value)

        if overwrite.is_empty():
            overwrites.pop(target, None)
        else:
            overwrites[target] = overwrite

        return None

    async def lock_channel(self, channel: discord.TextChannel, moderator: discord.Member) -> tuple[bool, list[str]]:
        guild = channel.guild
        reason = f"Channel locked by {moderator}"
        staff_ids = set(self.lock_staff_role_ids)
        warnings = []
        overwrites = dict(channel.overwrites)
        planned_changes = 0

        if self.lock_deny_everyone:
            warning = self.apply_overwrite_values(overwrites, guild, guild.default_role, SEND_LOCK_DENY)

            if warning:
                warnings.append(f"@{warning}")
            else:
                planned_changes += 1

        if self.lock_deny_members_role:
            members_role = self.members_role(guild)

            if members_role is None:
                warnings.append(f"Members role not found (`{self.members_role_id}`)")
            elif members_role.id in staff_ids:
                pass
            else:
                warning = self.apply_overwrite_values(overwrites, guild, members_role, SEND_LOCK_DENY)

                if warning:
                    warnings.append(f"{warning} (move the bot role above it)")
                else:
                    planned_changes += 1

        warning = self.apply_overwrite_values(overwrites, guild, guild.me, STAFF_SEND_ALLOW)

        if warning:
            warnings.append("bot role")
        else:
            planned_changes += 1

        for role in self.staff_roles(guild):
            warning = self.apply_overwrite_values(overwrites, guild, role, STAFF_SEND_ALLOW)

            if warning:
                warnings.append(f"{role.name} (move the bot role above it)")
            else:
                planned_changes += 1

        if planned_changes == 0:
            return False, warnings or ["nothing could be updated"]

        try:
            await channel.edit(overwrites=overwrites, reason=reason)
        except discord.Forbidden:
            return False, ["I do not have permission to edit this channel's permissions"]
        except discord.HTTPException:
            return False, ["Discord rejected the permission update"]

        return True, warnings

    async def unlock_channel(self, channel: discord.TextChannel, moderator: discord.Member) -> tuple[bool, list[str]]:
        guild = channel.guild
        reason = f"Channel unlocked by {moderator}"
        staff_ids = set(self.lock_staff_role_ids)
        warnings = []
        overwrites = dict(channel.overwrites)
        planned_changes = 0

        if self.lock_deny_everyone:
            warning = self.apply_overwrite_values(overwrites, guild, guild.default_role, SEND_LOCK_CLEAR)

            if warning:
                warnings.append(f"@{warning}")
            else:
                planned_changes += 1

        if self.lock_deny_members_role:
            members_role = self.members_role(guild)

            if members_role is not None and members_role.id not in staff_ids:
                warning = self.apply_overwrite_values(overwrites, guild, members_role, SEND_LOCK_CLEAR)

                if warning:
                    warnings.append(f"{members_role.name} (move the bot role above it)")
                else:
                    planned_changes += 1

        for role in self.staff_roles(guild):
            if role not in overwrites:
                continue

            warning = self.apply_overwrite_values(overwrites, guild, role, SEND_LOCK_CLEAR)

            if warning:
                warnings.append(f"{role.name} (move the bot role above it)")
            else:
                planned_changes += 1

        if planned_changes == 0:
            return True, warnings

        try:
            await channel.edit(overwrites=overwrites, reason=reason)
        except discord.Forbidden:
            return False, ["I do not have permission to edit this channel's permissions"]
        except discord.HTTPException:
            return False, ["Discord rejected the permission update"]

        return True, warnings

    @app_commands.command(name="lockchat", description="Lock this channel so only staff can send messages.")
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def lockchat(self, interaction: discord.Interaction):
        if not self.lockchat_enabled:
            await interaction.response.send_message("Lock chat is disabled in the config.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            return

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not self.can_use_lockchat(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if not self.lock_staff_role_ids:
            await interaction.response.send_message("No staff roles are configured in `Moderation.LOCKCHAT.STAFF_ROLE_IDS`.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        locked, warnings = await self.lock_channel(interaction.channel, interaction.user)

        if not locked:
            error_text = ", ".join(warnings)
            await interaction.followup.send(f"Could not lock this channel: {error_text}", ephemeral=True)
            return

        staff_mentions = ", ".join(role.mention for role in self.staff_roles(interaction.guild)) or "configured staff"
        channel_embed = self.base_embed(
            "Channel Locked",
            f"This channel was locked by {interaction.user.mention}.\n\nOnly staff can send messages: {staff_mentions}",
        )
        response = "Channel locked."

        if warnings:
            response += f"\n\nWarnings: {', '.join(warnings)}"

        await interaction.channel.send(embed=channel_embed)
        await interaction.followup.send(response, ephemeral=True)
        await self.bot.event_logger.log(
            "MODERATION",
            "CHANNEL_LOCK",
            "Channel Locked",
            f"{interaction.user.mention} locked {interaction.channel.mention}.",
            fields=[
                ("Moderator", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                ("Channel", f"{interaction.channel.mention} (`{interaction.channel.id}`)", True),
                ("Staff Roles", staff_mentions, False),
                ("Warnings", ", ".join(warnings) if warnings else "None", False),
            ],
            payload={
                "guild_id": interaction.guild.id,
                "moderator_id": interaction.user.id,
                "channel_id": interaction.channel.id,
                "staff_role_ids": self.lock_staff_role_ids,
                "warnings": warnings,
            },
            guild=interaction.guild,
        )

    @app_commands.command(name="unlockchat", description="Unlock this channel and restore normal send permissions.")
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def unlockchat(self, interaction: discord.Interaction):
        if not self.lockchat_enabled:
            await interaction.response.send_message("Lock chat is disabled in the config.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not self.can_use_lockchat(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        unlocked, warnings = await self.unlock_channel(interaction.channel, interaction.user)

        if not unlocked:
            error_text = ", ".join(warnings)
            await interaction.followup.send(f"Could not unlock this channel: {error_text}", ephemeral=True)
            return

        channel_embed = self.base_embed("Channel Unlocked", f"This channel was unlocked by {interaction.user.mention}.")
        response = "Channel unlocked."

        if warnings:
            response += f"\n\nWarnings: {', '.join(warnings)}"

        await interaction.channel.send(embed=channel_embed)
        await interaction.followup.send(response, ephemeral=True)
        await self.bot.event_logger.log(
            "MODERATION",
            "CHANNEL_UNLOCK",
            "Channel Unlocked",
            f"{interaction.user.mention} unlocked {interaction.channel.mention}.",
            fields=[
                ("Moderator", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                ("Channel", f"{interaction.channel.mention} (`{interaction.channel.id}`)", True),
                ("Warnings", ", ".join(warnings) if warnings else "None", False),
            ],
            payload={
                "guild_id": interaction.guild.id,
                "moderator_id": interaction.user.id,
                "channel_id": interaction.channel.id,
                "warnings": warnings,
            },
            guild=interaction.guild,
        )

    @app_commands.command(name="purge", description="Delete multiple messages from this channel.")
    @app_commands.describe(amount="How many recent messages to check.", user="Only delete messages from this member.")
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int, user: discord.Member | None = None):
        if not self.purge_enabled:
            await interaction.response.send_message("Purge is disabled in the config.", ephemeral=True)
            return

        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("This command can only be used in text channels or threads.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not self.can_use_purge(interaction.user):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if amount < self.purge_min_amount or amount > self.purge_max_amount:
            await interaction.response.send_message(f"Amount must be between **{self.purge_min_amount}** and **{self.purge_max_amount}**.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        def check(message: discord.Message) -> bool:
            if message.pinned and not self.purge_delete_pinned:
                return False

            if user is not None and message.author.id != user.id:
                return False

            return True

        try:
            deleted = await interaction.channel.purge(limit=amount, check=check, reason=f"Purged by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send("I do not have permission to delete messages in this channel.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send("Something went wrong while deleting messages.", ephemeral=True)
            return

        deleted_count = len(deleted)
        description = f"Deleted **{deleted_count}** message(s)."

        if deleted_count < amount and not self.purge_delete_pinned:
            description += "\n\nSome messages may have been skipped because they are pinned or older than 14 days."

        if user is not None:
            description += f"\n\nFilter: {user.mention}"

        await interaction.followup.send(embed=self.base_embed("Purge Complete", description), ephemeral=True)
        await self.bot.event_logger.log(
            "MODERATION",
            "PURGE",
            "Messages Purged",
            f"{interaction.user.mention} purged **{deleted_count}** message(s) in {interaction.channel.mention}.",
            fields=[
                ("Moderator", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                ("Channel", f"{interaction.channel.mention} (`{interaction.channel.id}`)", True),
                ("Deleted", str(deleted_count), True),
                ("Requested", str(amount), True),
                ("Target User", user.mention if user is not None else "All users", False),
            ],
            payload={
                "guild_id": interaction.guild.id,
                "moderator_id": interaction.user.id,
                "channel_id": interaction.channel.id,
                "deleted_count": deleted_count,
                "requested_amount": amount,
                "target_user_id": user.id if user is not None else None,
            },
            guild=interaction.guild,
        )

async def setup(bot):
    await bot.add_cog(ModerationCog(bot), guilds=[discord.Object(id=guild_id)])
