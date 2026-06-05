import asyncio
import io
import discord
import aiosqlite
import yaml
import time
import re
from datetime import datetime, timezone
from discord import app_commands
from discord.ext import commands
from cogs.functions.sqlite import DATABASE_PATH, tickets

TICKET_DELETE_DELAY = 15
TRANSCRIPT_SEPARATOR = "_" * 40

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
ticket_config = data.get("Tickets", {})

def current_timestamp() -> int:
    return int(time.time())

def clean_channel_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9-]", "-", value.lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned[:80] or "ticket"

def button_style(style: str) -> discord.ButtonStyle:
    styles = {
        "gray": discord.ButtonStyle.gray,
        "grey": discord.ButtonStyle.gray,
        "green": discord.ButtonStyle.green,
        "red": discord.ButtonStyle.red,
        "blurple": discord.ButtonStyle.blurple,
    }
    return styles.get(str(style).lower(), discord.ButtonStyle.gray)

class TicketModal(discord.ui.Modal):
    def __init__(self, cog: "TicketsCog", ticket_type: str, type_config: dict, questions: list[str]):
        super().__init__(title=type_config.get("LABEL", ticket_type.title())[:45])
        self.cog = cog
        self.ticket_type = ticket_type
        self.type_config = type_config
        self.questions = questions
        self.inputs = []

        for index, question in enumerate(questions):
            field = discord.ui.TextInput(
                label=question[:45],
                style=discord.TextStyle.paragraph,
                required=True,
                custom_id=f"question_{index}",
            )
            self.inputs.append(field)
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        answers = [(question, str(field.value)) for question, field in zip(self.questions, self.inputs)]
        channel = await self.cog.create_ticket_channel(interaction, self.ticket_type, self.type_config)

        if channel is None:
            await interaction.response.send_message("I could not create that ticket channel.", ephemeral=True)
            return

        ticket_id = await self.cog.create_ticket_record(interaction, channel, self.ticket_type)
        await self.cog.save_answers(ticket_id, answers)
        await self.cog.send_ticket_summary(channel, interaction.user, self.ticket_type, self.type_config, ticket_id, answers)
        await self.cog.log_ticket_open(interaction, channel, ticket_id, self.ticket_type)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self, cog: "TicketsCog"):
        super().__init__(timeout=None)
        self.cog = cog

        for ticket_type, type_config in cog.ticket_types.items():
            button = discord.ui.Button(
                label=type_config.get("LABEL", ticket_type.title()),
                style=button_style(type_config.get("BUTTON_STYLE", "gray")),
                custom_id=f"ticket_open:{ticket_type}",
            )
            button.callback = self.open_ticket
            self.add_item(button)

    async def open_ticket(self, interaction: discord.Interaction):
        ticket_type = interaction.data["custom_id"].split(":", 1)[1]
        await self.cog.start_ticket(interaction, ticket_type)

