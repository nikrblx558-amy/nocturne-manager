"""
/help command — built with Discord Components V2 (not classic embeds).

This is a pilot conversion: Components V2 is a newer, separate message-
building system (Container/TextDisplay/Section/MediaGallery/Separator)
that cannot be mixed with classic embeds in the same message. It requires
discord.py >= 2.6. Verified against the actually-installed discord.py
version in this project before writing this file.
"""
import json
import os

import discord
from discord import app_commands
from discord.ext import commands
from discord.components import MediaGalleryItem

from utils.branding import BOT_BANNER_URL

EMOJI_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "emojis.json")
PREFIX = os.getenv("PREFIX", "n!")
ACCENT_COLOR = 0x8B0000


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


def build_overview_text(bot: discord.Client) -> str:
    emojis = load_emojis()
    jl = emojis.get("help_joinleave", "📥")
    app = emojis.get("help_application", "📝")
    tick = emojis.get("help_tickets", "🎫")
    return (
        f"# {bot.user.name}\n"
        f"Hey! I'm **{bot.user.name}** — here to help manage your server.\n\n"
        f"{jl} **Join & Leave** — custom embeds for members joining/leaving\n"
        f"{app} **Applications** — build application panels with a live-preview builder\n"
        f"{tick} **Tickets** — multi-category support tickets with a live-preview builder\n\n"
        f"Use the dropdown below to see detailed commands for each category.\n"
        f"My prefix is `{PREFIX}` — slash commands (`/...`) always work too."
    )


def build_category_text(category_key: str) -> str:
    emojis = load_emojis()
    cat = CATEGORIES[category_key]
    emoji = emojis.get(cat["emoji_key"], "📁")
    lines = [f"# {emoji} {cat['label']} Commands", cat["description"], ""]
    for name, desc in cat["commands"]:
        lines.append(f"**`{name}`**\n{desc}")
    return "\n\n".join(lines)


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, outer: "HelpLayoutView"):
        self.outer = outer
        emojis = load_emojis()
        options = [
            discord.SelectOption(
                label="Overview", value="overview",
                emoji=emojis.get("help_overview", "🏠"),
                description="What I can do for your server",
            )
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
        self.outer.category = self.values[0]
        self.outer.rebuild()
        await interaction.response.edit_message(view=self.outer)


class HelpLayoutView(discord.ui.LayoutView):
    """Components V2 layout — replaces what used to be a classic Embed.
    Everything (text, banner, thumbnail, dropdown) lives inside one
    Container so it keeps the same accent-color side bar look an embed had."""

    def __init__(self, bot: discord.Client, category: str = "overview"):
        super().__init__(timeout=180)
        self.bot = bot
        self.category = category
        self.rebuild()

    def rebuild(self):
        for item in list(self.children):
            self.remove_item(item)

        text = build_overview_text(self.bot) if self.category not in CATEGORIES else build_category_text(self.category)

        header = discord.ui.Section(
            discord.ui.TextDisplay(text),
            accessory=discord.ui.Thumbnail(media=self.bot.user.display_avatar.url),
        )

        children = [header]
        if BOT_BANNER_URL:
            children.append(discord.ui.MediaGallery(MediaGalleryItem(media=BOT_BANNER_URL)))
        children.append(discord.ui.Separator())
        children.append(discord.ui.ActionRow(HelpCategorySelect(self)))

        container = discord.ui.Container(*children, accent_colour=discord.Color(ACCENT_COLOR))
        self.add_item(container)


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show what Nocturne Manager can do and how to use it")
    async def help_slash(self, interaction: discord.Interaction):
        view = HelpLayoutView(self.bot, "overview")
        await interaction.response.send_message(view=view, ephemeral=True)

    @commands.command(name="help", aliases=["commands", "cmds"])
    async def help_prefix(self, ctx: commands.Context):
        view = HelpLayoutView(self.bot, "overview")
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
