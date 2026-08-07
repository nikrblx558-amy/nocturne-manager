"""
Ticket System — multi-category support tickets with a live-preview panel
builder, persistent Open/Claim/Close controls, per-category permissions,
and automatic transcript logging.
"""
import re
import io
import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import JSONStore
from utils.embed_builder import parse_color
from cogs.premium import get_limits

store = JSONStore("tickets.json")            # panel configs (per guild -> panels -> panel_id -> config)
ticket_store = JSONStore("ticket_channels.json")  # live ticket channel records (per guild -> channel_id -> record)

BUTTON_STYLE_MAP = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}

# Friendly aliases so staff can type colors instead of Discord's internal names.
BUTTON_STYLE_ALIASES = {
    "primary": "primary", "blurple": "primary", "blue": "primary",
    "secondary": "secondary", "grey": "secondary", "gray": "secondary",
    "success": "success", "green": "success",
    "danger": "danger", "red": "danger",
}
BUTTON_STYLE_DISPLAY = {"primary": "blurple", "secondary": "grey", "success": "green", "danger": "red"}


def parse_button_style(text: str, default: str = "primary") -> str:
    return BUTTON_STYLE_ALIASES.get((text or "").strip().lower(), default)


def make_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "panel"


def default_ticket_panel_config(name: str) -> dict:
    return {
        "name": name,
        "title": name,
        "description": "Need help? Click a button below to open a ticket.",
        "thumbnail": None,
        "banner": None,
        "color": "#8B0000",
        "footer": "",
        "footer_icon": None,
        "style": "buttons",   # "buttons" or "dropdown"
        "categories": [],
        "post_channel_id": None,
        "message_id": None,
    }


def default_category(label: str) -> dict:
    return {
        "id": make_slug(label),
        "label": label,
        "emoji": "🎫",
        "button_style": "primary",
        "welcome_message": "Thanks for opening a ticket! Support will be with you shortly.",
        "max_tickets_per_user": 1,
        "category_channel_id": None,   # Discord category the ticket channel is created under
        "log_channel_id": None,        # where the transcript gets posted when closed
        "support_role_ids": [],        # roles who can manage tickets of this category
        "required_role_id": None,      # role needed to open this category — None = anyone
    }


def build_ticket_panel_embed(config: dict) -> discord.Embed:
    embed = discord.Embed(
        title=config.get("title") or "Support Tickets",
        description=config.get("description") or "Click a button below to open a ticket.",
        color=discord.Color(parse_color(config.get("color"))),
    )
    thumb = config.get("thumbnail")
    if thumb and str(thumb).startswith("http"):
        embed.set_thumbnail(url=thumb)
    banner = config.get("banner")
    if banner and str(banner).startswith("http"):
        embed.set_image(url=banner)

    categories = config.get("categories", [])
    if categories:
        lines = [f"{cat.get('emoji') or '🎫'} **{cat['label']}**" for cat in categories]
        embed.add_field(name="Available Categories", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Available Categories", value="*No categories configured yet.*", inline=False)

    footer = config.get("footer") or "Nocturne Manager • Ticket System"
    footer_icon = config.get("footer_icon")
    if footer_icon and str(footer_icon).startswith("http"):
        embed.set_footer(text=footer, icon_url=footer_icon)
    else:
        embed.set_footer(text=footer)
    return embed


def build_open_view(guild_id, panel_id: str, config: dict) -> discord.ui.View | None:
    categories = config.get("categories", [])
    if not categories:
        return None
    view = discord.ui.View(timeout=None)
    if config.get("style") == "dropdown":
        options = [
            discord.SelectOption(label=cat["label"][:100], value=cat["id"], emoji=cat.get("emoji") or None)
            for cat in categories[:25]
        ]
        view.add_item(discord.ui.Select(
            placeholder="Select a ticket category...",
            options=options,
            custom_id=f"ntick:open_select:{guild_id}:{panel_id}",
            row=0,
        ))
    else:
        for i, cat in enumerate(categories[:25]):
            style = BUTTON_STYLE_MAP.get(cat.get("button_style", "primary"), discord.ButtonStyle.primary)
            view.add_item(discord.ui.Button(
                label=cat["label"][:80], emoji=cat.get("emoji") or None, style=style,
                custom_id=f"ntick:open:{guild_id}:{panel_id}:{cat['id']}", row=i // 5,
            ))
    return view


def build_ticket_control_view(guild_id, channel_id, claimed: bool = False) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    base = f"ntick:{{}}:{guild_id}:{channel_id}"
    view.add_item(discord.ui.Button(
        label="Claimed" if claimed else "Claim", emoji="🙋",
        style=discord.ButtonStyle.secondary if claimed else discord.ButtonStyle.primary,
        custom_id=base.format("claim"), disabled=claimed, row=0,
    ))
    view.add_item(discord.ui.Button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id=base.format("close"), row=0))
    view.add_item(discord.ui.Button(label="Close with Reason", emoji="📝", style=discord.ButtonStyle.danger, custom_id=base.format("close_reason"), row=0))
    return view


# ---------------------------------------------------------------------------
# MODALS — panel-level settings
# ---------------------------------------------------------------------------

