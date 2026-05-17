import discord
import aiosqlite
import random
import yaml
import time
import re
from discord import app_commands
from discord.ext import commands, tasks
from cogs.functions.sqlite import DATABASE_PATH, giveaways

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]

def current_timestamp() -> int:
    return int(time.time())

def parse_duration(duration: str) -> int | None:
    matches = re.findall(r"(\d+)\s*([smhdw])", duration.lower())

    if not matches:
        return None

    total = 0
    consumed = ""
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    for amount, unit in matches:
        total += int(amount) * multipliers[unit]
        consumed += f"{amount}{unit}"

    normalized = re.sub(r"\s+", "", duration.lower())

    if consumed != normalized or total <= 0:
        return None

    return total

class GiveawayEntryView(discord.ui.View):
    def __init__(self, cog: "GiveawaysCog", giveaway_id: int, disabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.giveaway_id = giveaway_id

        button = discord.ui.Button(
            label="Enter Giveaway",
            style=discord.ButtonStyle.green,
            custom_id=f"giveaway_enter:{giveaway_id}",
            disabled=disabled,
        )
        button.callback = self.enter_giveaway
        self.add_item(button)

    async def enter_giveaway(self, interaction: discord.Interaction):
        await self.cog.handle_entry(interaction, self.giveaway_id)

class GiveawayListView(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.page = 0
        self.previous_page.disabled = True
        self.next_page.disabled = len(embeds) <= 1

    def update_buttons(self):
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= len(self.embeds) - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

class GiveawaysCog(commands.Cog):
    giveaway = app_commands.Group(name="giveaway", description="Manage giveaways.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def initialize(self):
        await giveaways()
        await self.restore_active_views()
        self.finish_expired_giveaways.start()

    async def restore_active_views(self):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT id, message_id FROM giveaways WHERE status = ? AND message_id IS NOT NULL", ("active",)) as cursor:
                rows = await cursor.fetchall()

        for giveaway_id, message_id in rows:
            self.bot.add_view(GiveawayEntryView(self, giveaway_id), message_id=message_id)

    def cog_unload(self):
        self.finish_expired_giveaways.cancel()

    def base_embed(self, title: str, description: str | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=discord.Color.from_str(embed_color))

    def giveaway_belongs_to_guild(self, giveaway, guild_id: int | None) -> bool:
        return giveaway is not None and giveaway["guild_id"] == guild_id

    async def get_giveaway(self, giveaway_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,)) as cursor:
                return await cursor.fetchone()

    async def get_entry_count(self, giveaway_id: int) -> int:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0]

    async def get_entries(self, giveaway_id: int) -> list[int]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,)) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def update_giveaway_message(self, giveaway_id: int, disabled: bool = False):
        giveaway = await self.get_giveaway(giveaway_id)

        if giveaway is None or giveaway["message_id"] is None:
            return

        guild = self.bot.get_guild(giveaway["guild_id"])
        channel = self.bot.get_channel(giveaway["channel_id"])

        if guild is None or channel is None:
            return

        try:
            message = await channel.fetch_message(giveaway["message_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        embed = await self.create_giveaway_embed(giveaway_id)
        view = GiveawayEntryView(self, giveaway_id, disabled=disabled)
        await message.edit(embed=embed, view=view)

    async def create_giveaway_embed(self, giveaway_id: int) -> discord.Embed:
        giveaway = await self.get_giveaway(giveaway_id)
        entry_count = await self.get_entry_count(giveaway_id)
        status = giveaway["status"].title()

        embed = self.base_embed(f"Giveaway: {giveaway['prize']}")
        embed.add_field(name="Prize", value=giveaway["prize"], inline=False)
        embed.add_field(name="Winners", value=str(giveaway["winner_count"]), inline=True)
        embed.add_field(name="Entries", value=str(entry_count), inline=True)
        embed.add_field(name="Status", value=status, inline=True)

        if giveaway["status"] == "active":
            embed.add_field(name="Ends", value=f"<t:{giveaway['end_time']}:R>", inline=True)
        else:
            embed.add_field(name="Ended", value=f"<t:{current_timestamp()}:R>", inline=True)

        embed.add_field(name="Hosted By", value=f"<@{giveaway['host_id']}>", inline=True)
        embed.set_footer(text=f"Giveaway ID: {giveaway_id}")
        return embed

    async def handle_entry(self, interaction: discord.Interaction, giveaway_id: int):
        giveaway = await self.get_giveaway(giveaway_id)

        if giveaway is None:
            await interaction.response.send_message("That giveaway could not be found.", ephemeral=True)
            return

        if not self.giveaway_belongs_to_guild(giveaway, interaction.guild_id):
            await interaction.response.send_message("That giveaway could not be found in this server.", ephemeral=True)
            return

        if giveaway["status"] != "active" or giveaway["end_time"] <= current_timestamp():
            await interaction.response.send_message("That giveaway is no longer active.", ephemeral=True)
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            try:
                await db.execute("INSERT INTO giveaway_entries (giveaway_id, user_id, joined_at) VALUES (?, ?, ?)", (giveaway_id, interaction.user.id, current_timestamp()))
                await db.commit()
            except aiosqlite.IntegrityError:
                await interaction.response.send_message("You're already entered in this giveaway.", ephemeral=True)
                return

        await self.update_giveaway_message(giveaway_id)
        await interaction.response.send_message("You're entered in the giveaway!", ephemeral=True)

    async def finish_giveaway(self, giveaway_id: int, announce: bool = True):
        giveaway = await self.get_giveaway(giveaway_id)

        if giveaway is None or giveaway["status"] != "active":
            return False

        entries = await self.get_entries(giveaway_id)
        winner_count = min(giveaway["winner_count"], len(entries))
        winners = random.sample(entries, winner_count) if winner_count else []

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE giveaways SET status = ? WHERE id = ?", ("finished", giveaway_id))
            await db.commit()

        await self.update_giveaway_message(giveaway_id, disabled=True)

        if announce:
            channel = self.bot.get_channel(giveaway["channel_id"])

            if channel is not None:
                if winners:
                    winner_mentions = ", ".join(f"<@{winner}>" for winner in winners)
                    await channel.send(f"Congratulations {winner_mentions}! You won **{giveaway['prize']}**!")
                else:
                    await channel.send(f"Giveaway **{giveaway['prize']}** ended with no entries.")

        return True

    @tasks.loop(seconds=30)
    async def finish_expired_giveaways(self):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT id FROM giveaways WHERE status = ? AND end_time <= ?", ("active", current_timestamp())) as cursor:
                rows = await cursor.fetchall()

        for row in rows:
            await self.finish_giveaway(row[0])

    @finish_expired_giveaways.before_loop
    async def before_finish_expired_giveaways(self):
        await self.bot.wait_until_ready()

    @giveaway.command(name="start", description="Start a giveaway.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(prize="The prize to give away.", winners="How many winners to draw.", duration="Duration like 10m, 2h, 1d2h30m.")
    async def start(self, interaction: discord.Interaction, prize: str, winners: app_commands.Range[int, 1, 100], duration: str):
        seconds = parse_duration(duration)

        if seconds is None:
            await interaction.response.send_message("Invalid duration. Use formats like `10m`, `2h`, `3d`, or `1d2h30m`.", ephemeral=True)
            return

        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Giveaways can only be started in a server channel.", ephemeral=True)
            return

        end_time = current_timestamp() + seconds

        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute("INSERT INTO giveaways (guild_id, channel_id, host_id, prize, winner_count, end_time, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (interaction.guild.id, interaction.channel.id, interaction.user.id, prize, winners, end_time, "active", current_timestamp()))
            giveaway_id = cursor.lastrowid
            await db.commit()

        embed = await self.create_giveaway_embed(giveaway_id)
        view = GiveawayEntryView(self, giveaway_id)
        await interaction.response.send_message("Giveaway created!", ephemeral=True)
        message = await interaction.channel.send(embed=embed, view=view)

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE giveaways SET message_id = ? WHERE id = ?", (message.id, giveaway_id))
            await db.commit()

        self.bot.add_view(GiveawayEntryView(self, giveaway_id), message_id=message.id)

    @giveaway.command(name="list", description="List giveaways.")
    @app_commands.checks.has_permissions(administrator=True)
    async def list(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT g.*, COUNT(e.user_id) AS entry_count FROM giveaways g LEFT JOIN giveaway_entries e ON e.giveaway_id = g.id WHERE g.guild_id = ? GROUP BY g.id ORDER BY g.created_at DESC", (interaction.guild_id,)) as cursor:
                giveaways = await cursor.fetchall()

        if not giveaways:
            await interaction.response.send_message("There are no giveaways to list.", ephemeral=True)
            return

        embeds = []

        for index in range(0, len(giveaways), 5):
            page_giveaways = giveaways[index:index + 5]
            page_number = (index // 5) + 1
            page_count = ((len(giveaways) - 1) // 5) + 1
            embed = self.base_embed("Giveaways")
            embed.set_footer(text=f"Page {page_number}/{page_count}")

            for giveaway in page_giveaways:
                if giveaway["status"] == "active":
                    time_text = f"Ends <t:{giveaway['end_time']}:R>"
                else:
                    time_text = giveaway["status"].title()

                embed.add_field(name=f"#{giveaway['id']} - {giveaway['prize']}", value=f"Status: {giveaway['status'].title()}\nWinners: {giveaway['winner_count']}\nEntries: {giveaway['entry_count']}\n{time_text}", inline=False)

            embeds.append(embed)

        await interaction.response.send_message(embed=embeds[0], view=GiveawayListView(embeds), ephemeral=True)

    @giveaway.command(name="stop", description="Stop a giveaway without drawing winners.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(giveaway_id="The giveaway ID to stop.")
    async def stop(self, interaction: discord.Interaction, giveaway_id: int):
        giveaway = await self.get_giveaway(giveaway_id)

        if not self.giveaway_belongs_to_guild(giveaway, interaction.guild_id):
            await interaction.response.send_message("That giveaway could not be found.", ephemeral=True)
            return

        if giveaway["status"] != "active":
            await interaction.response.send_message("That giveaway is not active.", ephemeral=True)
            return

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE giveaways SET status = ? WHERE id = ?", ("stopped", giveaway_id))
            await db.commit()

        await self.update_giveaway_message(giveaway_id, disabled=True)
        await interaction.response.send_message(f"Stopped giveaway #{giveaway_id}.", ephemeral=True)

    @giveaway.command(name="finish", description="Finish a giveaway and draw winners now.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(giveaway_id="The giveaway ID to finish.")
    async def finish(self, interaction: discord.Interaction, giveaway_id: int):
        giveaway = await self.get_giveaway(giveaway_id)

        if not self.giveaway_belongs_to_guild(giveaway, interaction.guild_id):
            await interaction.response.send_message("That giveaway could not be found.", ephemeral=True)
            return

        finished = await self.finish_giveaway(giveaway_id)

        if finished:
            await interaction.response.send_message(f"Finished giveaway #{giveaway_id}.", ephemeral=True)
        else:
            await interaction.response.send_message("That giveaway could not be finished.", ephemeral=True)

    @giveaway.command(name="delete", description="Delete a giveaway.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(giveaway_id="The giveaway ID to delete.")
    async def delete(self, interaction: discord.Interaction, giveaway_id: int):
        giveaway = await self.get_giveaway(giveaway_id)

        if not self.giveaway_belongs_to_guild(giveaway, interaction.guild_id):
            await interaction.response.send_message("That giveaway could not be found.", ephemeral=True)
            return

        channel = self.bot.get_channel(giveaway["channel_id"])

        if channel is not None and giveaway["message_id"] is not None:
            try:
                message = await channel.fetch_message(giveaway["message_id"])
                await message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("DELETE FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,))
            await db.execute("DELETE FROM giveaways WHERE id = ?", (giveaway_id,))
            await db.commit()

        await interaction.response.send_message(f"Deleted giveaway #{giveaway_id}.", ephemeral=True)

async def setup(bot):
    cog = GiveawaysCog(bot)
    await cog.initialize()
    await bot.add_cog(cog, guilds=[discord.Object(id=guild_id)])