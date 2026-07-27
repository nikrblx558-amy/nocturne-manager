"""
Application System — a full replacement for the old Status Bot feature.

Lets staff build application panels (like a job application / staff
recruitment form) with a live-preview builder, publish them with a persistent
"Apply" button, collect answers via a DM conversation (bot asks each question
one at a time in the user's DMs), and review submissions with Accept/Deny
buttons in a log channel.
"""
import re
import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import JSONStore
from utils.embed_builder import parse_color
from utils.branding import BOT_INVITE_URL, SUPPORT_SERVER_URL, BOT_BANNER_URL
from cogs.premium import get_limits, PREMIUM_MAX_QUESTIONS

store = JSONStore("applications.json")
history_store = JSONStore("submissions.json")

MAX_QUESTIONS = 25      # Discord embeds allow a maximum of 25 fields, used to display Q&A
ANSWER_TIMEOUT = 600    # seconds to wait for a reply to each DM question


def make_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "panel"


def default_application_config(name: str) -> dict:
    return {
        "name": name,
        "title": name,
        "description": "Click the button below to apply.",
        "thumbnail": None,
        "banner": None,
        "color": "#8B0000",
        "footer": "",
        "footer_icon": None,
        "button_label": "Apply Now",
        "button_emoji": "📝",
        "questions": [],
        "log_channel_id": None,
        "post_channel_id": None,
        "message_id": None,
    }


def build_application_embed(config: dict) -> discord.Embed:
    embed = discord.Embed(
        title=config.get("title") or "Application",
        description=config.get("description") or "Click the button below to apply.",
        color=discord.Color(parse_color(config.get("color"))),
    )
    thumb = config.get("thumbnail")
    if thumb and str(thumb).startswith("http"):
        embed.set_thumbnail(url=thumb)
    banner = config.get("banner")
    if banner and str(banner).startswith("http"):
        embed.set_image(url=banner)
    footer = config.get("footer") or "Nocturne Manager • Application System"
    footer_icon = config.get("footer_icon")
    if footer_icon and str(footer_icon).startswith("http"):
        embed.set_footer(text=footer, icon_url=footer_icon)
    else:
        embed.set_footer(text=footer)
    return embed


def build_apply_view(guild_id: int, panel_id: str, config: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label=(config.get("button_label") or "Apply Now")[:80],
            emoji=config.get("button_emoji") or None,
            style=discord.ButtonStyle.primary,
            custom_id=f"napp:apply:{guild_id}:{panel_id}",
        )
    )
    return view


def build_decision_view(
    guild_id: int, panel_id: str, applicant_id: int, message_id: int,
    jump_url: str = None, decided: bool = False,
) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    base = f"napp:decision:{guild_id}:{panel_id}:{applicant_id}"

    # Row 0 — the actual decision actions. Disabled once a decision is made.
    view.add_item(discord.ui.Button(
        label="Accept", style=discord.ButtonStyle.success,
        custom_id=f"{base}:accept:{message_id}", disabled=decided, row=0,
    ))
    view.add_item(discord.ui.Button(
        label="Deny", style=discord.ButtonStyle.danger,
        custom_id=f"{base}:deny:{message_id}", disabled=decided, row=0,
    ))
    view.add_item(discord.ui.Button(
        label="Accept with reason", style=discord.ButtonStyle.success,
        custom_id=f"{base}:accept_reason:{message_id}", disabled=decided, row=0,
    ))
    view.add_item(discord.ui.Button(
        label="Deny with reason", style=discord.ButtonStyle.danger,
        custom_id=f"{base}:deny_reason:{message_id}", disabled=decided, row=0,
    ))

    # Row 1 — utility actions, stay enabled even after a decision is made.
    view.add_item(discord.ui.Button(
        label="History", style=discord.ButtonStyle.primary,
        custom_id=f"napp:history:{guild_id}:{applicant_id}", row=1,
    ))
    view.add_item(discord.ui.Button(
        label="Open Ticket with User", style=discord.ButtonStyle.secondary,
        custom_id=f"napp:ticket:{guild_id}:{applicant_id}", row=1,
    ))
    if jump_url:
        view.add_item(discord.ui.Button(label="Jump to Message", style=discord.ButtonStyle.link, url=jump_url, row=1))

    return view


