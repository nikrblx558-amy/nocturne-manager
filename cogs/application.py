"""
Application System — a full replacement for the old Status Bot feature.

Lets staff build application panels (like a job application / staff
recruitment form) with a live-preview builder, publish them with a persistent
"Apply" button, collect answers via a modal, and review submissions with
Accept/Deny buttons in a log channel.
"""
import re
import copy
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import JSONStore
from utils.embed_builder import parse_color

store = JSONStore("applications.json")

CHUNK_SIZE = 5          # Discord modals allow a maximum of 5 components per modal
MAX_QUESTIONS = 25      # Discord embeds allow a maximum of 25 fields, used to display Q&A


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


def build_decision_view(guild_id: int, panel_id: str, applicant_id: int, disabled: bool = False) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label="Accept",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"napp:decision:{guild_id}:{panel_id}:{applicant_id}:accept",
            disabled=disabled,
        )
    )
    view.add_item(
        discord.ui.Button(
            label="Deny",
            emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id=f"napp:decision:{guild_id}:{panel_id}:{applicant_id}:deny",
            disabled=disabled,
        )
    )
    return view


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
        if len(questions) >= MAX_QUESTIONS:
            await interaction.response.send_message(
                f"⚠️ Maximum of {MAX_QUESTIONS} questions (Discord embed field limit).", ephemeral=True
            )
            return
        style = "paragraph" if self.style_input.value.strip().lower().startswith("p") else "short"
        questions.append({"label": self.label_input.value, "style": style})
        await self.view_ref.save_and_refresh(interaction)


