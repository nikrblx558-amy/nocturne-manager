"""
Nocturne Manager
-----------------
A Discord bot for join/leave notifications (with a live-preview panel builder)
and an Application System (staff applications, whitelist forms, etc.) — also
with a live-preview panel builder.
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
DEV_GUILD_ID = os.getenv("GUILD_ID")  # optional, for instant sync during development
PREFIX = os.getenv("PREFIX", "n!")    # prefix for classic commands, e.g. n!joinleave builder join

intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # REQUIRED for prefix commands to read message text.
# ⚠️ Setting this in code is NOT enough — you must ALSO enable
# "MESSAGE CONTENT INTENT" under your app's Bot tab on
# https://discord.com/developers/applications, then save changes.
# Without that toggle, Discord will silently withhold message content from
# the bot and prefix commands (n!...) will never trigger, even though slash
# commands keep working fine.


class NocturneManager(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned_or(PREFIX), intents=intents, help_command=None)

    async def setup_hook(self):
        for ext in ("cogs.joinleave", "cogs.application"):
            await self.load_extension(ext)
            logger.info("Loaded extension: %s", ext)

        # IMPORTANT: we only ever use GLOBAL commands. Guild-specific copies
        # are intentionally NOT created anymore — having both a global command
        # and a guild-specific command with the same name makes Discord show
        # TWO separate entries in that server (duplicates), even though
        # they're "the same" command to a human.
        if DEV_GUILD_ID:
            # One-time cleanup: wipe any guild-specific commands left over
            # from before, so the duplicates disappear from the test server.
            guild = discord.Object(id=int(DEV_GUILD_ID))
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Cleared leftover guild-specific commands in dev guild %s (fixes duplicates)", DEV_GUILD_ID)

        # Global sync is what makes commands show up in EVERY server,
        # including new ones. The first global sync after a change can take
        # up to ~1 hour (sometimes longer due to Discord client-side caching)
        # to fully propagate — this is normal and not a bug.
        synced_global = await self.tree.sync()
        logger.info("Synced %s slash commands globally (propagation can take up to 1 hour, sometimes more)", len(synced_global))

    async def on_ready(self):
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        logger.info("Prefix commands active with prefix: '%s' (message_content intent: %s)", PREFIX, intents.message_content)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="applications & new members")
        )


bot = NocturneManager()


@bot.command(name="ping")
async def ping_cmd(ctx: commands.Context):
    """Simple sanity check to confirm prefix commands are working."""
    latency_ms = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Prefix commands are working. Latency: {latency_ms}ms")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ You need the **Manage Server** permission to use this command."
    elif isinstance(error, app_commands.CheckFailure):
        msg = "❌ You're not allowed to use this command."
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = f"⏳ Please wait {error.retry_after:.1f}s before trying again."
    else:
        msg = "⚠️ Something went wrong running this command. It's been logged."
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
        return  # ignore so a typo'd prefix command doesn't spam the channel
    if isinstance(error, commands.NotOwner):
        await ctx.send("❌ This command can only be used by the bot owner.")
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need the **Manage Server** permission to use this command.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ Missing a required argument: `{error.param.name}`. Check the command format.")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("⚠️ One of the arguments was in the wrong format. Check the command again.")
        return
    logger.exception("Prefix command error", exc_info=error)
    await ctx.send("⚠️ Something went wrong running this command. It's been logged.")


async def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Check your .env file or Railway environment variables.")
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
