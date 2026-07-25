"""
Nocturne Manager
-----------------
Bot Discord untuk notifikasi join/leave (dengan panel builder interaktif)
dan notifikasi status bot (online/maintenance/update/offline).
"""
import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nocturne")

TOKEN = os.getenv("DISCORD_TOKEN")
DEV_GUILD_ID = os.getenv("GUILD_ID")  # opsional, untuk sync instan pas development
PREFIX = os.getenv("PREFIX", "n!")   # prefix untuk command klasik, contoh: n!joinleave builder join

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # wajib aktif biar prefix command bisa baca isi pesan


class NocturneManager(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned_or(PREFIX), intents=intents, help_command=None)

    async def setup_hook(self):
        for ext in ("cogs.joinleave", "cogs.status_panel"):
            await self.load_extension(ext)
            logger.info("Extension dimuat: %s", ext)

        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Sync %s slash command ke guild dev %s (instan)", len(synced), DEV_GUILD_ID)
        else:
            synced = await self.tree.sync()
            logger.info("Sync %s slash command secara global (bisa sampai 1 jam propagasi)", len(synced))

    async def on_ready(self):
        logger.info("Login sebagai %s (ID: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="server kamu | Nocturne Manager")
        )


bot = NocturneManager()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ Kamu butuh izin **Manage Server** untuk menjalankan command ini."
    elif isinstance(error, app_commands.CheckFailure):
        msg = "❌ Command ini cuma bisa dipakai owner bot."
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = f"⏳ Tunggu {error.retry_after:.1f} detik lagi."
    else:
        msg = "⚠️ Terjadi error saat menjalankan command ini. Sudah dicatat di log."
        logger.exception("App command error", exc_info=error)

    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return  # abaikan biar gak spam kalau orang salah ketik prefix command
    if isinstance(error, commands.NotOwner):
        await ctx.send("❌ Command ini cuma bisa dipakai owner bot.")
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Kamu butuh izin **Manage Server** untuk menjalankan command ini.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ Ada parameter yang kurang: `{error.param.name}`. Cek lagi formatnya.")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("⚠️ Salah satu parameter formatnya salah. Cek lagi command-nya.")
        return
    logger.exception("Prefix command error", exc_info=error)
    await ctx.send("⚠️ Terjadi error saat menjalankan command ini. Sudah dicatat di log.")


async def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN belum diset. Cek file .env atau environment variable di Railway.")
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
