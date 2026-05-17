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
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(emoji='👍', label='Verify Here', style=discord.ButtonStyle.green, custom_id='verification:1')
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        members_role = interaction.guild.get_role(members_role_id)
        
        if members_role in interaction.user.roles:
            embed = discord.Embed(title="Verification Failed", description="You're already verified!", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.user.add_roles(members_role)
        embed = discord.Embed(title="Verification Successful", description="You've been verified!", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

class PanelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.add_view(Verification())

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="verification", description="Sends the verification panel!")
    async def verification(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Verification", description=f"Click the button below to become verified!", color=discord.Color.from_str(embed_color))
        await interaction.channel.send(embed=embed, view=Verification())
        await interaction.response.send_message("Sent!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PanelsCog(bot), guilds=[discord.Object(id=guild_id)])