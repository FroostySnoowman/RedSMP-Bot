import discord
import yaml
from discord import app_commands
from discord.ext import commands

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
members_role_id = data["Roles"]["MEMBERS_ROLE_ID"]

class Verification(discord.ui.View):
    def __init__(self, cog: "PanelsCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(emoji='👍', label='Verify Here', style=discord.ButtonStyle.green, custom_id='verification:1')
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        members_role = interaction.guild.get_role(members_role_id)

        if members_role is None:
            await interaction.response.send_message("Verification is not configured correctly. Ask an admin to set `Roles.MEMBERS_ROLE_ID`.", ephemeral=True)
            return

        if members_role in interaction.user.roles:
            embed = discord.Embed(title="Verification Failed", description="You're already verified!", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.user.add_roles(members_role)
        embed = discord.Embed(title="Verification Successful", description="You've been verified!", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

        if interaction.guild is not None:
            await self.cog.bot.event_logger.log(
                "VERIFICATION",
                "SUCCESS",
                "Member Verified",
                f"{interaction.user.mention} completed verification.",
                fields=[
                    ("User", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                    ("Role", members_role.mention, True),
                    ("Channel", interaction.channel.mention if interaction.channel else "Unknown", True),
                ],
                payload={
                    "guild_id": interaction.guild.id,
                    "user_id": interaction.user.id,
                    "role_id": members_role.id,
                    "channel_id": interaction.channel.id if interaction.channel else None,
                },
                guild=interaction.guild,
            )

class PanelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.add_view(Verification(self))

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="verification", description="Sends the verification panel!")
    async def verification(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Verification", description=f"Click the button below to become verified!", color=discord.Color.from_str(embed_color))
        await interaction.channel.send(embed=embed, view=Verification(self))
        await interaction.response.send_message("Sent!", ephemeral=True)

        if interaction.guild is not None:
            await self.bot.event_logger.log(
                "VERIFICATION",
                "PANEL_SENT",
                "Verification Panel Sent",
                f"{interaction.user.mention} sent the verification panel in {interaction.channel.mention}.",
                fields=[
                    ("Moderator", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                    ("Channel", f"{interaction.channel.mention} (`{interaction.channel.id}`)", True),
                    ("Role", f"<@&{members_role_id}>", True),
                ],
                payload={
                    "guild_id": interaction.guild.id,
                    "moderator_id": interaction.user.id,
                    "channel_id": interaction.channel.id,
                    "role_id": members_role_id,
                },
                guild=interaction.guild,
            )

async def setup(bot):
    await bot.add_cog(PanelsCog(bot), guilds=[discord.Object(id=guild_id)])