class TickTitleModal(discord.ui.Modal, title="Set Title"):
    def __init__(self, view: "TicketBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(label="Panel Title", default=view.config.get("title") or "", max_length=256)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["title"] = self.input.value
        await self.view_ref.save_and_refresh(interaction)


class TickDescriptionModal(discord.ui.Modal, title="Set Description"):
    def __init__(self, view: "TicketBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(
            label="Panel Description", style=discord.TextStyle.paragraph,
            default=view.config.get("description") or "", max_length=4000, required=False,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["description"] = self.input.value
        await self.view_ref.save_and_refresh(interaction)


class TickThumbnailModal(discord.ui.Modal, title="Set Thumbnail"):
    def __init__(self, view: "TicketBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(label="Image URL", default=view.config.get("thumbnail") or "", max_length=300, required=False)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["thumbnail"] = self.input.value or None
        await self.view_ref.save_and_refresh(interaction)


class TickBannerModal(discord.ui.Modal, title="Set Banner"):
    def __init__(self, view: "TicketBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(label="Banner image URL", default=view.config.get("banner") or "", max_length=300, required=False)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["banner"] = self.input.value or None
        await self.view_ref.save_and_refresh(interaction)


class TickColorModal(discord.ui.Modal, title="Set Embed Color"):
    def __init__(self, view: "TicketBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(label="Hex color (e.g. #8B0000)", default=view.config.get("color", "#8B0000"), max_length=7)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.input.value.strip()
        if not val.startswith("#"):
            val = "#" + val
        self.view_ref.config["color"] = val
        await self.view_ref.save_and_refresh(interaction)


class TickFooterModal(discord.ui.Modal, title="Set Footer"):
    def __init__(self, view: "TicketBuilderView"):
        super().__init__()
        self.view_ref = view
        self.text_input = discord.ui.TextInput(
            label="Footer text (leave empty for default)", default=view.config.get("footer") or "",
            max_length=200, required=False,
        )
        self.icon_input = discord.ui.TextInput(
            label="Footer icon URL (optional)", default=view.config.get("footer_icon") or "",
            max_length=300, required=False,
        )
        self.add_item(self.text_input)
        self.add_item(self.icon_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["footer"] = self.text_input.value
        self.view_ref.config["footer_icon"] = self.icon_input.value or None
        await self.view_ref.save_and_refresh(interaction)


class AddCategoryModal(discord.ui.Modal, title="Add Ticket Category"):
    def __init__(self, view: "TicketBuilderView"):
        super().__init__()
        self.view_ref = view
        self.label_input = discord.ui.TextInput(label="Category Label", max_length=80)
        self.emoji_input = discord.ui.TextInput(label="Emoji (optional)", default="🎫", max_length=100, required=False)
        self.welcome_input = discord.ui.TextInput(
            label="Welcome message shown in the ticket", style=discord.TextStyle.paragraph,
            default="Thanks for opening a ticket! Support will be with you shortly.", max_length=1000, required=False,
        )
        self.max_input = discord.ui.TextInput(label="Max open tickets per user", default="1", max_length=2)
        self.add_item(self.label_input)
        self.add_item(self.emoji_input)
        self.add_item(self.welcome_input)
        self.add_item(self.max_input)

    async def on_submit(self, interaction: discord.Interaction):
        categories = self.view_ref.config.setdefault("categories", [])
        limit = self.view_ref.max_categories
        if len(categories) >= limit:
            upsell = "" if self.view_ref.is_premium else " Upgrade to Premium for more categories."
            await interaction.response.send_message(
                f"⚠️ This server's plan allows up to {limit} categories per panel.{upsell}", ephemeral=True
            )
            return

        try:
            max_tickets = max(0, int(self.max_input.value.strip()))
        except ValueError:
            max_tickets = 1

        slug = make_slug(self.label_input.value)
        base_slug, counter = slug, 2
        existing_ids = {c["id"] for c in categories}
        while slug in existing_ids:
            slug = f"{base_slug}-{counter}"
            counter += 1

        category = default_category(self.label_input.value)
        category["id"] = slug
        category["emoji"] = self.emoji_input.value or None
        category["welcome_message"] = self.welcome_input.value
        category["max_tickets_per_user"] = max_tickets
        categories.append(category)
        await self.view_ref.save_and_refresh(interaction)


class EditCategoryInfoModal(discord.ui.Modal, title="Edit Category"):
    def __init__(self, manage_view: "CategoryManageView"):
        super().__init__()
        self.manage_view = manage_view
        cat = manage_view.get_category()
        self.label_input = discord.ui.TextInput(label="Category Label", default=cat.get("label", ""), max_length=80)
        self.emoji_input = discord.ui.TextInput(label="Emoji (optional)", default=cat.get("emoji") or "", max_length=100, required=False)
        self.welcome_input = discord.ui.TextInput(
            label="Welcome message shown in the ticket", style=discord.TextStyle.paragraph,
            default=cat.get("welcome_message", ""), max_length=1000, required=False,
        )
        self.max_input = discord.ui.TextInput(label="Max open tickets per user", default=str(cat.get("max_tickets_per_user", 1)), max_length=2)
        self.style_input = discord.ui.TextInput(
            label="Button type: primary/secondary/success/danger",
            default=cat.get("button_style", "primary"), max_length=10, required=False,
        )
        self.add_item(self.label_input)
        self.add_item(self.emoji_input)
        self.add_item(self.welcome_input)
        self.add_item(self.max_input)
        self.add_item(self.style_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            max_tickets = max(0, int(self.max_input.value.strip()))
        except ValueError:
            max_tickets = 1
        style_value = self.style_input.value.strip().lower()
        if style_value not in BUTTON_STYLE_MAP:
            style_value = "primary"
        cat = self.manage_view.get_category()
        cat["label"] = self.label_input.value
        cat["emoji"] = self.emoji_input.value or None
        cat["welcome_message"] = self.welcome_input.value
        cat["max_tickets_per_user"] = max_tickets
        cat["button_style"] = style_value
        await self.manage_view.save_and_refresh(interaction)


# ---------------------------------------------------------------------------
# DYNAMIC SELECT COMPONENTS — main builder
# ---------------------------------------------------------------------------

class CategoryManageSelect(discord.ui.Select):
    def __init__(self, view: "TicketBuilderView"):
        self.view_ref = view
        categories = view.config.get("categories", [])
        options = []
        if not categories:
            options.append(discord.SelectOption(label="No categories yet — use Add Category first", value="none"))
        else:
            for cat in categories:
                options.append(discord.SelectOption(label=cat["label"][:100], value=cat["id"], emoji=cat.get("emoji") or None))
        super().__init__(placeholder="⚙️ Manage a category (roles, channels, etc.)...", options=options[:25], row=2)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.defer()
            return
        manage_view = CategoryManageView(self.view_ref.store, self.view_ref.guild, self.view_ref.panel_id, self.view_ref.config, self.values[0])
        await interaction.response.send_message(content=manage_view.header_text(), view=manage_view, ephemeral=True)
        manage_view.message = await interaction.original_response()


class PublishChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, outer: "PublishChannelPickView"):
        self.outer = outer
        super().__init__(placeholder="Choose a channel to post the panel in...", channel_types=[discord.ChannelType.text, discord.ChannelType.news])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel_id = self.values[0].id
        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(channel_id)
            except discord.HTTPException:
                await interaction.edit_original_response(content="❌ Couldn't find that channel. Please try again.", view=None)
                return

        embed = build_ticket_panel_embed(self.outer.config)
        open_view = build_open_view(self.outer.guild.id, self.outer.panel_id, self.outer.config)

        try:
            message = await channel.send(embed=embed, view=open_view)
        except discord.Forbidden:
            await interaction.edit_original_response(
                content=f"❌ I don't have permission to send messages in {channel.mention}.", view=None
            )
            return
        except discord.HTTPException as exc:
            await interaction.edit_original_response(content=f"❌ Failed to publish the panel: {exc}", view=None)
            return

        panels = await self.outer.store.get_path(str(self.outer.guild.id), "panels", default={})
        cfg = panels.get(self.outer.panel_id, self.outer.config)
        cfg["post_channel_id"] = channel.id
        cfg["message_id"] = message.id
        panels[self.outer.panel_id] = cfg
        await self.outer.store.set_path(str(self.outer.guild.id), "panels", panels)

        await interaction.edit_original_response(content=f"✅ Panel published to {channel.mention}!", view=None)


class PublishChannelPickView(discord.ui.View):
    def __init__(self, store: JSONStore, guild: discord.Guild, panel_id: str, config: dict):
        super().__init__(timeout=180)
        self.store = store
        self.guild = guild
        self.panel_id = panel_id
        self.config = config
        self.add_item(PublishChannelSelect(self))


# ---------------------------------------------------------------------------
# CATEGORY MANAGEMENT POPUP — its own 5-row view, separate from the main builder
# ---------------------------------------------------------------------------

class SupportRoleSelect(discord.ui.RoleSelect):
    def __init__(self, view: "CategoryManageView"):
        self.view_ref = view
        super().__init__(placeholder="Set support role(s) who can manage these tickets...", min_values=0, max_values=10, row=0)

    async def callback(self, interaction: discord.Interaction):
        cat = self.view_ref.get_category()
        cat["support_role_ids"] = [r.id for r in self.values]
        await self.view_ref.save_and_refresh(interaction)


class CategoryChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, view: "CategoryManageView"):
        self.view_ref = view
        super().__init__(placeholder="Set the Discord category tickets are created under...", channel_types=[discord.ChannelType.category], min_values=0, max_values=1, row=1)

    async def callback(self, interaction: discord.Interaction):
        cat = self.view_ref.get_category()
        cat["category_channel_id"] = self.values[0].id if self.values else None
        await self.view_ref.save_and_refresh(interaction)


class TicketLogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, view: "CategoryManageView"):
        self.view_ref = view
        super().__init__(placeholder="Set the transcript log channel for this category...", channel_types=[discord.ChannelType.text, discord.ChannelType.news], min_values=0, max_values=1, row=2)

    async def callback(self, interaction: discord.Interaction):
        cat = self.view_ref.get_category()
        cat["log_channel_id"] = self.values[0].id if self.values else None
        await self.view_ref.save_and_refresh(interaction)


class RequiredRoleSelect(discord.ui.RoleSelect):
    def __init__(self, view: "CategoryManageView"):
        self.view_ref = view
        super().__init__(placeholder="Set a role required to open this category (optional)...", min_values=0, max_values=1, row=3)

    async def callback(self, interaction: discord.Interaction):
        cat = self.view_ref.get_category()
        cat["required_role_id"] = self.values[0].id if self.values else None
        await self.view_ref.save_and_refresh(interaction)


class CategoryManageView(discord.ui.View):
    def __init__(self, store: JSONStore, guild: discord.Guild, panel_id: str, config: dict, category_id: str):
        super().__init__(timeout=300)
        self.store = store
        self.guild = guild
        self.panel_id = panel_id
        self.config = config
        self.category_id = category_id
        self.message: discord.Message | None = None
        self.add_item(SupportRoleSelect(self))
        self.add_item(CategoryChannelSelect(self))
        self.add_item(TicketLogChannelSelect(self))
        self.add_item(RequiredRoleSelect(self))

    def get_category(self) -> dict:
        for cat in self.config.get("categories", []):
            if cat["id"] == self.category_id:
                return cat
        # Shouldn't happen, but fall back to a throwaway dict so callbacks don't crash.
        return {}

    def header_text(self) -> str:
        cat = self.get_category()
        roles = ", ".join(f"<@&{rid}>" for rid in cat.get("support_role_ids", [])) or "*none (falls back to Manage Server permission)*"
        cat_channel = f"<#{cat['category_channel_id']}>" if cat.get("category_channel_id") else "*none*"
        log_channel = f"<#{cat['log_channel_id']}>" if cat.get("log_channel_id") else "*none (no auto-transcript)*"
        required_role = f"<@&{cat['required_role_id']}>" if cat.get("required_role_id") else "*anyone can open*"
        button_type = cat.get("button_style", "primary")
        return (
            f"### ⚙️ CATEGORY SETTINGS — {cat.get('label', self.category_id)}\n"
            f"Button type: **{button_type}**  •  Emoji: {cat.get('emoji') or '*none*'}\n"
            f"Support roles: {roles}\n"
            f"Ticket category channel: {cat_channel}\n"
            f"Log channel: {log_channel}\n"
            f"Required role to open: {required_role}\n"
            f"Max tickets per user: **{cat.get('max_tickets_per_user', 1)}**\n"
            f"-# Changes here save instantly. Use **Edit Info** to change label/emoji/welcome/max/button type. Close this message when you're done."
        )

    async def save_and_refresh(self, interaction: discord.Interaction):
        panels = await self.store.get_path(str(self.guild.id), "panels", default={})
        panels[self.panel_id] = self.config
        await self.store.set_path(str(self.guild.id), "panels", panels)
        content = self.header_text()
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, view=self)
        else:
            await interaction.response.edit_message(content=content, view=self)

    @discord.ui.button(label="Edit Info", emoji="📝", style=discord.ButtonStyle.secondary, row=4)
    async def btn_edit_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditCategoryInfoModal(self))

    @discord.ui.button(label="Remove Category", emoji="🗑️", style=discord.ButtonStyle.danger, row=4)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        categories = self.config.get("categories", [])
        self.config["categories"] = [c for c in categories if c["id"] != self.category_id]
        panels = await self.store.get_path(str(self.guild.id), "panels", default={})
        panels[self.panel_id] = self.config
        await self.store.set_path(str(self.guild.id), "panels", panels)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="🗑️ Category removed. Close this message.", view=self)
        self.stop()

    @discord.ui.button(label="Done", emoji="✅", style=discord.ButtonStyle.primary, row=4)
    async def btn_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


# ---------------------------------------------------------------------------
# MAIN BUILDER VIEW
# ---------------------------------------------------------------------------

class TicketBuilderView(discord.ui.View):
    def __init__(self, store: JSONStore, guild: discord.Guild, panel_id: str, config: dict, author_id: int, max_categories: int = None, is_premium: bool = False):
        super().__init__(timeout=600)
        self.store = store
        self.guild = guild
        self.panel_id = panel_id
        self.config = config
        self.author_id = author_id
        self.max_categories = max_categories or 2
        self.is_premium = is_premium
        self.message: discord.Message | None = None
        self._build_dynamic_items()

    def _build_dynamic_items(self):
        for item in list(self.children):
            if isinstance(item, CategoryManageSelect):
                self.remove_item(item)
        self.add_item(CategoryManageSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("⚠️ This builder panel isn't yours.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def render_embed(self) -> discord.Embed:
        return build_ticket_panel_embed(self.config)

    def header_text(self) -> str:
        plan = "💎 Premium" if self.is_premium else "🆓 Free"
        cat_count = len(self.config.get("categories", []))
        style = self.config.get("style", "buttons")
        published = f"<#{self.config['post_channel_id']}>" if self.config.get("post_channel_id") else "*not published yet*"
        return (
            f"### 🎫 TICKET PANEL BUILDER — {self.config.get('name', self.panel_id)}\n"
            f"Plan: {plan}  •  Categories: {cat_count}/{self.max_categories}  •  Opening style: **{style}**  •  Published in: {published}\n"
            f"-# This is a live preview of the panel embed. Use Publish once you're happy with it."
        )

    async def save_and_refresh(self, interaction: discord.Interaction):
        panels = await self.store.get_path(str(self.guild.id), "panels", default={})
        panels[self.panel_id] = self.config
        await self.store.set_path(str(self.guild.id), "panels", panels)

        self._build_dynamic_items()
        content = self.header_text()
        embed = self.render_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, embed=embed, view=self)
        else:
            await interaction.response.edit_message(content=content, embed=embed, view=self)

    # ---- Row 0 ----
    @discord.ui.button(label="Title", emoji="📝", style=discord.ButtonStyle.secondary, row=0)
    async def btn_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TickTitleModal(self))

    @discord.ui.button(label="Description", emoji="📄", style=discord.ButtonStyle.secondary, row=0)
    async def btn_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TickDescriptionModal(self))

    @discord.ui.button(label="Thumbnail", emoji="🖼️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_thumbnail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TickThumbnailModal(self))

    @discord.ui.button(label="Banner", emoji="🏳️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TickBannerModal(self))

    @discord.ui.button(label="Color", emoji="🎨", style=discord.ButtonStyle.secondary, row=0)
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TickColorModal(self))

    # ---- Row 1 ----
    @discord.ui.button(label="Footer", emoji="🔻", style=discord.ButtonStyle.secondary, row=1)
    async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TickFooterModal(self))

    @discord.ui.button(label="Add Category", emoji="➕", style=discord.ButtonStyle.secondary, row=1)
    async def btn_add_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddCategoryModal(self))

    @discord.ui.button(label="Toggle Style", emoji="🔀", style=discord.ButtonStyle.secondary, row=1)
    async def btn_toggle_style(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["style"] = "dropdown" if self.config.get("style", "buttons") == "buttons" else "buttons"
        await self.save_and_refresh(interaction)

    @discord.ui.button(label="Publish", emoji="📤", style=discord.ButtonStyle.success, row=1)
    async def btn_publish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.config.get("categories"):
            await interaction.response.send_message("⚠️ Add at least 1 category before publishing.", ephemeral=True)
            return
        pick_view = PublishChannelPickView(self.store, self.guild, self.panel_id, self.config)
        await interaction.response.send_message(
            "Select the channel to post this ticket panel in:", view=pick_view, ephemeral=True
        )

    @discord.ui.button(label="Reset", emoji="♻️", style=discord.ButtonStyle.danger, row=1)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        name = self.config.get("name", self.panel_id)
        self.config = default_ticket_panel_config(name)
        await self.save_and_refresh(interaction)

    # ---- Row 3 ----
    @discord.ui.button(label="Done", emoji="✅", style=discord.ButtonStyle.primary, row=3)
    async def btn_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        content = self.header_text() + "\n\n**Builder closed. Run `/ticket builder` again to edit.**"
        await interaction.response.edit_message(content=content, view=self)
        self.stop()


# ---------------------------------------------------------------------------
# ADD/REMOVE USER POPUP (used from ticket channel controls)
# ---------------------------------------------------------------------------

class UserActionSelect(discord.ui.UserSelect):
    def __init__(self, outer: "UserActionPickView"):
        self.outer = outer
        placeholder = "Choose a user to add..." if outer.action == "add" else "Choose a user to remove..."
        super().__init__(placeholder=placeholder, row=0)

    async def callback(self, interaction: discord.Interaction):
        user = self.values[0]
        channel = interaction.channel
        try:
            if self.outer.action == "add":
                await channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
                await interaction.response.edit_message(content=f"✅ Added {user.mention} to this ticket.", view=None)
                await channel.send(f"➕ {user.mention} was added to the ticket by {interaction.user.mention}.")
            else:
                await channel.set_permissions(user, overwrite=None)
                await interaction.response.edit_message(content=f"✅ Removed {user.mention} from this ticket.", view=None)
                await channel.send(f"➖ {user.mention} was removed from the ticket by {interaction.user.mention}.")
        except discord.Forbidden:
            await interaction.response.edit_message(content="❌ I don't have permission to modify channel permissions here.", view=None)


class UserActionPickView(discord.ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=120)
        self.action = action
        self.add_item(UserActionSelect(self))


class CloseReasonModal(discord.ui.Modal, title="Close Ticket with Reason"):
    def __init__(self, guild_id: str, channel_id: str):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.reason_input = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        cog: "TicketSystem" = interaction.client.get_cog("TicketSystem")
        await cog.close_ticket(interaction, self.guild_id, self.channel_id, reason=self.reason_input.value)


# ---------------------------------------------------------------------------
# COG
# ---------------------------------------------------------------------------

class TicketSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ticket_group = app_commands.Group(name="ticket", description="Create & manage ticket panels")

    async def panel_autocomplete(self, interaction: discord.Interaction, current: str):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        results = [
            app_commands.Choice(name=cfg.get("name", slug), value=slug)
            for slug, cfg in panels.items()
            if current.lower() in cfg.get("name", slug).lower()
        ]
        return results[:25]

    # ---------------- SLASH COMMANDS ----------------
    @ticket_group.command(name="new", description="Create a new ticket panel")
    @app_commands.describe(name="A name for this panel, e.g. 'Support Tickets'")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def new_panel(self, interaction: discord.Interaction, name: str):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        limits = await get_limits(interaction.guild_id)
        if len(panels) >= limits["max_ticket_panels"]:
            upsell = "" if limits["premium"] else " Upgrade to Premium for more panels."
            await interaction.response.send_message(
                f"⚠️ This server's plan allows up to {limits['max_ticket_panels']} ticket panel(s).{upsell}", ephemeral=True
            )
            return
        slug = make_slug(name)
        base_slug, counter = slug, 2
        while slug in panels:
            slug = f"{base_slug}-{counter}"
            counter += 1
        panels[slug] = default_ticket_panel_config(name)
        await store.set_path(str(interaction.guild_id), "panels", panels)
        await interaction.response.send_message(
            f"✅ Created ticket panel **{name}**. Use `/ticket builder` and select it to configure & publish it.", ephemeral=True
        )

    @ticket_group.command(name="builder", description="Open the live-preview builder for a ticket panel")
    @app_commands.describe(panel="Which panel to configure")
    @app_commands.autocomplete(panel=panel_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def builder_cmd(self, interaction: discord.Interaction, panel: str):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        if panel not in panels:
            await interaction.response.send_message("⚠️ Panel not found. Check `/ticket list`.", ephemeral=True)
            return
        limits = await get_limits(interaction.guild_id)
        view = TicketBuilderView(
            store, interaction.guild, panel, panels[panel], interaction.user.id,
            max_categories=limits["max_ticket_categories"], is_premium=limits["premium"],
        )
        await interaction.response.send_message(content=view.header_text(), embed=view.render_embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @ticket_group.command(name="list", description="List all ticket panels in this server")
    async def list_panels(self, interaction: discord.Interaction):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        if not panels:
            await interaction.response.send_message("No ticket panels yet. Use `/ticket new` to create one.", ephemeral=True)
            return
        lines = []
        for slug, cfg in panels.items():
            status = "✅ Published" if cfg.get("message_id") else "⏳ Draft"
            lines.append(f"• **{cfg.get('name', slug)}** `({slug})` — {status} — {len(cfg.get('categories', []))} categor(y/ies)")
        await interaction.response.send_message("**🎫 Ticket Panels**\n" + "\n".join(lines), ephemeral=True)

    @ticket_group.command(name="delete", description="Delete a ticket panel")
    @app_commands.describe(panel="Which panel to delete")
    @app_commands.autocomplete(panel=panel_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_panel(self, interaction: discord.Interaction, panel: str):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        if panel not in panels:
            await interaction.response.send_message("⚠️ Panel not found.", ephemeral=True)
            return
        name = panels.pop(panel).get("name", panel)
        await store.set_path(str(interaction.guild_id), "panels", panels)
        await interaction.response.send_message(
            f"🗑️ Deleted ticket panel **{name}**. Already-open tickets keep working, but the panel's buttons will stop opening new ones.",
            ephemeral=True,
        )

    # ---------------- PREFIX COMMANDS ----------------
    @commands.group(name="ticket", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def ticket_prefix(self, ctx: commands.Context):
        await ctx.send(
            "Usage:\n"
            f"`{ctx.prefix}ticket new <name>`\n"
            f"`{ctx.prefix}ticket builder <slug>`\n"
            f"`{ctx.prefix}ticket list`\n"
            f"`{ctx.prefix}ticket delete <slug>`"
        )

    @ticket_prefix.command(name="new")
    @commands.has_permissions(manage_guild=True)
    async def ticket_prefix_new(self, ctx: commands.Context, *, name: str):
        panels = await store.get_path(str(ctx.guild.id), "panels", default={})
        limits = await get_limits(ctx.guild.id)
        if len(panels) >= limits["max_ticket_panels"]:
            upsell = "" if limits["premium"] else " Upgrade to Premium for more panels."
            await ctx.send(f"⚠️ This server's plan allows up to {limits['max_ticket_panels']} ticket panel(s).{upsell}")
            return
        slug = make_slug(name)
        base_slug, counter = slug, 2
        while slug in panels:
            slug = f"{base_slug}-{counter}"
            counter += 1
        panels[slug] = default_ticket_panel_config(name)
        await store.set_path(str(ctx.guild.id), "panels", panels)
        await ctx.send(f"✅ Created ticket panel **{name}** (`{slug}`). Use `{ctx.prefix}ticket builder {slug}` to configure it.")

    @ticket_prefix.command(name="builder")
    @commands.has_permissions(manage_guild=True)
    async def ticket_prefix_builder(self, ctx: commands.Context, slug: str):
        panels = await store.get_path(str(ctx.guild.id), "panels", default={})
        if slug not in panels:
            await ctx.send(f"⚠️ Panel not found. Check `{ctx.prefix}ticket list`.")
            return
        limits = await get_limits(ctx.guild.id)
        view = TicketBuilderView(
            store, ctx.guild, slug, panels[slug], ctx.author.id,
            max_categories=limits["max_ticket_categories"], is_premium=limits["premium"],
        )
        message = await ctx.send(content=view.header_text(), embed=view.render_embed(), view=view)
        view.message = message

    @ticket_prefix.command(name="list")
    async def ticket_prefix_list(self, ctx: commands.Context):
        panels = await store.get_path(str(ctx.guild.id), "panels", default={})
        if not panels:
            await ctx.send("No ticket panels yet.")
            return
        lines = []
        for slug, cfg in panels.items():
            status = "✅ Published" if cfg.get("message_id") else "⏳ Draft"
            lines.append(f"• **{cfg.get('name', slug)}** `({slug})` — {status} — {len(cfg.get('categories', []))} categor(y/ies)")
        await ctx.send("**🎫 Ticket Panels**\n" + "\n".join(lines))

    @ticket_prefix.command(name="delete")
    @commands.has_permissions(manage_guild=True)
    async def ticket_prefix_delete(self, ctx: commands.Context, slug: str):
        panels = await store.get_path(str(ctx.guild.id), "panels", default={})
        if slug not in panels:
            await ctx.send("⚠️ Panel not found.")
            return
        name = panels.pop(slug).get("name", slug)
        await store.set_path(str(ctx.guild.id), "panels", panels)
        await ctx.send(f"🗑️ Deleted ticket panel **{name}**.")

    # ---------------- HELPERS ----------------
    def _can_manage(self, interaction: discord.Interaction, category: dict | None) -> bool:
        if interaction.user.guild_permissions.manage_guild:
            return True
        if not category:
            return False
        role_ids = category.get("support_role_ids", [])
        if not role_ids:
            return False
        member_role_ids = {r.id for r in getattr(interaction.user, "roles", [])}
        return any(rid in member_role_ids for rid in role_ids)

    async def _get_category(self, guild_id, panel_id, category_id) -> dict | None:
        panels = await store.get_path(str(guild_id), "panels", default={})
        panel = panels.get(panel_id)
        if not panel:
            return None
        for cat in panel.get("categories", []):
            if cat["id"] == category_id:
                return cat
        return None

    async def _get_ticket_record(self, guild_id, channel_id) -> dict | None:
        return await ticket_store.get_path(str(guild_id), str(channel_id), default=None)

    async def _save_ticket_record(self, guild_id, channel_id, record: dict):
        await ticket_store.set_path(str(guild_id), str(channel_id), record)

    async def _delete_ticket_record(self, guild_id, channel_id):
        data = await ticket_store.read()
        guild_data = data.get(str(guild_id), {})
        guild_data.pop(str(channel_id), None)
        data[str(guild_id)] = guild_data
        await ticket_store.write(data)

    async def _build_transcript(self, channel: discord.TextChannel) -> discord.File:
        lines = []
        async for message in channel.history(limit=1000, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = message.content or "[no text content]"
            lines.append(f"[{timestamp}] {message.author}: {content}")
        text = "\n".join(lines) if lines else "(no messages)"
        return discord.File(fp=io.BytesIO(text.encode("utf-8")), filename=f"transcript-{channel.name}.txt")

    # ---------------- RAW COMPONENT ROUTING (survives restarts) ----------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if custom_id.startswith("ntick:open_select:"):
            await self._handle_open_select(interaction, custom_id)
        elif custom_id.startswith("ntick:open:"):
            await self._handle_open_button(interaction, custom_id)
        elif custom_id.startswith("ntick:claim:"):
            await self._handle_claim(interaction, custom_id)
        elif custom_id.startswith("ntick:close_reason:"):
            await self._handle_close_reason(interaction, custom_id)
        elif custom_id.startswith("ntick:close:"):
            await self._handle_close(interaction, custom_id)
        elif custom_id.startswith("ntick:adduser:"):
            await self._handle_adduser(interaction, custom_id)
        elif custom_id.startswith("ntick:removeuser:"):
            await self._handle_removeuser(interaction, custom_id)
        elif custom_id.startswith("ntick:transcript:"):
            await self._handle_transcript(interaction, custom_id)
        elif custom_id.startswith("ntick:delete:"):
            await self._handle_delete(interaction, custom_id)
        elif custom_id.startswith("ntick:reopen:"):
            await self._handle_reopen(interaction, custom_id)

    # ---------------- OPEN TICKET ----------------
    async def _handle_open_button(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, panel_id, category_id = custom_id.split(":")
        await self._open_ticket(interaction, guild_id, panel_id, category_id)

    async def _handle_open_select(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, panel_id = custom_id.split(":")
        category_id = interaction.data["values"][0]
        await self._open_ticket(interaction, guild_id, panel_id, category_id)

    async def _open_ticket(self, interaction: discord.Interaction, guild_id: str, panel_id: str, category_id: str):
        panels = await store.get_path(str(guild_id), "panels", default={})
        panel = panels.get(panel_id)
        if not panel:
            await interaction.response.send_message("⚠️ This ticket panel is no longer available.", ephemeral=True)
            return
        category = next((c for c in panel.get("categories", []) if c["id"] == category_id), None)
        if not category:
            await interaction.response.send_message("⚠️ This ticket category is no longer available.", ephemeral=True)
            return

        required_role_id = category.get("required_role_id")
        if required_role_id:
            member_role_ids = {r.id for r in getattr(interaction.user, "roles", [])}
            if int(required_role_id) not in member_role_ids:
                await interaction.response.send_message(
                    f"⚠️ You need the <@&{required_role_id}> role to open this ticket type.", ephemeral=True
                )
                return

        max_tickets = category.get("max_tickets_per_user", 1)
        if max_tickets:
            all_tickets = await ticket_store.get_path(str(guild_id), default={})
            open_count = sum(
                1 for rec in all_tickets.values()
                if rec.get("opener_id") == interaction.user.id
                and rec.get("category_id") == category_id
                and rec.get("status") == "open"
            )
            if open_count >= max_tickets:
                await interaction.response.send_message(
                    f"⚠️ You already have {open_count} open ticket(s) of this type (limit: {max_tickets}). "
                    f"Please close it before opening another.", ephemeral=True
                )
                return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        parent = None
        cat_channel_id = category.get("category_channel_id")
        if cat_channel_id:
            possible_parent = guild.get_channel(int(cat_channel_id))
            if isinstance(possible_parent, discord.CategoryChannel):
                parent = possible_parent

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        for role_id in category.get("support_role_ids", []):
            role = guild.get_role(int(role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        safe_name = re.sub(r"[^a-z0-9-]", "-", interaction.user.name.lower()).strip("-") or "user"
        channel_name = f"ticket-{safe_name}"[:90]

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name, category=parent, overwrites=overwrites,
                reason=f"Ticket opened by {interaction.user} ({category['label']})",
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create channels in this server.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎫 {category['label']}",
            description=category.get("welcome_message") or "Thanks for opening a ticket! Support will be with you shortly.",
            color=discord.Color(parse_color(panel.get("color"))),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Opened by {interaction.user}")
        control_view = build_ticket_control_view(guild_id, ticket_channel.id)

        mention_roles = " ".join(f"<@&{rid}>" for rid in category.get("support_role_ids", []))
        content = f"{interaction.user.mention} {mention_roles}".strip()

        await ticket_channel.send(content=content or None, embed=embed, view=control_view)

        record = {
            "panel_id": panel_id,
            "category_id": category_id,
            "opener_id": interaction.user.id,
            "claimed_by": None,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "closed_by": None,
            "closed_at": None,
            "close_reason": None,
        }
        await self._save_ticket_record(guild_id, ticket_channel.id, record)

        await interaction.followup.send(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

    # ---------------- CLAIM ----------------
    async def _handle_claim(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, channel_id = custom_id.split(":")
        record = await self._get_ticket_record(guild_id, channel_id)
        if not record:
            await interaction.response.send_message("⚠️ This ticket record could not be found.", ephemeral=True)
            return
        if record.get("status") == "closed":
            await interaction.response.send_message("⚠️ This ticket is already closed.", ephemeral=True)
            return
        category = await self._get_category(guild_id, record["panel_id"], record["category_id"])
        if not self._can_manage(interaction, category):
            await interaction.response.send_message("❌ You don't have permission to manage this ticket.", ephemeral=True)
            return

        if record.get("claimed_by") == interaction.user.id:
            record["claimed_by"] = None
            await self._save_ticket_record(guild_id, channel_id, record)
            await interaction.response.send_message(f"🔓 {interaction.user.mention} unclaimed this ticket.")
        else:
            record["claimed_by"] = interaction.user.id
            await self._save_ticket_record(guild_id, channel_id, record)
            await interaction.response.send_message(f"🙋 {interaction.user.mention} claimed this ticket.")

    # ---------------- CLOSE ----------------
    async def _handle_close(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, channel_id = custom_id.split(":")
        await self.close_ticket(interaction, guild_id, channel_id, reason=None)

    async def _handle_close_reason(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, channel_id = custom_id.split(":")
        record = await self._get_ticket_record(guild_id, channel_id)
        category = await self._get_category(guild_id, record["panel_id"], record["category_id"]) if record else None
        if not self._can_manage(interaction, category):
            await interaction.response.send_message("❌ You don't have permission to close this ticket.", ephemeral=True)
            return
        await interaction.response.send_modal(CloseReasonModal(guild_id, channel_id))

    async def close_ticket(self, interaction: discord.Interaction, guild_id: str, channel_id: str, reason: str = None):
        record = await self._get_ticket_record(guild_id, channel_id)
        if not record:
            await interaction.response.send_message("⚠️ This ticket record could not be found.", ephemeral=True)
            return
        if record.get("status") == "closed":
            await interaction.response.send_message("⚠️ This ticket is already closed.", ephemeral=True)
            return
        category = await self._get_category(guild_id, record["panel_id"], record["category_id"])
        if not self._can_manage(interaction, category):
            await interaction.response.send_message("❌ You don't have permission to close this ticket.", ephemeral=True)
            return

        channel = interaction.channel
        opener = channel.guild.get_member(record["opener_id"])
        if opener:
            try:
                await channel.set_permissions(opener, send_messages=False)
            except discord.Forbidden:
                pass

        record["status"] = "closed"
        record["closed_by"] = interaction.user.id
        record["closed_at"] = datetime.now(timezone.utc).isoformat()
        record["close_reason"] = reason
        await self._save_ticket_record(guild_id, channel_id, record)

        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=(
                f"Closed by {interaction.user.mention}" + (f"\n**Reason:** {reason}" if reason else "") +
                f"\n\nThis channel will be **automatically deleted in {AUTO_DELETE_DELAY} seconds**. "
                f"Click **Reopen** before then to cancel, or **Delete Channel** to skip the wait."
            ),
            color=discord.Color(0x8B0000),
        )
        closed_view = build_closed_ticket_view(guild_id, channel_id)
        await interaction.response.send_message(embed=embed, view=closed_view)

        if category and category.get("log_channel_id"):
            log_channel = channel.guild.get_channel(int(category["log_channel_id"]))
            if log_channel:
                try:
                    transcript_file = await self._build_transcript(channel)
                    await log_channel.send(
                        content=f"📄 Transcript for **{channel.name}** (closed by {interaction.user.mention})",
                        file=transcript_file,
                    )
                except discord.HTTPException:
                    pass

        asyncio.create_task(self._auto_delete_after_delay(guild_id, channel_id))

    async def _auto_delete_after_delay(self, guild_id: str, channel_id, delay: int = None):
        await asyncio.sleep(delay if delay is not None else AUTO_DELETE_DELAY)
        record = await self._get_ticket_record(guild_id, channel_id)
        if not record or record.get("status") != "closed":
            return  # someone reopened it (or it's already gone) — leave it alone
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            try:
                await channel.delete(reason="Ticket auto-deleted after close timeout")
            except (discord.Forbidden, discord.NotFound):
                pass
        await self._delete_ticket_record(guild_id, channel_id)

    # ---------------- DELETE / REOPEN ----------------
    async def _handle_delete(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, channel_id = custom_id.split(":")
        record = await self._get_ticket_record(guild_id, channel_id)
        category = await self._get_category(guild_id, record["panel_id"], record["category_id"]) if record else None
        if not self._can_manage(interaction, category):
            await interaction.response.send_message("❌ You don't have permission to delete this ticket.", ephemeral=True)
            return
        await interaction.response.send_message("🗑️ Deleting this channel now...")
        try:
            await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except discord.Forbidden:
            pass
        except discord.NotFound:
            pass
        await self._delete_ticket_record(guild_id, channel_id)

    async def _handle_reopen(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, channel_id = custom_id.split(":")
        record = await self._get_ticket_record(guild_id, channel_id)
        if not record:
            await interaction.response.send_message("⚠️ This ticket record could not be found.", ephemeral=True)
            return
        category = await self._get_category(guild_id, record["panel_id"], record["category_id"])
        if not self._can_manage(interaction, category):
            await interaction.response.send_message("❌ You don't have permission to reopen this ticket.", ephemeral=True)
            return

        opener = interaction.guild.get_member(record["opener_id"])
        if opener:
            try:
                await interaction.channel.set_permissions(opener, view_channel=True, send_messages=True, read_message_history=True)
            except discord.Forbidden:
                pass

        record["status"] = "open"
        record["closed_by"] = None
        record["closed_at"] = None
        record["close_reason"] = None
        await self._save_ticket_record(guild_id, channel_id, record)

        await interaction.response.send_message(f"🔓 Ticket reopened by {interaction.user.mention}.")

    # ---------------- ADD / REMOVE USER ----------------
    async def _handle_adduser(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, channel_id = custom_id.split(":")
        record = await self._get_ticket_record(guild_id, channel_id)
        category = await self._get_category(guild_id, record["panel_id"], record["category_id"]) if record else None
        if not self._can_manage(interaction, category):
            await interaction.response.send_message("❌ You don't have permission to manage this ticket.", ephemeral=True)
            return
        view = UserActionPickView(action="add")
        await interaction.response.send_message("Select a user to add to this ticket:", view=view, ephemeral=True)

    async def _handle_removeuser(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, channel_id = custom_id.split(":")
        record = await self._get_ticket_record(guild_id, channel_id)
        category = await self._get_category(guild_id, record["panel_id"], record["category_id"]) if record else None
        if not self._can_manage(interaction, category):
            await interaction.response.send_message("❌ You don't have permission to manage this ticket.", ephemeral=True)
            return
        view = UserActionPickView(action="remove")
        await interaction.response.send_message("Select a user to remove from this ticket:", view=view, ephemeral=True)

    # ---------------- TRANSCRIPT ----------------
    async def _handle_transcript(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, channel_id = custom_id.split(":")
        record = await self._get_ticket_record(guild_id, channel_id)
        category = await self._get_category(guild_id, record["panel_id"], record["category_id"]) if record else None
        if not self._can_manage(interaction, category):
            await interaction.response.send_message("❌ You don't have permission to generate a transcript.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        transcript_file = await self._build_transcript(interaction.channel)
        await interaction.followup.send("📄 Transcript generated:", file=transcript_file, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketSystem(bot))
