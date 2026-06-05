import discord
import yaml
from discord import app_commands
from discord.ext import commands

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def base_embed(self, title: str, description: str | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=discord.Color.from_str(embed_color))

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