class TicketChannelView(discord.ui.View):
    def __init__(self, cog: "TicketsCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="ticket_channel:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket(interaction)

class TicketsCog(commands.Cog):
    ticket = app_commands.Group(name="tickets", description="Manage tickets.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = ticket_config
        self.ticket_types = self.config.get("TYPES", {})
        self.staff_role_ids = self.config.get("STAFF_ROLE_IDS", [])
        self.log_channel_id = self.config.get("LOG_CHANNEL_ID", 0)
        self.default_category_id = self.config.get("DEFAULT_CATEGORY_ID", 0)

    async def initialize(self):
        await tickets()
        self.bot.add_view(TicketPanelView(self))
        self.bot.add_view(TicketChannelView(self))

    def base_embed(self, title: str, description: str | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=discord.Color.from_str(embed_color))

    def get_type_config(self, ticket_type: str) -> dict | None:
        return self.ticket_types.get(ticket_type)

    def get_questions(self, type_config: dict) -> list[str]:
        return [str(question) for question in type_config.get("QUESTIONS", [])]

    def is_staff(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True

        return any(role.id in self.staff_role_ids for role in member.roles)

    async def start_ticket(self, interaction: discord.Interaction, ticket_type: str):
        type_config = self.get_type_config(ticket_type)

        if type_config is None:
            await interaction.response.send_message("That ticket type is not configured.", ephemeral=True)
            return

        questions = self.get_questions(type_config)

        if len(questions) <= 5:
            await interaction.response.send_modal(TicketModal(self, ticket_type, type_config, questions))
            return

        channel = await self.create_ticket_channel(interaction, ticket_type, type_config)

        if channel is None:
            await interaction.response.send_message("I could not create that ticket channel.", ephemeral=True)
            return

        ticket_id = await self.create_ticket_record(interaction, channel, ticket_type)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)
        await self.log_ticket_open(interaction, channel, ticket_id, ticket_type)
        answers = await self.collect_text_answers(channel, interaction.user, questions)

        if answers is None:
            await self.mark_ticket_closed(ticket_id)
            await channel.send("Ticket setup timed out before all questions were answered.")
            await self.log_ticket_timeout(interaction, channel, ticket_id, ticket_type)
            return

        await self.save_answers(ticket_id, answers)
        await self.send_ticket_summary(channel, interaction.user, ticket_type, type_config, ticket_id, answers)

    async def create_ticket_channel(self, interaction: discord.Interaction, ticket_type: str, type_config: dict):
        if interaction.guild is None:
            return None

        category_id = type_config.get("CATEGORY_ID") or self.default_category_id
        category = interaction.guild.get_channel(category_id) if category_id else None
        prefix = clean_channel_name(type_config.get("CHANNEL_PREFIX", ticket_type))
        username = clean_channel_name(interaction.user.name)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }

        for role_id in self.staff_role_ids:
            role = interaction.guild.get_role(role_id)

            if role is not None:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)

        try:
            return await interaction.guild.create_text_channel(name=f"{prefix}-{username}", category=category, overwrites=overwrites, reason=f"Ticket opened by {interaction.user}")
        except discord.HTTPException:
            return None

    async def create_ticket_record(self, interaction: discord.Interaction, channel: discord.TextChannel, ticket_type: str) -> int:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute("INSERT INTO tickets (guild_id, channel_id, creator_id, ticket_type, status, created_at) VALUES (?, ?, ?, ?, ?, ?)", (interaction.guild.id, channel.id, interaction.user.id, ticket_type, "open", current_timestamp()))
            await db.commit()
            return cursor.lastrowid

    async def save_answers(self, ticket_id: int, answers: list[tuple[str, str]]):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.executemany("INSERT INTO ticket_answers (ticket_id, question, answer, position) VALUES (?, ?, ?, ?)", [(ticket_id, question, answer, index) for index, (question, answer) in enumerate(answers)])
            await db.commit()

    async def collect_text_answers(self, channel: discord.TextChannel, user: discord.Member | discord.User, questions: list[str]):
        answers = []

        for question in questions:
            embed = self.base_embed("Ticket Question", question)
            await channel.send(content=user.mention, embed=embed)

            def check(message: discord.Message) -> bool:
                return message.author.id == user.id and message.channel.id == channel.id

            try:
                message = await self.bot.wait_for("message", check=check, timeout=300)
            except TimeoutError:
                return None

            answers.append((question, message.content))

        return answers

    async def send_ticket_summary(self, channel: discord.TextChannel, user: discord.Member | discord.User, ticket_type: str, type_config: dict, ticket_id: int, answers: list[tuple[str, str]]):
        embed = self.base_embed(f"{type_config.get('LABEL', ticket_type.title())} Ticket", f"Opened by {user.mention}")
        embed.add_field(name="Ticket ID", value=str(ticket_id), inline=True)
        embed.add_field(name="Type", value=type_config.get("LABEL", ticket_type.title()), inline=True)

        for question, answer in answers:
            embed.add_field(name=question[:256], value=answer[:1024] or "No answer provided.", inline=False)

        await channel.send(embed=embed, view=TicketChannelView(self))

    async def get_ticket_by_channel(self, channel_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tickets WHERE channel_id = ? ORDER BY id DESC LIMIT 1", (channel_id,)) as cursor:
                return await cursor.fetchone()

    async def mark_ticket_closed(self, ticket_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE tickets SET status = ?, closed_at = ? WHERE id = ?", ("closed", current_timestamp(), ticket_id))
            await db.commit()

    def iso_timestamp(self, value: datetime | int) -> str:
        if isinstance(value, int):
            value = datetime.fromtimestamp(value, tz=timezone.utc)

        value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%dT%H:%M:%S") + f".{value.microsecond // 1000:03d}Z"

    def transcript_author(self, author: discord.abc.User) -> str:
        discriminator = getattr(author, "discriminator", "0")

        if discriminator and discriminator != "0":
            return f"{author.name}#{discriminator}"

        return author.name

    def transcript_content(self, message: discord.Message) -> str:
        parts = []

        if message.content:
            parts.append(message.content)

        for embed in message.embeds:
            if embed.description:
                parts.append(embed.description)

        if message.attachments:
            attachment_names = ", ".join(attachment.filename for attachment in message.attachments)
            parts.append(f"[attachments: {attachment_names}]")

        if message.stickers:
            sticker_names = ", ".join(sticker.name for sticker in message.stickers)
            parts.append(f"[stickers: {sticker_names}]")

        if not parts:
            return "[no text content]"

        content = "\n".join(parts)
        content = content.replace("```", "'''")
        return " ".join(content.split())

    def transcript_line(self, message: discord.Message) -> str:
        timestamp = self.iso_timestamp(message.created_at)
        author = self.transcript_author(message.author)
        content = self.transcript_content(message)
        return f"[{timestamp}] {author}: {content}"

    async def fetch_channel_messages(self, channel: discord.TextChannel) -> list[discord.Message]:
        messages = []
        async for message in channel.history(limit=None, oldest_first=True):
            messages.append(message)
        return messages

    async def build_transcript_file(self, ticket, channel: discord.TextChannel, guild: discord.Guild, closer: discord.abc.User | None = None) -> discord.File:
        type_config = self.get_type_config(ticket["ticket_type"])
        category = type_config.get("LABEL", ticket["ticket_type"]) if type_config else ticket["ticket_type"]
        creator = guild.get_member(ticket["creator_id"]) or self.bot.get_user(ticket["creator_id"])
        creator_name = creator.name if creator is not None else "Unknown User"
        opened_at = self.iso_timestamp(ticket["created_at"])
        messages = await self.fetch_channel_messages(channel)
        header_lines = [
            f"Ticket transcript — #{channel.name}",
            f"Category: {category}",
            f"Opened by: {creator_name} ({ticket['creator_id']})",
            f"Opened at: {opened_at}",
        ]

        if closer is not None:
            header_lines.append(f"Closed by: {self.transcript_author(closer)} ({closer.id}) at {self.iso_timestamp(datetime.now(timezone.utc))}")

        header_lines.append(TRANSCRIPT_SEPARATOR)
        message_lines = [self.transcript_line(message) for message in messages]
        full_text = "\n".join(header_lines + message_lines)
        filename = f"{channel.name}-transcript.txt"
        return discord.File(io.BytesIO(full_text.encode("utf-8")), filename=filename)

    async def log_ticket_open(self, interaction: discord.Interaction, channel: discord.TextChannel, ticket_id: int, ticket_type: str):
        type_config = self.get_type_config(ticket_type)
        label = type_config.get("LABEL", ticket_type) if type_config else ticket_type

        await self.bot.event_logger.log(
            "TICKETS",
            "OPEN",
            "Ticket Opened",
            f"{interaction.user.mention} opened ticket #{ticket_id}.",
            fields=[
                ("Ticket ID", str(ticket_id), True),
                ("Type", label, True),
                ("Creator", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                ("Channel", f"{channel.mention} (`{channel.id}`)", False),
            ],
            payload={
                "guild_id": interaction.guild.id,
                "ticket_id": ticket_id,
                "ticket_type": ticket_type,
                "creator_id": interaction.user.id,
                "channel_id": channel.id,
            },
            guild=interaction.guild,
        )

    async def log_ticket_timeout(self, interaction: discord.Interaction, channel: discord.TextChannel, ticket_id: int, ticket_type: str):
        await self.bot.event_logger.log(
            "TICKETS",
            "SETUP_TIMEOUT",
            "Ticket Setup Timed Out",
            f"Ticket #{ticket_id} timed out before all questions were answered.",
            fields=[
                ("Ticket ID", str(ticket_id), True),
                ("Type", ticket_type, True),
                ("Creator", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
                ("Channel", f"{channel.mention} (`{channel.id}`)", False),
            ],
            payload={
                "guild_id": interaction.guild.id,
                "ticket_id": ticket_id,
                "ticket_type": ticket_type,
                "creator_id": interaction.user.id,
                "channel_id": channel.id,
            },
            guild=interaction.guild,
        )

    async def log_ticket_close(self, interaction: discord.Interaction, ticket, event: str = "CLOSE"):
        if interaction.channel is None or interaction.guild is None:
            return

        title = "Ticket Deleted" if event == "DELETE" else "Ticket Closed"
        description = f"Ticket #{ticket['id']} was {'deleted' if event == 'DELETE' else 'closed'} by {interaction.user.mention}."
        transcript_file = await self.build_transcript_file(ticket, interaction.channel, interaction.guild, interaction.user)

        await self.bot.event_logger.log(
            "TICKETS",
            event,
            title,
            description,
            fields=[
                ("Ticket ID", str(ticket["id"]), True),
                ("Type", ticket["ticket_type"], True),
                ("Channel", f"#{interaction.channel.name} (`{interaction.channel.id}`)", False),
                ("Closed By", f"{interaction.user.mention} (`{interaction.user.id}`)", False),
            ],
            file=transcript_file,
            payload={
                "guild_id": interaction.guild.id,
                "ticket_id": ticket["id"],
                "ticket_type": ticket["ticket_type"],
                "creator_id": ticket["creator_id"],
                "channel_id": interaction.channel.id,
                "closed_by": interaction.user.id,
            },
            guild=interaction.guild,
        )

    async def disable_close_button(self, channel: discord.TextChannel):
        async for message in channel.history(limit=25):
            if message.author.id != self.bot.user.id or not message.components:
                continue

            for row in message.components:
                for component in row.children:
                    if getattr(component, "custom_id", None) == "ticket_channel:close":
                        await message.edit(view=None)
                        return

    async def delete_ticket_channel_after(self, channel: discord.TextChannel, ticket_id: int):
        await asyncio.sleep(TICKET_DELETE_DELAY)

        try:
            await channel.delete(reason=f"Ticket #{ticket_id} closed")
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    async def close_ticket(self, interaction: discord.Interaction):
        if interaction.channel is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This can only be used in a ticket channel.", ephemeral=True)
            return

        ticket = await self.get_ticket_by_channel(interaction.channel.id)

        if ticket is None:
            await interaction.response.send_message("This channel is not linked to a ticket.", ephemeral=True)
            return

        if ticket["status"] != "open":
            await interaction.response.send_message("This ticket is already closed.", ephemeral=True)
            return

        if interaction.user.id != ticket["creator_id"] and not self.is_staff(interaction.user):
            await interaction.response.send_message("You do not have permission to close this ticket.", ephemeral=True)
            return

        channel = interaction.channel
        await self.mark_ticket_closed(ticket["id"])
        await interaction.response.send_message("Ticket closed.", ephemeral=True)
        await self.disable_close_button(channel)

        creator = interaction.guild.get_member(ticket["creator_id"])

        if creator is not None:
            try:
                await channel.set_permissions(creator, send_messages=False)
            except discord.HTTPException:
                pass

        close_embed = self.base_embed("Ticket Closed", f"This ticket was closed by {interaction.user.mention}.\n\nThis channel will be deleted in **{TICKET_DELETE_DELAY} seconds**.")
        await channel.send(embed=close_embed)
        await self.log_ticket_close(interaction, ticket)
        asyncio.create_task(self.delete_ticket_channel_after(channel, ticket["id"]))

    @ticket.command(name="panel", description="Send the ticket panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction):
        if not self.ticket_types:
            await interaction.response.send_message("No ticket types are configured.", ephemeral=True)
            return

        embed = self.base_embed("Tickets", "Click a button below to open a ticket.")

        for ticket_type, type_config in self.ticket_types.items():
            embed.add_field(name=type_config.get("LABEL", ticket_type.title()), value=type_config.get("DESCRIPTION", "Open a ticket."), inline=False)

        await interaction.channel.send(embed=embed, view=TicketPanelView(self))
        await interaction.response.send_message("Ticket panel sent.", ephemeral=True)
        await self.bot.event_logger.log(
            "TICKETS",
            "PANEL_SENT",
            "Ticket Panel Sent",
            f"{interaction.user.mention} sent the ticket panel in {interaction.channel.mention}.",
            fields=[
                ("Moderator", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                ("Channel", f"{interaction.channel.mention} (`{interaction.channel.id}`)", True),
                ("Ticket Types", str(len(self.ticket_types)), True),
            ],
            payload={
                "guild_id": interaction.guild.id,
                "moderator_id": interaction.user.id,
                "channel_id": interaction.channel.id,
            },
            guild=interaction.guild,
        )

    @ticket.command(name="close", description="Close the current ticket.")
    async def close(self, interaction: discord.Interaction):
        await self.close_ticket(interaction)

    @ticket.command(name="delete", description="Delete the current ticket channel.")
    async def delete(self, interaction: discord.Interaction):
        if interaction.channel is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This can only be used in a ticket channel.", ephemeral=True)
            return

        ticket = await self.get_ticket_by_channel(interaction.channel.id)

        if ticket is None:
            await interaction.response.send_message("This channel is not linked to a ticket.", ephemeral=True)
            return

        if not self.is_staff(interaction.user):
            await interaction.response.send_message("You do not have permission to delete this ticket.", ephemeral=True)
            return

        await self.mark_ticket_closed(ticket["id"])
        await interaction.response.send_message("Deleting ticket channel.", ephemeral=True)
        await self.log_ticket_close(interaction, ticket, event="DELETE")
        await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")

async def setup(bot):
    cog = TicketsCog(bot)
    await cog.initialize()
    await bot.add_cog(cog, guilds=[discord.Object(id=guild_id)])