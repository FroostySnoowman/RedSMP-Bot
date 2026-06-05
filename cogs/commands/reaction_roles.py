import discord
import yaml
from discord import app_commands
from discord.ext import commands

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
reaction_roles_config = data.get("ReactionRoles", {})

def button_style(style: str) -> discord.ButtonStyle:
    styles = {
        "gray": discord.ButtonStyle.gray,
        "grey": discord.ButtonStyle.gray,
        "green": discord.ButtonStyle.green,
        "red": discord.ButtonStyle.red,
        "blurple": discord.ButtonStyle.blurple,
    }
    return styles.get(str(style).lower(), discord.ButtonStyle.blurple)

class ReactionRolePanelView(discord.ui.View):
    def __init__(self, cog: "ReactionRolesCog", panel_key: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.panel_key = panel_key
        panel = cog.get_panel(panel_key)

        if panel is None:
            return

        default_style = panel.get("BUTTON_STYLE", "blurple")

        for index, role_config in enumerate(panel.get("ROLES", [])):
            role_id = role_config.get("ROLE_ID", 0)

            if not role_id:
                continue

            emoji = role_config.get("EMOJI")

            button = discord.ui.Button(
                label=role_config.get("LABEL", f"Role {index + 1}")[:80],
                style=button_style(role_config.get("BUTTON_STYLE", default_style)),
                emoji=emoji if emoji else None,
                custom_id=f"reactionrole:{panel_key}:{index}",
            )
            button.callback = self.build_callback(index)
            self.add_item(button)

    def build_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            await self.cog.handle_role_toggle(interaction, self.panel_key, index)

        return callback

class ReactionRolesCog(commands.Cog):
    reactionroles = app_commands.Group(name="reactionroles", description="Manage reaction role panels.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = reaction_roles_config
        self.panels = self.config.get("PANELS", {})
        self.title_emoji = self.config.get("TITLE_EMOJI", "🔔")

        for panel_key in self.panels:
            self.bot.add_view(ReactionRolePanelView(self, panel_key))

    def base_embed(self, title: str, description: str | None = None, color: discord.Color | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=color or discord.Color.from_str(embed_color))

    def get_panel(self, panel_key: str) -> dict | None:
        panel = self.panels.get(panel_key)

        if not isinstance(panel, dict):
            return None

        return panel

    def panel_title(self, panel_key: str, panel: dict) -> str:
        title = panel.get("TITLE", panel_key.replace("_", " ").title())
        emoji = panel.get("TITLE_EMOJI", self.title_emoji)

        if emoji:
            return f"{emoji} {title}"

        return title

    def configured_roles(self, panel: dict) -> list[tuple[int, dict]]:
        roles = []

        for index, role_config in enumerate(panel.get("ROLES", [])):
            role_id = role_config.get("ROLE_ID", 0)

            if role_id:
                roles.append((index, role_config))

        return roles

    def panel_embed(self, panel_key: str) -> discord.Embed | None:
        panel = self.get_panel(panel_key)

        if panel is None or not self.configured_roles(panel):
            return None

        return self.base_embed(self.panel_title(panel_key, panel), panel.get("DESCRIPTION"))

    def can_manage_role(self, guild: discord.Guild, role: discord.Role) -> bool:
        if guild.me.top_role <= role:
            return False

        return guild.me.guild_permissions.manage_roles

    async def handle_role_toggle(self, interaction: discord.Interaction, panel_key: str, index: int):
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return

        panel = self.get_panel(panel_key)

        if panel is None:
            await interaction.response.send_message("This reaction role panel is no longer configured.", ephemeral=True)
            return

        roles = panel.get("ROLES", [])

        if index >= len(roles):
            await interaction.response.send_message("That role button is no longer valid.", ephemeral=True)
            return

        role_config = roles[index]
        role_id = role_config.get("ROLE_ID", 0)
        role = interaction.guild.get_role(role_id)

        if role is None:
            await interaction.response.send_message("That role could not be found. Ask an admin to update the config.", ephemeral=True)
            return

        if not self.can_manage_role(interaction.guild, role):
            await interaction.response.send_message("I cannot assign that role. Move my highest role above it in Server Settings.", ephemeral=True)
            return

        member = interaction.user
        label = role_config.get("LABEL", role.name)

        if role in member.roles:
            try:
                await member.remove_roles(role, reason=f"Reaction role removed: {panel_key}/{label}")
            except discord.Forbidden:
                await interaction.response.send_message("I could not remove that role.", ephemeral=True)
                return

            embed = self.base_embed("Role Removed", f"You no longer have **{label}** ({role.mention}).", discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if panel.get("EXCLUSIVE", False):
            roles_to_remove = []

            for other_index, other_config in self.configured_roles(panel):
                if other_index == index:
                    continue

                other_role = interaction.guild.get_role(other_config.get("ROLE_ID", 0))

                if other_role is not None and other_role in member.roles and self.can_manage_role(interaction.guild, other_role):
                    roles_to_remove.append(other_role)

            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason=f"Reaction role exclusive swap: {panel_key}")
                except discord.Forbidden:
                    await interaction.response.send_message("I could not update your other roles for this panel.", ephemeral=True)
                    return

        try:
            await member.add_roles(role, reason=f"Reaction role added: {panel_key}/{label}")
        except discord.Forbidden:
            await interaction.response.send_message("I could not assign that role.", ephemeral=True)
            return

        description = f"You now have **{label}** ({role.mention})."

        if panel.get("EXCLUSIVE", False):
            description += "\n\nYour previous selection in this panel was replaced."

        embed = self.base_embed("Role Added", description, discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def panel_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        choices = []

        for panel_key, panel in self.panels.items():
            if not self.configured_roles(panel):
                continue

            label = panel.get("TITLE", panel_key.replace("_", " ").title())

            if not current or current.lower() in panel_key.lower() or current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=panel_key))

        return choices[:25]

    @reactionroles.command(name="send", description="Send reaction role panels to this channel.")
    @app_commands.describe(panel="Send one panel, or leave empty to send every configured panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def send(self, interaction: discord.Interaction, panel: str | None = None):
        panel_keys = [panel] if panel else list(self.panels.keys())
        panels_to_send = []

        for panel_key in panel_keys:
            embed = self.panel_embed(panel_key)
            view = ReactionRolePanelView(self, panel_key)

            if embed is None or not view.children:
                continue

            panels_to_send.append((embed, view))

        if not panels_to_send:
            await interaction.response.send_message("No reaction role panels are configured with valid role IDs.", ephemeral=True)
            return

        await interaction.response.send_message(f"Sent **{len(panels_to_send)}** reaction role panel(s).", ephemeral=True)

        for embed, view in panels_to_send:
            await interaction.channel.send(embed=embed, view=view)

    @send.autocomplete("panel")
    async def send_panel_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await self.panel_autocomplete(interaction, current)

    @reactionroles.command(name="status", description="Show configured reaction role panels.")
    @app_commands.checks.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        if not self.panels:
            await interaction.response.send_message("No reaction role panels are configured.", ephemeral=True)
            return

        embed = self.base_embed("Reaction Roles", "Configured panels and role mappings.")

        for panel_key, panel in self.panels.items():
            role_lines = []
            guild = interaction.guild

            for index, role_config in self.configured_roles(panel):
                role_id = role_config.get("ROLE_ID", 0)
                role = guild.get_role(role_id) if guild is not None else None
                role_name = role.mention if role is not None else f"Missing role (`{role_id}`)"
                role_lines.append(f"**{role_config.get('LABEL', f'Role {index + 1}')}** → {role_name}")

            if not role_lines:
                role_lines.append("No valid role IDs configured.")

            mode = "One at a time" if panel.get("EXCLUSIVE", False) else "Toggle multiple"
            embed.add_field(name=self.panel_title(panel_key, panel), value=f"{panel.get('DESCRIPTION', 'No description.')}\n\n" + "\n".join(role_lines) + f"\n\n**Mode:** {mode}", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ReactionRolesCog(bot), guilds=[discord.Object(id=guild_id)])