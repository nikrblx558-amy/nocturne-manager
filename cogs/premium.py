"""
Premium Lock system.

Prefix commands ONLY (no slash commands) — these are owner-only management
tools, so they're intentionally kept out of the public slash command picker
that every server member can see.

To lock a NEW feature behind premium: add a Free/Premium constant pair below,
include it in `get_limits()`, then check the relevant limit wherever that
feature is used (see cogs/application.py and cogs/panel_builder.py for
examples already wired up).
"""
import discord
from discord.ext import commands

from utils.storage import JSONStore

store = JSONStore("premium.json")

# ---------------------------------------------------------------------------
# Default Free / Premium limits. A server on Premium can still get a fully
# custom value for any of these via `setlimit` — these are just the defaults
# applied when `grant` is used without custom numbers.
# ---------------------------------------------------------------------------
FREE_MAX_QUESTIONS = 7       # questions per application panel
PREMIUM_MAX_QUESTIONS = 25

FREE_MAX_PANELS = 1          # application panels per server
PREMIUM_MAX_PANELS = 10

FREE_MAX_ROW_LINKS = 1       # link buttons per join/leave embed
PREMIUM_MAX_ROW_LINKS = 5

FREE_MAX_TICKET_PANELS = 1        # ticket panels per server
PREMIUM_MAX_TICKET_PANELS = 5

FREE_MAX_TICKET_CATEGORIES = 2    # categories per ticket panel
PREMIUM_MAX_TICKET_CATEGORIES = 10

# Maps the friendly name used in commands -> the actual key stored in JSON.
LIMIT_KEYS = {
    "questions": "max_questions",
    "panels": "max_panels",
    "row_links": "max_row_links",
    "links": "max_row_links",
    "ticket_panels": "max_ticket_panels",
    "ticket_categories": "max_ticket_categories",
}


async def get_limits(guild_id: int) -> dict:
    """Single source of truth other cogs call to check what a server can do.
    Free servers always get the fixed Free values. Premium servers get their
    own custom value if one was set via `setlimit`, otherwise the Premium
    default."""
    data = await store.get_path(str(guild_id), default={})
    premium = bool(data.get("premium"))
    if premium:
        return {
            "premium": True,
            "max_questions": data.get("max_questions", PREMIUM_MAX_QUESTIONS),
            "max_panels": data.get("max_panels", PREMIUM_MAX_PANELS),
            "max_row_links": data.get("max_row_links", PREMIUM_MAX_ROW_LINKS),
            "max_ticket_panels": data.get("max_ticket_panels", PREMIUM_MAX_TICKET_PANELS),
            "max_ticket_categories": data.get("max_ticket_categories", PREMIUM_MAX_TICKET_CATEGORIES),
        }
    return {
        "premium": False,
        "max_questions": FREE_MAX_QUESTIONS,
        "max_panels": FREE_MAX_PANELS,
        "max_row_links": FREE_MAX_ROW_LINKS,
        "max_ticket_panels": FREE_MAX_TICKET_PANELS,
        "max_ticket_categories": FREE_MAX_TICKET_CATEGORIES,
    }


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="premium", aliases=["prem", "plan"], invoke_without_command=True)
    async def premium_group(self, ctx: commands.Context):
        """Anyone can check the current server's plan — only the subcommands
        below (grant/revoke/setlimit/list) are owner-only."""
        limits = await get_limits(ctx.guild.id)
        tier = "💎 Premium" if limits["premium"] else "🆓 Free"
        await ctx.send(
            f"Current plan: **{tier}**\n"
            f"• Max questions per application panel: **{limits['max_questions']}**\n"
            f"• Max application panels: **{limits['max_panels']}**\n"
            f"• Max link buttons per join/leave embed: **{limits['max_row_links']}**"
        )

    @premium_group.command(name="grant", aliases=["add", "upgrade"])
    @commands.is_owner()
    async def grant(
        self,
        ctx: commands.Context,
        guild_id: int,
        max_questions: int = None,
        max_panels: int = None,
        max_row_links: int = None,
    ):
        """Usage: n!premium grant <guild_id> [max_questions] [max_panels] [max_row_links]
        Any number left out falls back to the default Premium value."""
        data = await store.get_path(str(guild_id), default={})
        data["premium"] = True
        data["granted_by"] = ctx.author.id
        if max_questions is not None:
            data["max_questions"] = max_questions
        if max_panels is not None:
            data["max_panels"] = max_panels
        if max_row_links is not None:
            data["max_row_links"] = max_row_links
        await store.set_path(str(guild_id), data)

        guild = self.bot.get_guild(guild_id)
        name = guild.name if guild else f"`{guild_id}`"
        await ctx.send(
            f"✅ Premium granted to **{name}**.\n"
            f"Limits — questions: **{data.get('max_questions', PREMIUM_MAX_QUESTIONS)}**, "
            f"panels: **{data.get('max_panels', PREMIUM_MAX_PANELS)}**, "
            f"link buttons: **{data.get('max_row_links', PREMIUM_MAX_ROW_LINKS)}**"
        )

    @premium_group.command(name="revoke", aliases=["remove", "downgrade"])
    @commands.is_owner()
    async def revoke(self, ctx: commands.Context, guild_id: int):
        data = await store.get_path(str(guild_id), default={})
        data["premium"] = False
        await store.set_path(str(guild_id), data)
        guild = self.bot.get_guild(guild_id)
        name = guild.name if guild else f"`{guild_id}`"
        await ctx.send(f"✅ Premium revoked from **{name}**.")

    @premium_group.command(name="setlimit", aliases=["limit", "set"])
    @commands.is_owner()
    async def setlimit(self, ctx: commands.Context, guild_id: int, key: str, value: int):
        """Usage: n!premium setlimit <guild_id> <questions|panels|row_links> <value>
        Only works on servers that already have Premium — use `grant` first."""
        limit_key = LIMIT_KEYS.get(key.lower())
        if not limit_key:
            options = ", ".join(sorted(set(LIMIT_KEYS)))
            await ctx.send(f"⚠️ Unknown limit `{key}`. Valid options: {options}")
            return
        data = await store.get_path(str(guild_id), default={})
        if not data.get("premium"):
            await ctx.send("⚠️ That server isn't Premium yet. Use `grant` first.")
            return
        data[limit_key] = value
        await store.set_path(str(guild_id), data)
        guild = self.bot.get_guild(guild_id)
        name = guild.name if guild else f"`{guild_id}`"
        await ctx.send(f"✅ Set **{key}** limit to **{value}** for **{name}**.")

    @premium_group.command(name="list", aliases=["all"])
    @commands.is_owner()
    async def list_premium(self, ctx: commands.Context):
        all_data = await store.read()
        premium_ids = [gid for gid, d in all_data.items() if d.get("premium")]
        if not premium_ids:
            await ctx.send("No servers have premium yet.")
            return
        lines = []
        for gid in premium_ids:
            d = all_data[gid]
            guild = self.bot.get_guild(int(gid))
            name = guild.name if guild else "Unknown (bot not in this server)"
            lines.append(
                f"• **{name}** (`{gid}`) — questions: {d.get('max_questions', PREMIUM_MAX_QUESTIONS)}, "
                f"panels: {d.get('max_panels', PREMIUM_MAX_PANELS)}, "
                f"links: {d.get('max_row_links', PREMIUM_MAX_ROW_LINKS)}"
            )
        await ctx.send("**💎 Premium Servers**\n" + "\n".join(lines))


async def setup(bot: commands.Bot):
    await bot.add_cog(Premium(bot))
