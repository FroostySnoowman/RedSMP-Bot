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

giveaways_columns = {
    "id",
    "guild_id",
    "channel_id",
    "message_id",
    "host_id",
    "prize",
    "winner_count",
    "end_time",
    "status",
    "created_at",
}

giveaway_entries_columns = {
    "giveaway_id",
    "user_id",
    "joined_at",
}

ticket_columns = {
    "id",
    "guild_id",
    "channel_id",
    "creator_id",
    "ticket_type",
    "status",
    "created_at",
    "closed_at",
}

ticket_answer_columns = {
    "ticket_id",
    "question",
    "answer",
    "position",
}

async def check_tables():
    await giveaways()
    await tickets()

async def refresh_table(table: str):
    if table == "Giveaways":
        await giveaways(True)
    elif table == "Tickets":
        await tickets(True)

async def giveaways(delete: bool = False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if delete:
            await drop_giveaway_tables(db)

        if not await giveaway_tables_valid(db):
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

async def table_columns(db, table: str) -> set[str]:
    try:
        async with db.execute(f"PRAGMA table_info({table})") as cursor:
            rows = await cursor.fetchall()
            return {row[1] for row in rows}
    except sqlite3.OperationalError:
        return set()

async def giveaway_tables_valid(db) -> bool:
    giveaway_table_columns = await table_columns(db, "giveaways")
    entry_table_columns = await table_columns(db, "giveaway_entries")
    return giveaways_columns.issubset(giveaway_table_columns) and giveaway_entries_columns.issubset(entry_table_columns)

async def tickets(delete: bool = False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if delete:
            await drop_ticket_tables(db)

        if not await ticket_tables_valid(db):
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

async def ticket_tables_valid(db) -> bool:
    tickets_table_columns = await table_columns(db, "tickets")
    answers_table_columns = await table_columns(db, "ticket_answers")
    return ticket_columns.issubset(tickets_table_columns) and ticket_answer_columns.issubset(answers_table_columns)

class SQLiteCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="refreshtable", description="Refreshes a SQLite table!")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(table="What table should be refreshed?")
    async def refreshtable(self, interaction: discord.Interaction, table: Literal["Giveaways", "Tickets"]) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)

        if await self.bot.is_owner(interaction.user):
            await refresh_table(table)
            embed = discord.Embed(description=f"Successfully refreshed the table **{table}**!", color=discord.Color.from_str(embed_color))
        else:
            embed = discord.Embed(description="You do not have permission to use this command!", color=discord.Color.red())
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(SQLiteCog(bot), guilds=[discord.Object(id=guild_id)])