import discord
import aiosqlite
import sqlite3
import yaml
from discord.ext import commands
from discord import app_commands
from typing import Literal

with open('config.yml', 'r') as file:
    data = yaml.safe_load(file)

guild_id = data["General"]["GUILD_ID"]
embed_color = data["General"]["EMBED_COLOR"]
DATABASE_PATH = "database.db"

async def check_tables():
    await giveaways()
    await tickets()
    await leveling()
    await automod()
    await security()

async def refresh_table(table: str):
    if table == "Giveaways":
        await giveaways(True)
    elif table == "Tickets":
        await tickets(True)
    elif table == "Leveling":
        await leveling(True)
    elif table == "Automod":
        await automod(True)
    elif table == "Security":
        await security(True)

async def giveaways(delete: bool = False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if delete:
            await drop_giveaway_tables(db)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                host_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winner_count INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at INTEGER NOT NULL,
                PRIMARY KEY (giveaway_id, user_id),
                FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
            )
        """)
        await db.commit()

async def drop_giveaway_tables(db):
    for table in ("giveaway_entries", "giveaways"):
        try:
            await db.execute(f"DROP TABLE {table}")
        except sqlite3.OperationalError:
            pass

    await db.commit()

async def tickets(delete: bool = False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if delete:
            await drop_ticket_tables(db)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                closed_at INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_answers (
                ticket_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
            )
        """)
        await db.commit()

async def drop_ticket_tables(db):
    for table in ("ticket_answers", "tickets"):
        try:
            await db.execute(f"DROP TABLE {table}")
        except sqlite3.OperationalError:
            pass

    await db.commit()

async def leveling(delete: bool = False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if delete:
            await drop_leveling_tables(db)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS level_users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                xp INTEGER NOT NULL,
                level INTEGER NOT NULL,
                messages INTEGER NOT NULL,
                last_xp_at INTEGER NOT NULL,
                last_channel_id INTEGER,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS level_history (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                level INTEGER NOT NULL,
                reached_at INTEGER NOT NULL
            )
        """)
        await db.commit()

async def drop_leveling_tables(db):
    for table in ("level_history", "level_users"):
        try:
            await db.execute(f"DROP TABLE {table}")
        except sqlite3.OperationalError:
            pass

    await db.commit()

async def automod(delete: bool = False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if delete:
            await drop_automod_tables(db)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_infractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                filter_type TEXT NOT NULL,
                filter_name TEXT NOT NULL,
                matched_value TEXT NOT NULL,
                action TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        await db.commit()

async def drop_automod_tables(db):
    try:
        await db.execute("DROP TABLE automod_infractions")
    except sqlite3.OperationalError:
        pass

    await db.commit()

async def security(delete: bool = False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if delete:
            await drop_security_tables(db)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                target_id INTEGER,
                action_taken TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_counters (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                count INTEGER NOT NULL,
                window_started_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id, event_type)
            )
        """)
        await db.commit()

async def drop_security_tables(db):
    for table in ("security_counters", "security_events"):
        try:
            await db.execute(f"DROP TABLE {table}")
        except sqlite3.OperationalError:
            pass

    await db.commit()

class SQLiteCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="refreshtable", description="Refreshes a SQLite table!")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(table="What table should be refreshed?")
    async def refreshtable(self, interaction: discord.Interaction, table: Literal["Giveaways", "Tickets", "Leveling", "Automod", "Security"]) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)

        if await self.bot.is_owner(interaction.user):
            await refresh_table(table)
            embed = discord.Embed(description=f"Successfully refreshed the table **{table}**!", color=discord.Color.from_str(embed_color))
        else:
            embed = discord.Embed(description="You do not have permission to use this command!", color=discord.Color.red())
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(SQLiteCog(bot), guilds=[discord.Object(id=guild_id)])