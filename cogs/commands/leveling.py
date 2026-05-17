import discord
import aiosqlite
import random
import yaml
import time
import math
import io
from pathlib import Path
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
from cogs.functions.sqlite import DATABASE_PATH, leveling

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
leveling_config = data.get("Leveling", {})
font_paths = [
    Path("assets/fonts/NotoSansSC-Regular.ttf"),
    Path("assets/fonts/NotoSansJP-Regular.ttf"),
    Path("assets/fonts/NotoSansTC-Regular.ttf"),
    Path("assets/fonts/NotoSansKR-Regular.ttf"),
    Path("assets/fonts/NotoSans-Regular.ttf"),
]

def current_timestamp() -> int:
    return int(time.time())

def hex_color(value: str, fallback: str) -> tuple[int, int, int]:
    value = str(value or fallback).lstrip("#")

    try:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        fallback = fallback.lstrip("#")
        return tuple(int(fallback[index:index + 2], 16) for index in (0, 2, 4))

class RankCardRenderer:
    def __init__(self, config: dict):
        card_config = config.get("RANK_CARD", {})
        self.width = int(card_config.get("WIDTH", 900))
        self.height = int(card_config.get("HEIGHT", 280))
        self.background_color = hex_color(card_config.get("BACKGROUND_COLOR"), "#1f1f2e")
        self.accent_color = hex_color(card_config.get("ACCENT_COLOR"), "#9C27B0")
        self.text_color = hex_color(card_config.get("TEXT_COLOR"), "#FFFFFF")
        self.muted_text_color = hex_color(card_config.get("MUTED_TEXT_COLOR"), "#B8B8C8")
        self.bar_background_color = hex_color(card_config.get("BAR_BACKGROUND_COLOR"), "#34344A")

    def font(self, size: int):
        for path in font_paths:
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                pass

        return ImageFont.load_default()

    def text_width(self, draw: ImageDraw.ImageDraw, text: str, font) -> int:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    def fit_text(self, draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 18):
        for size in range(start_size, min_size - 1, -2):
            font = self.font(size)

            if self.text_width(draw, text, font) <= max_width:
                return text, font

        font = self.font(min_size)
        ellipsis = "..."
        fitted = text

        while fitted and self.text_width(draw, f"{fitted}{ellipsis}", font) > max_width:
            fitted = fitted[:-1]

        return f"{fitted}{ellipsis}" if fitted else ellipsis, font

    def rounded_rectangle(self, draw: ImageDraw.ImageDraw, coordinates: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int]):
        draw.rounded_rectangle(coordinates, radius=radius, fill=fill)

    async def avatar_image(self, member: discord.Member, size: int) -> Image.Image:
        avatar_bytes = await member.display_avatar.with_size(256).read()
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size))
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, size, size), fill=255)
        output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        output.paste(avatar, (0, 0), mask)
        return output

    async def render(self, member: discord.Member, level: int, xp: int, current_xp: int, needed_xp: int, rank: int) -> discord.File:
        image = Image.new("RGB", (self.width, self.height), self.background_color)
        draw = ImageDraw.Draw(image)
        avatar_size = min(150, self.height - 90)
        avatar = await self.avatar_image(member, avatar_size)
        avatar_x = 50
        avatar_y = (self.height - avatar_size) // 2
        image.paste(avatar, (avatar_x, avatar_y), avatar)

        content_x = avatar_x + avatar_size + 45
        content_width = self.width - content_x - 50
        name_text, name_font = self.fit_text(draw, member.display_name, content_width, 42, 20)
        draw.text((content_x, 46), name_text, fill=self.text_color, font=name_font)

        details_font = self.font(25)
        xp_font = self.font(23)
        draw.text((content_x, 105), f"Level {level}  |  Rank #{rank}", fill=self.muted_text_color, font=details_font)
        xp_text = f"{current_xp:,} / {needed_xp:,} XP"
        xp_width = self.text_width(draw, xp_text, xp_font)
        draw.text((content_x + content_width - xp_width, 145), xp_text, fill=self.text_color, font=xp_font)

        bar_x = content_x
        bar_y = 185
        bar_width = content_width
        bar_height = 34
        progress = 0 if needed_xp <= 0 else max(0, min(current_xp / needed_xp, 1))
        fill_width = max(bar_height, int(bar_width * progress)) if progress > 0 else 0
        self.rounded_rectangle(draw, (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), bar_height // 2, self.bar_background_color)

        if fill_width:
            self.rounded_rectangle(draw, (bar_x, bar_y, bar_x + fill_width, bar_y + bar_height), bar_height // 2, self.accent_color)

        total_font = self.font(18)
        draw.text((content_x, 228), f"Total XP: {xp:,}", fill=self.muted_text_color, font=total_font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename=f"rank-{member.id}.png")

class LeaderboardView(discord.ui.View):
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

class LevelingCog(commands.Cog):
    level = app_commands.Group(name="level", description="View levels and XP.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = leveling_config
        self.enabled = bool(self.config.get("ENABLED", True))
        self.min_xp = int(self.config.get("MIN_XP_PER_MESSAGE", 15))
        self.max_xp = int(self.config.get("MAX_XP_PER_MESSAGE", 25))
        self.cooldown = int(self.config.get("COOLDOWN_SECONDS", 60))
        self.base_xp = int(self.config.get("BASE_XP", 100))
        self.multiplier = float(self.config.get("XP_MULTIPLIER", 1.35))
        self.level_up_channel_id = int(self.config.get("LEVEL_UP_CHANNEL_ID", 0))
        self.ignored_channel_ids = set(self.config.get("IGNORED_CHANNEL_IDS", []))
        self.ignored_role_ids = set(self.config.get("IGNORED_ROLE_IDS", []))
        self.remove_previous_level_roles = bool(self.config.get("REMOVE_PREVIOUS_LEVEL_ROLES", False))
        self.level_roles = {
            int(level): int(role_id)
            for level, role_id in self.config.get("LEVEL_ROLES", {}).items()
            if int(role_id)
        }
        self.renderer = RankCardRenderer(self.config)

    async def initialize(self):
        await leveling()

    def xp_needed_for_level(self, level: int) -> int:
        return max(1, math.ceil(self.base_xp * (self.multiplier ** max(level - 1, 0))))

    def total_xp_for_level(self, level: int) -> int:
        if level <= 1:
            return 0

        return sum(self.xp_needed_for_level(value) for value in range(1, level))

    def level_for_xp(self, xp: int) -> int:
        level = 1

        while xp >= self.total_xp_for_level(level + 1):
            level += 1

        return level

    def current_level_xp(self, xp: int, level: int) -> int:
        return max(0, xp - self.total_xp_for_level(level))

    def base_embed(self, title: str, description: str | None = None) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=discord.Color.from_str(embed_color))

    def should_ignore_message(self, message: discord.Message) -> bool:
        if not self.enabled or message.guild is None or message.author.bot:
            return True

        if message.channel.id in self.ignored_channel_ids:
            return True

        if isinstance(message.author, discord.Member):
            return any(role.id in self.ignored_role_ids for role in message.author.roles)

        return False

    async def get_user_row(self, guild_id: int, user_id: int):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM level_users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)) as cursor:
                return await cursor.fetchone()

    async def upsert_user_xp(self, message: discord.Message, amount: int):
        now = current_timestamp()

        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM level_users WHERE guild_id = ? AND user_id = ?", (message.guild.id, message.author.id)) as cursor:
                row = await cursor.fetchone()

            if row is not None and now - row["last_xp_at"] < self.cooldown:
                await db.execute("UPDATE level_users SET messages = messages + 1, last_channel_id = ? WHERE guild_id = ? AND user_id = ?", (message.channel.id, message.guild.id, message.author.id))
                await db.commit()
                return row["level"], row["level"], False

            old_xp = row["xp"] if row is not None else 0
            old_level = row["level"] if row is not None else 1
            new_xp = old_xp + amount
            new_level = self.level_for_xp(new_xp)

            if row is None:
                await db.execute("INSERT INTO level_users (guild_id, user_id, xp, level, messages, last_xp_at, last_channel_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (message.guild.id, message.author.id, new_xp, new_level, 1, now, message.channel.id))
            else:
                await db.execute("UPDATE level_users SET xp = ?, level = ?, messages = messages + 1, last_xp_at = ?, last_channel_id = ? WHERE guild_id = ? AND user_id = ?", (new_xp, new_level, now, message.channel.id, message.guild.id, message.author.id))

            if new_level > old_level:
                for level in range(old_level + 1, new_level + 1):
                    await db.execute("INSERT INTO level_history (guild_id, user_id, level, reached_at) VALUES (?, ?, ?, ?)", (message.guild.id, message.author.id, level, now))

            await db.commit()
            return old_level, new_level, new_level > old_level

    async def award_level_roles(self, member: discord.Member, old_level: int, new_level: int) -> list[discord.Role]:
        awarded_roles = []

        for level in sorted(self.level_roles):
            if not old_level < level <= new_level:
                continue

            role = member.guild.get_role(self.level_roles[level])

            if role is None or role in member.roles:
                continue

            try:
                await member.add_roles(role, reason=f"Reached level {level}")
                awarded_roles.append(role)
            except discord.HTTPException:
                continue

            if self.remove_previous_level_roles:
                previous_roles = [
                    member.guild.get_role(role_id)
                    for role_level, role_id in self.level_roles.items()
                    if role_level < level
                ]
                removable_roles = [
                    previous_role
                    for previous_role in previous_roles
                    if previous_role is not None and previous_role in member.roles
                ]

                if removable_roles:
                    try:
                        await member.remove_roles(*removable_roles, reason=f"Reached level {level}")
                    except discord.HTTPException:
                        pass

        return awarded_roles

    async def announce_level_up(self, message: discord.Message, level: int, awarded_roles: list[discord.Role] | None = None):
        channel = self.bot.get_channel(self.level_up_channel_id) if self.level_up_channel_id else message.channel

        if channel is None:
            return

        embed = self.base_embed("Level Up!", f"{message.author.mention} reached **level {level}**!")

        if awarded_roles:
            embed.add_field(name="Role Rewards", value=", ".join(role.mention for role in awarded_roles), inline=False)

        await channel.send(embed=embed)

    async def rank_position(self, guild_id: int, user_id: int) -> int:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT COUNT(*) + 1 FROM level_users WHERE guild_id = ? AND (level > (SELECT level FROM level_users WHERE guild_id = ? AND user_id = ?) OR (level = (SELECT level FROM level_users WHERE guild_id = ? AND user_id = ?) AND xp > (SELECT xp FROM level_users WHERE guild_id = ? AND user_id = ?)))", (guild_id, guild_id, user_id, guild_id, user_id, guild_id, user_id)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row is not None else 1

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.should_ignore_message(message):
            return

        amount = random.randint(min(self.min_xp, self.max_xp), max(self.min_xp, self.max_xp))
        old_level, new_level, leveled_up = await self.upsert_user_xp(message, amount)

        if leveled_up and new_level > old_level:
            awarded_roles = await self.award_level_roles(message.author, old_level, new_level)
            await self.announce_level_up(message, new_level, awarded_roles)

    @level.command(name="rank", description="View your rank card or another member's rank card.")
    @app_commands.describe(member="The member to view.")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        target = member or interaction.user
        row = await self.get_user_row(interaction.guild_id, target.id)

        if row is None:
            level = 1
            xp = 0
            current_xp = 0
            needed_xp = self.xp_needed_for_level(level)
            rank = 1
        else:
            level = row["level"]
            xp = row["xp"]
            current_xp = self.current_level_xp(xp, level)
            needed_xp = self.xp_needed_for_level(level)
            rank = await self.rank_position(interaction.guild_id, target.id)

        file = await self.renderer.render(target, level, xp, current_xp, needed_xp, rank)
        await interaction.followup.send(file=file, ephemeral=True)

    @level.command(name="leaderboard", description="View the server XP leaderboard.")
    async def leaderboard(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT user_id, xp, level, messages FROM level_users WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 100", (interaction.guild_id,)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message("No one has earned XP yet.", ephemeral=True)
            return

        embeds = []

        for index in range(0, len(rows), 10):
            page_rows = rows[index:index + 10]
            page_number = (index // 10) + 1
            page_count = ((len(rows) - 1) // 10) + 1
            embed = self.base_embed("Level Leaderboard")
            embed.set_footer(text=f"Page {page_number}/{page_count}")

            description = []

            for offset, row in enumerate(page_rows, start=index + 1):
                member = interaction.guild.get_member(row["user_id"])
                name = member.display_name if member is not None else f"User {row['user_id']}"
                description.append(f"**#{offset}** {name} - Level **{row['level']}** | XP **{row['xp']:,}** | Messages **{row['messages']:,}**")

            embed.description = "\n".join(description)
            embeds.append(embed)

        await interaction.response.send_message(embed=embeds[0], view=LeaderboardView(embeds), ephemeral=True)

async def setup(bot):
    cog = LevelingCog(bot)
    await cog.initialize()
    await bot.add_cog(cog, guilds=[discord.Object(id=guild_id)])