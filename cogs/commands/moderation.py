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

    def can_manage_role(self, guild: discord.Guild, role: discord.Role) -> bool:
        if role.is_default():
            return guild.me.guild_permissions.manage_roles

        return guild.me.top_role > role and guild.me.guild_permissions.manage_roles

    async def apply_send_lock(self, channel: discord.TextChannel, target: discord.Role | discord.Member, locked: bool, reason: str):
        overwrite = channel.overwrites_for(target)

        if locked:
            overwrite.send_messages = False
            overwrite.send_messages_in_threads = False
            overwrite.create_public_threads = False
            overwrite.create_private_threads = False
        else:
            overwrite.send_messages = None
            overwrite.send_messages_in_threads = None
            overwrite.create_public_threads = None
            overwrite.create_private_threads = None

        await channel.set_permissions(target, overwrite=overwrite, reason=reason)

    async def apply_staff_access(self, channel: discord.TextChannel, role: discord.Role, reason: str):
        overwrite = channel.overwrites_for(role)
        overwrite.view_channel = True
        overwrite.read_message_history = True
        overwrite.send_messages = True
        overwrite.send_messages_in_threads = True
        await channel.set_permissions(role, overwrite=overwrite, reason=reason)

    async def lock_channel(self, channel: discord.TextChannel, moderator: discord.Member) -> tuple[bool, list[str]]:
        guild = channel.guild
        reason = f"Channel locked by {moderator}"
        staff_ids = set(self.lock_staff_role_ids)
        errors = []

        try:
            if self.lock_deny_everyone:
                if self.can_manage_role(guild, guild.default_role):
                    await self.apply_send_lock(channel, guild.default_role, True, reason)
                else:
                    errors.append("@everyone")

            if self.lock_deny_members_role:
                members_role = self.members_role(guild)

                if members_role is None:
                    errors.append(f"Members role not found (`{self.members_role_id}`)")
                elif members_role.id in staff_ids:
                    pass
                elif self.can_manage_role(guild, members_role):
                    await self.apply_send_lock(channel, members_role, True, reason)
                else:
                    errors.append(f"{members_role.name} (move the bot role above it)")

            overwrite = channel.overwrites_for(guild.me)
            overwrite.view_channel = True
            overwrite.read_message_history = True
            overwrite.send_messages = True
            overwrite.send_messages_in_threads = True
            await channel.set_permissions(guild.me, overwrite=overwrite, reason=reason)

            for role in self.staff_roles(guild):
                if self.can_manage_role(guild, role):
                    await self.apply_staff_access(channel, role, reason)
                else:
                    errors.append(f"{role.name} (move the bot role above it)")
        except discord.Forbidden:
            return False, ["missing channel permissions"]
        except discord.HTTPException:
            return False, ["discord API error"]

        return len(errors) == 0, errors

    async def unlock_channel(self, channel: discord.TextChannel, moderator: discord.Member) -> tuple[bool, list[str]]:
        guild = channel.guild
        reason = f"Channel unlocked by {moderator}"
        staff_ids = set(self.lock_staff_role_ids)
        errors = []

        try:
            if self.lock_deny_everyone:
                if self.can_manage_role(guild, guild.default_role):
                    await self.apply_send_lock(channel, guild.default_role, False, reason)
                else:
                    errors.append("@everyone")

            if self.lock_deny_members_role:
                members_role = self.members_role(guild)

                if members_role is not None and members_role.id not in staff_ids:
                    if self.can_manage_role(guild, members_role):
                        await self.apply_send_lock(channel, members_role, False, reason)
                    else:
                        errors.append(f"{members_role.name} (move the bot role above it)")

            for role in self.staff_roles(guild):
                if self.can_manage_role(guild, role):
                    await self.apply_send_lock(channel, role, False, reason)
                else:
                    errors.append(f"{role.name} (move the bot role above it)")
        except discord.Forbidden:
            return False, ["missing channel permissions"]
        except discord.HTTPException:
            return False, ["discord API error"]

        return len(errors) == 0, errors

    @app_commands.command(name="lockchat", description="Lock this channel so only staff can send messages.")
    @app_commands.checks.bot_has_permissions(manage_channels=True, manage_roles=True)
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

        locked, errors = await self.lock_channel(interaction.channel, interaction.user)

        if not locked:
            error_text = ", ".join(errors)
            await interaction.response.send_message(f"I could not fully lock this channel: {error_text}", ephemeral=True)
            return

        staff_mentions = ", ".join(role.mention for role in self.staff_roles(interaction.guild)) or "configured staff"
        channel_embed = self.base_embed("Channel Locked", f"This channel was locked by {interaction.user.mention}.\n\nOnly staff can send messages: {staff_mentions}")
        await interaction.response.send_message("Channel locked.", ephemeral=True)
        await interaction.channel.send(embed=channel_embed)

    @app_commands.command(name="unlockchat", description="Unlock this channel and restore normal send permissions.")
    @app_commands.checks.bot_has_permissions(manage_channels=True, manage_roles=True)
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

        unlocked, errors = await self.unlock_channel(interaction.channel, interaction.user)

        if not unlocked:
            error_text = ", ".join(errors)
            await interaction.response.send_message(f"I could not fully unlock this channel: {error_text}", ephemeral=True)
            return

        channel_embed = self.base_embed("Channel Unlocked", f"This channel was unlocked by {interaction.user.mention}.")
        await interaction.response.send_message("Channel unlocked.", ephemeral=True)
        await interaction.channel.send(embed=channel_embed)

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

async def setup(bot):
    await bot.add_cog(ModerationCog(bot), guilds=[discord.Object(id=guild_id)])