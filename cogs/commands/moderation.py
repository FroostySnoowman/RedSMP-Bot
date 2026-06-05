import discord
import yaml
from discord import app_commands
from discord.ext import commands

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
staff_role_ids = data.get("Tickets", {}).get("STAFF_ROLE_IDS", [])

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.staff_role_ids = staff_role_ids

    def base_embed(self, title: str, description: str | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=discord.Color.from_str(embed_color))

    def staff_roles(self, guild: discord.Guild) -> list[discord.Role]:
        roles = []

        for role_id in self.staff_role_ids:
            role = guild.get_role(role_id)

            if role is not None:
                roles.append(role)

        return roles

    async def lock_channel(self, channel: discord.TextChannel, moderator: discord.Member) -> bool:
        guild = channel.guild
        reason = f"Channel locked by {moderator}"

        try:
            await channel.set_permissions(guild.default_role, send_messages=False, reason=reason)
            await channel.set_permissions(guild.me, send_messages=True, read_message_history=True, reason=reason)

            for role in self.staff_roles(guild):
                await channel.set_permissions(role, send_messages=True, read_message_history=True, reason=reason)
        except discord.Forbidden:
            return False
        except discord.HTTPException:
            return False

        return True

    async def unlock_channel(self, channel: discord.TextChannel, moderator: discord.Member) -> bool:
        guild = channel.guild
        reason = f"Channel unlocked by {moderator}"

        try:
            await channel.set_permissions(guild.default_role, send_messages=None, reason=reason)

            for role in self.staff_roles(guild):
                await channel.set_permissions(role, send_messages=None, reason=reason)
        except discord.Forbidden:
            return False
        except discord.HTTPException:
            return False

        return True

    @app_commands.command(name="lockchat", description="Lock this channel so only staff can send messages.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def lockchat(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            return

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not self.staff_role_ids:
            await interaction.response.send_message("No staff roles are configured in `Tickets.STAFF_ROLE_IDS`.", ephemeral=True)
            return

        locked = await self.lock_channel(interaction.channel, interaction.user)

        if not locked:
            await interaction.response.send_message("I could not lock this channel. Check my permissions.", ephemeral=True)
            return

        staff_mentions = ", ".join(role.mention for role in self.staff_roles(interaction.guild)) or "configured staff"
        channel_embed = self.base_embed("Channel Locked", f"This channel was locked by {interaction.user.mention}.\n\nOnly staff can send messages: {staff_mentions}")
        await interaction.response.send_message("Channel locked.", ephemeral=True)
        await interaction.channel.send(embed=channel_embed)

    @app_commands.command(name="unlockchat", description="Unlock this channel and restore normal send permissions.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def unlockchat(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        unlocked = await self.unlock_channel(interaction.channel, interaction.user)

        if not unlocked:
            await interaction.response.send_message("I could not unlock this channel. Check my permissions.", ephemeral=True)
            return

        channel_embed = self.base_embed("Channel Unlocked", f"This channel was unlocked by {interaction.user.mention}.")
        await interaction.response.send_message("Channel unlocked.", ephemeral=True)
        await interaction.channel.send(embed=channel_embed)

    @app_commands.command(name="purge", description="Delete multiple messages from this channel.")
    @app_commands.describe(amount="How many recent messages to check (1-100).", user="Only delete messages from this member.")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100], user: discord.Member | None = None):
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("This command can only be used in text channels or threads.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        def check(message: discord.Message) -> bool:
            if message.pinned:
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

        if deleted_count < amount:
            description += "\n\nSome messages may have been skipped because they are pinned or older than 14 days."

        if user is not None:
            description += f"\n\nFilter: {user.mention}"

        await interaction.followup.send(embed=self.base_embed("Purge Complete", description), ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModerationCog(bot), guilds=[discord.Object(id=guild_id)])