class ReasonModal(discord.ui.Modal):
    """Opened when staff clicks 'Accept with reason' / 'Deny with reason'."""

    def __init__(self, guild_id: str, panel_id: str, applicant_id: str, message_id: str, action: str):
        super().__init__(title="Accept with Reason" if action == "accept" else "Deny with Reason")
        self.guild_id = guild_id
        self.panel_id = panel_id
        self.applicant_id = applicant_id
        self.message_id = message_id
        self.action = action
        self.reason_input = discord.ui.TextInput(
            label="Reason", style=discord.TextStyle.paragraph, max_length=500, required=True
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        cog: "ApplicationSystem" = interaction.client.get_cog("ApplicationSystem")
        await cog.apply_decision(
            interaction, self.guild_id, self.panel_id, self.applicant_id,
            self.message_id, self.action, reason=self.reason_input.value,
        )


# ---------------------------------------------------------------------------
# MODALS
# ---------------------------------------------------------------------------

class AppTitleModal(discord.ui.Modal, title="Set Title"):
    def __init__(self, view: "ApplicationBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(label="Panel Title", default=view.config.get("title") or "", max_length=256)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["title"] = self.input.value
        await self.view_ref.save_and_refresh(interaction)


class AppDescriptionModal(discord.ui.Modal, title="Set Description"):
    def __init__(self, view: "ApplicationBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(
            label="Panel Description",
            style=discord.TextStyle.paragraph,
            default=view.config.get("description") or "",
            max_length=4000,
            required=False,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["description"] = self.input.value
        await self.view_ref.save_and_refresh(interaction)


class AppThumbnailModal(discord.ui.Modal, title="Set Thumbnail"):
    def __init__(self, view: "ApplicationBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(
            label="Image URL", default=view.config.get("thumbnail") or "", max_length=300, required=False
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["thumbnail"] = self.input.value or None
        await self.view_ref.save_and_refresh(interaction)


class AppBannerModal(discord.ui.Modal, title="Set Banner"):
    def __init__(self, view: "ApplicationBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(
            label="Banner image URL", default=view.config.get("banner") or "", max_length=300, required=False
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["banner"] = self.input.value or None
        await self.view_ref.save_and_refresh(interaction)


class AppColorModal(discord.ui.Modal, title="Set Embed Color"):
    def __init__(self, view: "ApplicationBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(
            label="Hex color (e.g. #8B0000)", default=view.config.get("color", "#8B0000"), max_length=7
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.input.value.strip()
        if not val.startswith("#"):
            val = "#" + val
        self.view_ref.config["color"] = val
        await self.view_ref.save_and_refresh(interaction)


class AppFooterModal(discord.ui.Modal, title="Set Footer"):
    def __init__(self, view: "ApplicationBuilderView"):
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


class ButtonLabelModal(discord.ui.Modal, title="Set Apply Button Label"):
    def __init__(self, view: "ApplicationBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(
            label="Button label", default=view.config.get("button_label") or "Apply Now", max_length=80
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["button_label"] = self.input.value
        await self.view_ref.save_and_refresh(interaction)


class ButtonEmojiModal(discord.ui.Modal, title="Set Apply Button Emoji"):
    def __init__(self, view: "ApplicationBuilderView"):
        super().__init__()
        self.view_ref = view
        self.input = discord.ui.TextInput(
            label="Emoji (e.g. 📝 or <:name:id>), optional",
            default=view.config.get("button_emoji") or "",
            max_length=100,
            required=False,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["button_emoji"] = self.input.value or None
        await self.view_ref.save_and_refresh(interaction)


class AddQuestionModal(discord.ui.Modal, title="Add Question"):
    def __init__(self, view: "ApplicationBuilderView"):
        super().__init__()
        self.view_ref = view
        self.label_input = discord.ui.TextInput(label="Question text", max_length=200)
        self.style_input = discord.ui.TextInput(
            label="Answer style: short or paragraph", default="short", max_length=10
        )
        self.add_item(self.label_input)
        self.add_item(self.style_input)

    async def on_submit(self, interaction: discord.Interaction):
        questions = self.view_ref.config.setdefault("questions", [])
        limit = self.view_ref.max_questions
        if len(questions) >= limit:
            if self.view_ref.is_premium:
                msg = f"⚠️ Maximum of {limit} questions (Discord embed field limit)."
            else:
                msg = f"⚠️ The Free plan allows up to {limit} questions. Upgrade to Premium for up to {PREMIUM_MAX_QUESTIONS}."
            await interaction.response.send_message(msg, ephemeral=True)
            return
        style = "paragraph" if self.style_input.value.strip().lower().startswith("p") else "short"
        questions.append({"label": self.label_input.value, "style": style})
        await self.view_ref.save_and_refresh(interaction)


# ---------------------------------------------------------------------------
# DYNAMIC SELECT COMPONENTS
# ---------------------------------------------------------------------------

class QuestionRemoveSelect(discord.ui.Select):
    def __init__(self, view: "ApplicationBuilderView"):
        self.view_ref = view
        questions = view.config.get("questions", [])
        options = []
        if not questions:
            options.append(discord.SelectOption(label="No questions yet", value="none"))
        else:
            for i, q in enumerate(questions):
                options.append(discord.SelectOption(label=f"#{i + 1} — {q['label']}"[:100], value=str(i)))
        super().__init__(placeholder="🗑️ Remove a question...", options=options[:25], row=2)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "none":
            await interaction.response.defer()
            return
        idx = int(val)
        questions = self.view_ref.config.get("questions", [])
        if 0 <= idx < len(questions):
            questions.pop(idx)
        await self.view_ref.save_and_refresh(interaction)


class LogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, view: "ApplicationBuilderView"):
        self.view_ref = view
        super().__init__(
            placeholder="📌 Set the log channel (where submissions are reviewed)...",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.config["log_channel_id"] = self.values[0].id
        await self.view_ref.save_and_refresh(interaction)


class PublishChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, outer: "PublishChannelPickView"):
        self.outer = outer
        super().__init__(placeholder="Choose a channel to post the panel in...", channel_types=[discord.ChannelType.text, discord.ChannelType.news])

    async def callback(self, interaction: discord.Interaction):
        # Acknowledge immediately so Discord doesn't time out the interaction
        # while we send the message + write to storage below.
        await interaction.response.defer(ephemeral=True)

        # discord.ui.ChannelSelect.values returns lightweight AppCommandChannel
        # objects (no .send()), NOT the real channel — resolve it properly first.
        channel_id = self.values[0].id
        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(channel_id)
            except discord.HTTPException:
                await interaction.edit_original_response(
                    content="❌ Couldn't find that channel. Please try again.", view=None
                )
                return

        embed = build_application_embed(self.outer.config)
        apply_view = build_apply_view(self.outer.guild.id, self.outer.panel_id, self.outer.config)

        try:
            message = await channel.send(embed=embed, view=apply_view)
        except discord.Forbidden:
            await interaction.edit_original_response(
                content=f"❌ I don't have permission to send messages in {channel.mention}. "
                        f"Please check my permissions there (View Channel, Send Messages, Embed Links) and try again.",
                view=None,
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
# MAIN BUILDER VIEW
# ---------------------------------------------------------------------------

class ApplicationBuilderView(discord.ui.View):
    def __init__(self, store: JSONStore, guild: discord.Guild, panel_id: str, config: dict, author_id: int, max_questions: int = None, is_premium: bool = False):
        super().__init__(timeout=600)
        self.store = store
        self.guild = guild
        self.panel_id = panel_id
        self.config = config
        self.author_id = author_id
        self.max_questions = max_questions or MAX_QUESTIONS
        self.is_premium = is_premium
        self.message: discord.Message | None = None
        self._build_dynamic_items()

    def _build_dynamic_items(self):
        for item in list(self.children):
            if isinstance(item, (QuestionRemoveSelect, LogChannelSelect)):
                self.remove_item(item)
        self.add_item(QuestionRemoveSelect(self))
        self.add_item(LogChannelSelect(self))

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
        return build_application_embed(self.config)

    def header_text(self) -> str:
        log_channel = f"<#{self.config['log_channel_id']}>" if self.config.get("log_channel_id") else "*not set*"
        published = f"<#{self.config['post_channel_id']}>" if self.config.get("post_channel_id") else "*not published yet*"
        q_count = len(self.config.get("questions", []))
        plan = "💎 Premium" if self.is_premium else "🆓 Free"
        return (
            f"### 🛠️ APPLICATION PANEL BUILDER — {self.config.get('name', self.panel_id)}\n"
            f"Plan: {plan}  •  Log channel: {log_channel}  •  Questions: {q_count}/{self.max_questions}  •  Published in: {published}\n"
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
        await interaction.response.send_modal(AppTitleModal(self))

    @discord.ui.button(label="Description", emoji="📄", style=discord.ButtonStyle.secondary, row=0)
    async def btn_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppDescriptionModal(self))

    @discord.ui.button(label="Thumbnail", emoji="🖼️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_thumbnail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppThumbnailModal(self))

    @discord.ui.button(label="Banner", emoji="🏳️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppBannerModal(self))

    @discord.ui.button(label="Color", emoji="🎨", style=discord.ButtonStyle.secondary, row=0)
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppColorModal(self))

    # ---- Row 1 ----
    @discord.ui.button(label="Footer", emoji="🔻", style=discord.ButtonStyle.secondary, row=1)
    async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppFooterModal(self))

    @discord.ui.button(label="Button Label", emoji="🔤", style=discord.ButtonStyle.secondary, row=1)
    async def btn_button_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ButtonLabelModal(self))

    @discord.ui.button(label="Button Emoji", emoji="🙂", style=discord.ButtonStyle.secondary, row=1)
    async def btn_button_emoji(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ButtonEmojiModal(self))

    @discord.ui.button(label="Add Question", emoji="➕", style=discord.ButtonStyle.secondary, row=1)
    async def btn_add_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddQuestionModal(self))

    # ---- Row 4 ----
    @discord.ui.button(label="Publish", emoji="📤", style=discord.ButtonStyle.success, row=4)
    async def btn_publish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.config.get("log_channel_id"):
            await interaction.response.send_message("⚠️ Please set a Log Channel before publishing.", ephemeral=True)
            return
        if not self.config.get("questions"):
            await interaction.response.send_message("⚠️ Add at least 1 question before publishing.", ephemeral=True)
            return
        pick_view = PublishChannelPickView(self.store, self.guild, self.panel_id, self.config)
        await interaction.response.send_message(
            "Select the channel to post this application panel in:", view=pick_view, ephemeral=True
        )

    @discord.ui.button(label="Reset", emoji="♻️", style=discord.ButtonStyle.danger, row=4)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        name = self.config.get("name", self.panel_id)
        self.config = default_application_config(name)
        await self.save_and_refresh(interaction)

    @discord.ui.button(label="Done", emoji="✅", style=discord.ButtonStyle.primary, row=4)
    async def btn_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        content = self.header_text() + "\n\n**Builder closed. Run `/application builder` again to edit.**"
        await interaction.response.edit_message(content=content, view=self)
        self.stop()


# ---------------------------------------------------------------------------
# COG
# ---------------------------------------------------------------------------

class ApplicationSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Tracks user IDs currently filling out an application via DM, so we
        # can block a second concurrent Apply click while one is in progress.
        self.active_applications: set = set()

    app_group = app_commands.Group(name="application", description="Create & manage application panels")

    async def panel_autocomplete(self, interaction: discord.Interaction, current: str):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        results = [
            app_commands.Choice(name=cfg.get("name", slug), value=slug)
            for slug, cfg in panels.items()
            if current.lower() in cfg.get("name", slug).lower()
        ]
        return results[:25]

    # ---------------- SLASH COMMANDS ----------------
    @app_group.command(name="new", description="Create a new application panel")
    @app_commands.describe(name="A name for this panel, e.g. 'Staff Application'")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def new_panel(self, interaction: discord.Interaction, name: str):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        limits = await get_limits(interaction.guild_id)
        if len(panels) >= limits["max_panels"]:
            upsell = "" if limits["premium"] else " Upgrade to Premium for more panels."
            await interaction.response.send_message(
                f"⚠️ This server's plan allows up to {limits['max_panels']} application panel(s).{upsell}",
                ephemeral=True,
            )
            return
        slug = make_slug(name)
        base_slug, counter = slug, 2
        while slug in panels:
            slug = f"{base_slug}-{counter}"
            counter += 1
        panels[slug] = default_application_config(name)
        await store.set_path(str(interaction.guild_id), "panels", panels)
        await interaction.response.send_message(
            f"✅ Created application panel **{name}**. Use `/application builder` and select it to configure & publish it.",
            ephemeral=True,
        )

    @app_group.command(name="builder", description="Open the live-preview builder for an application panel")
    @app_commands.describe(panel="Which panel to configure")
    @app_commands.autocomplete(panel=panel_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def builder_cmd(self, interaction: discord.Interaction, panel: str):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        if panel not in panels:
            await interaction.response.send_message("⚠️ Panel not found. Check `/application list`.", ephemeral=True)
            return
        limits = await get_limits(interaction.guild_id)
        view = ApplicationBuilderView(
            store, interaction.guild, panel, panels[panel], interaction.user.id,
            max_questions=limits["max_questions"], is_premium=limits["premium"],
        )
        await interaction.response.send_message(
            content=view.header_text(), embed=view.render_embed(), view=view, ephemeral=True
        )
        view.message = await interaction.original_response()

    @app_group.command(name="list", description="List all application panels in this server")
    async def list_panels(self, interaction: discord.Interaction):
        panels = await store.get_path(str(interaction.guild_id), "panels", default={})
        if not panels:
            await interaction.response.send_message("No application panels yet. Use `/application new` to create one.", ephemeral=True)
            return
        lines = []
        for slug, cfg in panels.items():
            status = "✅ Published" if cfg.get("message_id") else "⏳ Draft"
            lines.append(f"• **{cfg.get('name', slug)}** `({slug})` — {status}")
        await interaction.response.send_message("**📋 Application Panels**\n" + "\n".join(lines), ephemeral=True)

    @app_group.command(name="delete", description="Delete an application panel")
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
            f"🗑️ Deleted application panel **{name}**. If it was already published, its Apply button will stop working.",
            ephemeral=True,
        )

    # ---------------- PREFIX COMMANDS ----------------
    @commands.group(name="application", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def app_prefix(self, ctx: commands.Context):
        await ctx.send(
            "Usage:\n"
            f"`{ctx.prefix}application new <name>`\n"
            f"`{ctx.prefix}application builder <slug>`\n"
            f"`{ctx.prefix}application list`\n"
            f"`{ctx.prefix}application delete <slug>`"
        )

    @app_prefix.command(name="new")
    @commands.has_permissions(manage_guild=True)
    async def app_prefix_new(self, ctx: commands.Context, *, name: str):
        panels = await store.get_path(str(ctx.guild.id), "panels", default={})
        limits = await get_limits(ctx.guild.id)
        if len(panels) >= limits["max_panels"]:
            upsell = "" if limits["premium"] else " Upgrade to Premium for more panels."
            await ctx.send(f"⚠️ This server's plan allows up to {limits['max_panels']} application panel(s).{upsell}")
            return
        slug = make_slug(name)
        base_slug, counter = slug, 2
        while slug in panels:
            slug = f"{base_slug}-{counter}"
            counter += 1
        panels[slug] = default_application_config(name)
        await store.set_path(str(ctx.guild.id), "panels", panels)
        await ctx.send(f"✅ Created application panel **{name}** (`{slug}`). Use `{ctx.prefix}application builder {slug}` to configure it.")

    @app_prefix.command(name="builder")
    @commands.has_permissions(manage_guild=True)
    async def app_prefix_builder(self, ctx: commands.Context, slug: str):
        panels = await store.get_path(str(ctx.guild.id), "panels", default={})
        if slug not in panels:
            await ctx.send(f"⚠️ Panel not found. Check `{ctx.prefix}application list`.")
            return
        limits = await get_limits(ctx.guild.id)
        view = ApplicationBuilderView(
            store, ctx.guild, slug, panels[slug], ctx.author.id,
            max_questions=limits["max_questions"], is_premium=limits["premium"],
        )
        message = await ctx.send(content=view.header_text(), embed=view.render_embed(), view=view)
        view.message = message

    @app_prefix.command(name="list")
    async def app_prefix_list(self, ctx: commands.Context):
        panels = await store.get_path(str(ctx.guild.id), "panels", default={})
        if not panels:
            await ctx.send("No application panels yet.")
            return
        lines = []
        for slug, cfg in panels.items():
            status = "✅ Published" if cfg.get("message_id") else "⏳ Draft"
            lines.append(f"• **{cfg.get('name', slug)}** `({slug})` — {status}")
        await ctx.send("**📋 Application Panels**\n" + "\n".join(lines))

    @app_prefix.command(name="delete")
    @commands.has_permissions(manage_guild=True)
    async def app_prefix_delete(self, ctx: commands.Context, slug: str):
        panels = await store.get_path(str(ctx.guild.id), "panels", default={})
        if slug not in panels:
            await ctx.send("⚠️ Panel not found.")
            return
        name = panels.pop(slug).get("name", slug)
        await store.set_path(str(ctx.guild.id), "panels", panels)
        await ctx.send(f"🗑️ Deleted application panel **{name}**.")

    # ---------------- RAW COMPONENT ROUTING (survives restarts) ----------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if custom_id.startswith("napp:apply:"):
            await self._handle_apply(interaction, custom_id)
        elif custom_id.startswith("napp:decision:"):
            await self._handle_decision(interaction, custom_id)
        elif custom_id.startswith("napp:history:"):
            await self._handle_history(interaction, custom_id)
        elif custom_id.startswith("napp:ticket:"):
            await self._handle_ticket(interaction, custom_id)

    async def _handle_apply(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, panel_id = custom_id.split(":")
        panels = await store.get_path(guild_id, "panels", default={})
        config = panels.get(panel_id)
        if not config:
            await interaction.response.send_message("⚠️ This application panel is no longer available.", ephemeral=True)
            return
        questions = config.get("questions", [])
        if not questions:
            await interaction.response.send_message("⚠️ This panel has no questions configured.", ephemeral=True)
            return

        if interaction.user.id in self.active_applications:
            await interaction.response.send_message(
                "⚠️ You already have an application in progress. Check your DMs!", ephemeral=True
            )
            return

        try:
            dm_channel = await interaction.user.create_dm()
            await dm_channel.send(
                f"📋 **{config.get('title', 'Application')}**\n"
                f"{config.get('description', '')}\n\n"
                f"I'll ask you {len(questions)} question(s) one at a time — just reply here in DMs.\n"
                f"Type `cancel` anytime to stop."
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I couldn't DM you. Please enable **Allow direct messages from server members** "
                "in your Privacy Settings for this server, then click Apply again.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message("📬 Check your DMs — I've sent you the application form!", ephemeral=True)

        guild = interaction.guild
        user = interaction.user
        self.active_applications.add(user.id)
        try:
            answers = []
            for i, question in enumerate(questions, start=1):
                await dm_channel.send(f"**Question {i}/{len(questions)}:** {question['label']}")

                def check(message: discord.Message, _channel_id=dm_channel.id, _user_id=user.id):
                    return message.author.id == _user_id and message.channel.id == _channel_id

                try:
                    reply = await self.bot.wait_for("message", check=check, timeout=ANSWER_TIMEOUT)
                except asyncio.TimeoutError:
                    await dm_channel.send("⌛ You took too long to respond. Click Apply again to restart the form.")
                    return

                if reply.content.strip().lower() == "cancel":
                    await dm_channel.send("❌ Application cancelled.")
                    return

                answers.append((question["label"], reply.content))

            await dm_channel.send("✅ Thanks! Your application has been submitted for review.")
            await self._send_branding_embed(dm_channel)
            await self.finalize_submission(guild, user, guild_id, panel_id, config, answers)
        finally:
            self.active_applications.discard(user.id)

    async def _send_branding_embed(self, dm_channel: discord.DMChannel):
        """Sent right after a DM application is completed — shows the bot's
        own name/icon/banner with Invite & Support Server buttons."""
        bot_user = self.bot.user
        embed = discord.Embed(
            title=bot_user.name,
            description=(
                "**Nocturne Manager** is an all-in-one Discord bot built for growing communities — from slick "
                "join/leave announcements to a full staff application system with a live-preview builder, "
                "just like the one you used above.\n\n"
                "✅ Custom join/leave embeds with your own branding\n"
                "✅ Multiple application panels with custom questions\n"
                "✅ Built-in Accept/Deny review workflow\n\n"
                "Enjoyed the experience? Bring **Nocturne Manager** to your own server using the links below!"
            ),
            color=discord.Color(parse_color(None)),
        )
        embed.set_thumbnail(url=bot_user.display_avatar.url)
        if BOT_BANNER_URL:
            embed.set_image(url=BOT_BANNER_URL)
        embed.set_footer(text="Nocturne Manager • Application System")

        view = discord.ui.View(timeout=None)
        if BOT_INVITE_URL:
            view.add_item(discord.ui.Button(label="Invite Bot", style=discord.ButtonStyle.link, url=BOT_INVITE_URL))
        if SUPPORT_SERVER_URL:
            view.add_item(discord.ui.Button(label="Join Support Server", style=discord.ButtonStyle.link, url=SUPPORT_SERVER_URL))

        try:
            if view.children:
                await dm_channel.send(embed=embed, view=view)
            else:
                await dm_channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def finalize_submission(self, guild: discord.Guild, user: discord.abc.User, guild_id, panel_id: str, config: dict, answers: list):
        panels = await store.get_path(str(guild_id), "panels", default={})
        fresh_config = panels.get(panel_id, config)
        log_channel_id = fresh_config.get("log_channel_id")
        channel = guild.get_channel(log_channel_id) if log_channel_id else None
        if not channel:
            try:
                await user.send(
                    "⚠️ Your application couldn't be delivered because this panel's log channel is no longer "
                    "configured. Please contact a server admin."
                )
            except discord.Forbidden:
                pass
            return

        embed = discord.Embed(
            title=f"📥 New Application — {fresh_config.get('title', 'Application')}",
            description=f"Applicant: {user.mention} (`{user.id}`)",
            color=discord.Color(parse_color(fresh_config.get("color"))),
            timestamp=datetime.now(timezone.utc),
        )
        for label, value in answers[:25]:
            embed.add_field(name=label[:256], value=(value or "-")[:1024], inline=False)
        embed.set_footer(text="Nocturne Manager • Application System")
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)

        # Send first WITHOUT the view, since the buttons need this message's
        # own ID baked into their custom_id — then attach the view right after.
        message = await channel.send(embed=embed)
        decision_view = build_decision_view(guild_id, panel_id, user.id, message.id, jump_url=message.jump_url)
        await message.edit(view=decision_view)

        records = await history_store.get_path(str(guild_id), str(user.id), default=[])
        records.append({
            "panel_id": panel_id,
            "panel_title": fresh_config.get("title", "Application"),
            "status": "pending",
            "reviewer_id": None,
            "reason": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_id": message.id,
            "channel_id": channel.id,
        })
        await history_store.set_path(str(guild_id), str(user.id), records)

    async def _handle_decision(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, panel_id, applicant_id, action, message_id = custom_id.split(":")

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You don't have permission to review applications.", ephemeral=True)
            return

        if action in ("accept_reason", "deny_reason"):
            base_action = "accept" if action == "accept_reason" else "deny"
            await interaction.response.send_modal(ReasonModal(guild_id, panel_id, applicant_id, message_id, base_action))
            return

        await self.apply_decision(interaction, guild_id, panel_id, applicant_id, message_id, action)

    async def apply_decision(self, interaction: discord.Interaction, guild_id, panel_id: str, applicant_id, message_id, action: str, reason: str = None):
        """Shared by the plain Accept/Deny buttons AND the Accept/Deny-with-reason
        modal submit. `interaction.message` is only populated for a direct
        button click — for a modal submit we have to fetch the message ourselves."""
        accepted = action == "accept"

        panels = await store.get_path(str(guild_id), "panels", default={})
        config = panels.get(panel_id, {})
        panel_title = config.get("title", "Application")

        source_message = interaction.message
        if source_message is None:
            try:
                source_message = await interaction.channel.fetch_message(int(message_id))
            except discord.HTTPException:
                source_message = None

        embed = source_message.embeds[0] if source_message and source_message.embeds else discord.Embed()
        embed.color = discord.Color.green() if accepted else discord.Color.red()
        status_line = f"{'✅ Accepted' if accepted else '❌ Denied'} by {interaction.user.mention}"
        if reason:
            status_line += f"\n**Reason:** {reason}"
        embed.add_field(name="Status", value=status_line, inline=False)

        jump_url = source_message.jump_url if source_message else None
        disabled_view = build_decision_view(guild_id, panel_id, int(applicant_id), int(message_id), jump_url=jump_url, decided=True)

        if interaction.message is not None:
            # Came straight from the button — this interaction IS the message.
            await interaction.response.edit_message(embed=embed, view=disabled_view)
        else:
            # Came from the reason modal — need to defer + edit the fetched message separately.
            await interaction.response.defer(ephemeral=True)
            if source_message is not None:
                await source_message.edit(embed=embed, view=disabled_view)
            await interaction.followup.send("✅ Decision recorded.", ephemeral=True)

        await self._update_submission_status(
            guild_id, applicant_id, message_id,
            "accepted" if accepted else "denied", interaction.user.id, reason,
        )

        try:
            applicant = interaction.guild.get_member(int(applicant_id)) or await self.bot.fetch_user(int(applicant_id))
            result_text = "accepted ✅" if accepted else "denied ❌"
            dm_text = f"Your application for **{panel_title}** in **{interaction.guild.name}** has been {result_text}."
            if reason:
                dm_text += f"\n**Reason:** {reason}"
            await applicant.send(dm_text)
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass

    async def _update_submission_status(self, guild_id, applicant_id, message_id, status: str, reviewer_id: int, reason: str = None):
        records = await history_store.get_path(str(guild_id), str(applicant_id), default=[])
        for rec in records:
            if str(rec.get("message_id")) == str(message_id):
                rec["status"] = status
                rec["reviewer_id"] = reviewer_id
                rec["reason"] = reason
                break
        await history_store.set_path(str(guild_id), str(applicant_id), records)

    async def _handle_history(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, applicant_id = custom_id.split(":")

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You don't have permission to view application history.", ephemeral=True)
            return

        records = await history_store.get_path(guild_id, applicant_id, default=[])
        if not records:
            await interaction.response.send_message("No application history found for this user.", ephemeral=True)
            return

        status_icons = {"pending": "⏳", "accepted": "✅", "denied": "❌"}
        lines = []
        for rec in records[-10:]:
            icon = status_icons.get(rec.get("status"), "❔")
            date_str = (rec.get("timestamp") or "")[:10]
            line = f"{icon} **{rec.get('panel_title', 'Application')}** — {rec.get('status', 'unknown')} ({date_str})"
            if rec.get("reason"):
                line += f"\n   ↳ *{rec['reason']}*"
            lines.append(line)

        embed = discord.Embed(
            title="📜 Application History",
            description="\n".join(lines),
            color=discord.Color(0x8B0000),
        )
        embed.set_footer(text=f"Showing last {len(lines)} submission(s) in this server")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_ticket(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, applicant_id = custom_id.split(":")

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You don't have permission to open tickets.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        applicant = guild.get_member(int(applicant_id))
        if not applicant:
            await interaction.followup.send("⚠️ That user is no longer in this server.", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            applicant: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel_name = f"ticket-{applicant.name}"[:90].lower().replace(" ", "-")
        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"Application ticket opened by {interaction.user} for {applicant}",
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create channels in this server.", ephemeral=True)
            return

        await ticket_channel.send(f"{applicant.mention} {interaction.user.mention}\nThis ticket was opened to discuss your application.")
        await interaction.followup.send(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ApplicationSystem(bot))
