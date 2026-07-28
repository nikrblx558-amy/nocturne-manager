"""
/help command — a category dropdown panel showing every user-facing command,
auto-branded with the bot's own icon and banner.
"""
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

from utils.branding import BOT_BANNER_URL

EMOJI_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "emojis.json")
PREFIX = os.getenv("PREFIX", "n!")


def load_emojis() -> dict:
    try:
        with open(EMOJI_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CATEGORIES = {
    "joinleave": {
        "label": "Join & Leave",
        "emoji_key": "help_joinleave",
        "description": "Custom embeds sent when a member joins or leaves your server.",
        "commands": [
            ("/joinleave builder", "Open the live-preview embed builder for Join or Leave notifications."),
            ("/joinleave toggle", "Quickly enable/disable Join or Leave notifications."),
            ("/joinleave test", "Send a sample embed to the configured channel."),
            (f"{PREFIX}joinleave builder <join|leave>", "Prefix version of the builder."),
            (f"{PREFIX}joinleave toggle <join|leave> <on|off>", "Prefix version of toggle."),
            (f"{PREFIX}joinleave test <join|leave>", "Prefix version of test."),
        ],
    },
    "application": {
        "label": "Applications",
        "emoji_key": "help_application",
        "description": "Build application panels (staff applications, whitelists, etc.) with a live-preview builder.",
        "commands": [
            ("/application new", "Create a new application panel."),
            ("/application builder", "Open the live-preview builder for a panel — set questions, log channel, and publish it."),
            ("/application list", "List all application panels in this server."),
            ("/application delete", "Delete an application panel."),
            (f"{PREFIX}application new <name>", "Prefix version of new."),
            (f"{PREFIX}application builder <slug>", "Prefix version of builder."),
            (f"{PREFIX}application list", "Prefix version of list."),
            (f"{PREFIX}application delete <slug>", "Prefix version of delete."),
        ],
    },
    "tickets": {
        "label": "Tickets",
        "emoji_key": "help_tickets",
        "description": "Multi-category support tickets with a live-preview builder — Claim, Close, Add/Remove User, Transcript, and more.",
        "commands": [
            ("/ticket new", "Create a new ticket panel."),
            ("/ticket builder", "Open the live-preview builder — add categories, set roles/channels, and publish it."),
            ("/ticket list", "List all ticket panels in this server."),
            ("/ticket delete", "Delete a ticket panel."),
            (f"{PREFIX}ticket new <name>", "Prefix version of new."),
            (f"{PREFIX}ticket builder <slug>", "Prefix version of builder."),
            (f"{PREFIX}ticket list", "Prefix version of list."),
            (f"{PREFIX}ticket delete <slug>", "Prefix version of delete."),
        ],
    },
}


def build_help_embed(bot: discord.Client, category: str = "overview") -> discord.Embed:
    emojis = load_emojis()
    color = discord.Color(0x8B0000)

    if category == "overview" or category not in CATEGORIES:
        jl_emoji = emojis.get("help_joinleave", "📥")
        app_emoji = emojis.get("help_application", "📝")
        tick_emoji = emojis.get("help_tickets", "🎫")
        embed = discord.Embed(
            title=bot.user.name,
            description=(
                f"Hey! I'm **{bot.user.name}** — here to help manage your server.\n\n"
                f"{jl_emoji} **Join & Leave** — custom embeds for members joining/leaving\n"
                f"{app_emoji} **Applications** — build application panels with a live-preview builder\n"
                f"{tick_emoji} **Tickets** — multi-category support tickets with a live-preview builder\n\n"
                f"Use the dropdown below to see detailed commands for each category.\n"
                f"My prefix is `{PREFIX}` — slash commands (`/...`) always work too."
            ),
            color=color,
        )
    else:
        cat = CATEGORIES[category]
        emoji = emojis.get(cat["emoji_key"], "📁")
        embed = discord.Embed(
            title=f"{emoji} {cat['label']} Commands",
            description=cat["description"],
            color=color,
        )
        for name, desc in cat["commands"]:
            embed.add_field(name=f"`{name}`", value=desc, inline=False)

    embed.set_thumbnail(url=bot.user.display_avatar.url)
    if BOT_BANNER_URL:
        embed.set_image(url=BOT_BANNER_URL)
    embed.set_footer(text=f"{bot.user.name} • Help")
    return embed


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, bot: discord.Client):
        self.bot = bot
        emojis = load_emojis()
        options = [
            discord.SelectOption(
                label="Overview", value="overview",
                emoji=emojis.get("help_overview", "🏠"),
                description="What I can do for your server",
            ),
        ]
        for key, cat in CATEGORIES.items():
            options.append(
                discord.SelectOption(
                    label=cat["label"], value=key,
                    emoji=emojis.get(cat["emoji_key"], "📁"),
                    description=cat["description"][:100],
                )
            )
        super().__init__(placeholder="📂 Select a category for detailed commands...", options=options)

    async def callback(self, interaction: discord.Interaction):
        embed = build_help_embed(self.bot, self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot: discord.Client):
        super().__init__(timeout=180)
        self.add_item(HelpCategorySelect(bot))


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show what Nocturne Manager can do and how to use it")
    async def help_slash(self, interaction: discord.Interaction):
        embed = build_help_embed(self.bot, "overview")
        await interaction.response.send_message(embed=embed, view=HelpView(self.bot), ephemeral=True)

    @commands.command(name="help", aliases=["commands", "cmds"])
    async def help_prefix(self, ctx: commands.Context):
        embed = build_help_embed(self.bot, "overview")
        await ctx.send(embed=embed, view=HelpView(self.bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