class ApplyModal(discord.ui.Modal):
    """One 'page' of the application form. If there are more than 5
    questions, additional pages are chained automatically after each submit."""

    def __init__(self, guild_id: int, panel_id: str, config: dict, questions_chunk: list, chunk_index: int, total_chunks: int):
        base_title = config.get("title") or "Application"
        suffix = f" ({chunk_index + 1}/{total_chunks})" if total_chunks > 1 else ""
        super().__init__(title=(base_title[:45 - len(suffix)] + suffix)[:45])
        self.guild_id = guild_id
        self.panel_id = panel_id
        self.config = config
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks
        self.question_inputs = []
        for q in questions_chunk:
            style = discord.TextStyle.paragraph if q.get("style") == "paragraph" else discord.TextStyle.short
            text_input = discord.ui.TextInput(label=q["label"][:45], style=style, required=True, max_length=1000)
            self.question_inputs.append((q["label"], text_input))
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        cog: "ApplicationSystem" = interaction.client.get_cog("ApplicationSystem")
        await cog.handle_modal_chunk(
            interaction, self.guild_id, self.panel_id, self.config,
            self.question_inputs, self.chunk_index, self.total_chunks,
        )


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
    def __init__(self, store: JSONStore, guild: discord.Guild, panel_id: str, config: dict, author_id: int):
        super().__init__(timeout=600)
        self.store = store
        self.guild = guild
        self.panel_id = panel_id
        self.config = config
        self.author_id = author_id
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
        return (
            f"### 🛠️ APPLICATION PANEL BUILDER — {self.config.get('name', self.panel_id)}\n"
            f"Log channel: {log_channel}  •  Questions: {q_count}/{MAX_QUESTIONS}  •  Published in: {published}\n"
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
        # Short-lived state for multi-page application forms (>5 questions).
        # Keyed by (guild_id, panel_id, user_id). Only needed for the few
        # seconds between a user submitting one page and the next page
        # opening — not meant to survive a bot restart.
        self.pending_answers: dict = {}
        self.pending_chunks: dict = {}

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
        view = ApplicationBuilderView(store, interaction.guild, panel, panels[panel], interaction.user.id)
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
        view = ApplicationBuilderView(store, ctx.guild, slug, panels[slug], ctx.author.id)
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

        chunks = [questions[i:i + CHUNK_SIZE] for i in range(0, len(questions), CHUNK_SIZE)]
        key = (guild_id, panel_id, str(interaction.user.id))
        self.pending_answers[key] = []
        self.pending_chunks[key] = chunks

        await interaction.response.send_modal(
            ApplyModal(int(guild_id), panel_id, config, chunks[0], 0, len(chunks))
        )

    async def handle_modal_chunk(self, interaction: discord.Interaction, guild_id: int, panel_id: str, config: dict, question_inputs, chunk_index: int, total_chunks: int):
        key = (str(guild_id), panel_id, str(interaction.user.id))
        answers = self.pending_answers.setdefault(key, [])
        answers.extend([(label, ti.value) for label, ti in question_inputs])

        next_index = chunk_index + 1
        if next_index < total_chunks:
            chunks = self.pending_chunks.get(key, [])
            if next_index >= len(chunks):
                # Safety net: pending state got lost (e.g. bot restarted mid-form).
                await interaction.response.send_message(
                    "⚠️ Something went wrong continuing your application. Please click Apply again to restart the form.",
                    ephemeral=True,
                )
                self.pending_answers.pop(key, None)
                self.pending_chunks.pop(key, None)
                return
            await interaction.response.send_modal(
                ApplyModal(guild_id, panel_id, config, chunks[next_index], next_index, total_chunks)
            )
            return

        # Last page submitted — finalize and send to the log channel.
        final_answers = self.pending_answers.pop(key, answers)
        self.pending_chunks.pop(key, None)
        await self.finalize_submission(interaction, guild_id, panel_id, config, final_answers)

    async def finalize_submission(self, interaction: discord.Interaction, guild_id: int, panel_id: str, config: dict, answers: list):
        panels = await store.get_path(str(guild_id), "panels", default={})
        fresh_config = panels.get(panel_id, config)
        log_channel_id = fresh_config.get("log_channel_id")
        channel = interaction.guild.get_channel(log_channel_id) if log_channel_id else None
        if not channel:
            await interaction.response.send_message(
                "⚠️ This panel has no valid log channel configured. Please contact a server admin.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📥 New Application — {fresh_config.get('title', 'Application')}",
            description=f"Applicant: {interaction.user.mention} (`{interaction.user.id}`)",
            color=discord.Color(parse_color(fresh_config.get("color"))),
            timestamp=datetime.now(timezone.utc),
        )
        for label, value in answers[:25]:
            embed.add_field(name=label[:256], value=(value or "-")[:1024], inline=False)
        embed.set_footer(text="Nocturne Manager • Application System")
        if interaction.user.display_avatar:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

        decision_view = build_decision_view(guild_id, panel_id, interaction.user.id)
        await channel.send(embed=embed, view=decision_view)
        await interaction.response.send_message(
            "✅ Your application has been submitted! You'll be notified once it's reviewed.", ephemeral=True
        )

    async def _handle_decision(self, interaction: discord.Interaction, custom_id: str):
        _, _, guild_id, panel_id, applicant_id, action = custom_id.split(":")

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You don't have permission to review applications.", ephemeral=True)
            return

        panels = await store.get_path(guild_id, "panels", default={})
        config = panels.get(panel_id, {})
        panel_title = config.get("title", "Application")

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        accepted = action == "accept"
        embed.color = discord.Color.green() if accepted else discord.Color.red()
        embed.add_field(
            name="Status",
            value=f"{'✅ Accepted' if accepted else '❌ Denied'} by {interaction.user.mention}",
            inline=False,
        )

        disabled_view = build_decision_view(guild_id, panel_id, int(applicant_id), disabled=True)
        await interaction.response.edit_message(embed=embed, view=disabled_view)

        try:
            applicant = interaction.guild.get_member(int(applicant_id)) or await self.bot.fetch_user(int(applicant_id))
            result_text = "accepted ✅" if accepted else "denied ❌"
            await applicant.send(
                f"Your application for **{panel_title}** in **{interaction.guild.name}** has been {result_text}."
            )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ApplicationSystem(bot))
