"""
Panel Builder interaktif untuk embed Join/Leave.
Konsep: 1 message berisi preview embed (berubah live) + tombol-tombol setting
di bawahnya, mirip contoh ticket panel builder.
"""
import copy
import discord

from utils.embed_builder import build_joinleave_embed
from utils.variables import VARIABLE_HELP

DEFAULT_JOIN = {
    "enabled": False,
    "channel_id": None,
    "content": "👋 Selamat datang {user} di **{server}**!",
    "title": "👋 Selamat Datang!",
    "description": "Halo {user}, selamat datang di **{server}**!",
    "thumbnail": "{user_avatar}",
    "banner": None,
    "color": "#8B0000",
    "footer": "",
    "blocks": [
        {"type": "field", "name": "Member Ke-", "value": "{member_count}", "inline": True}
    ],
    "row_links": [],
}

DEFAULT_LEAVE = {
    "enabled": False,
    "channel_id": None,
    "content": "",
    "title": "👋 Sampai Jumpa",
    "description": "**{user_name}** telah meninggalkan **{server}**.",
    "thumbnail": "{user_avatar}",
    "banner": None,
    "color": "#8B0000",
    "footer": "",
    "blocks": [
        {"type": "field", "name": "Sisa Member", "value": "{member_count}", "inline": True}
    ],
    "row_links": [],
}


# ---------------------------------------------------------------------------
# MODALS
# ---------------------------------------------------------------------------

class TitleModal(discord.ui.Modal, title="Set Title"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.title_input = discord.ui.TextInput(
            label="Judul Embed",
            default=(view.config.get("title") or "")[:256],
            max_length=256,
            required=False,
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["title"] = self.title_input.value
        await self.view_ref.save_and_refresh(interaction)


class DescriptionModal(discord.ui.Modal, title="Set Description"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.desc_input = discord.ui.TextInput(
            label="Deskripsi Embed",
            style=discord.TextStyle.paragraph,
            default=view.config.get("description") or "",
            max_length=4000,
            required=False,
        )
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["description"] = self.desc_input.value
        await self.view_ref.save_and_refresh(interaction)


class ThumbnailModal(discord.ui.Modal, title="Set Thumbnail"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.url_input = discord.ui.TextInput(
            label="URL gambar (atau ketik {user_avatar})",
            default=view.config.get("thumbnail") or "",
            max_length=300,
            required=False,
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["thumbnail"] = self.url_input.value or None
        await self.view_ref.save_and_refresh(interaction)


class BannerModal(discord.ui.Modal, title="Set Banner"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.url_input = discord.ui.TextInput(
            label="URL gambar banner",
            default=view.config.get("banner") or "",
            max_length=300,
            required=False,
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["banner"] = self.url_input.value or None
        await self.view_ref.save_and_refresh(interaction)


class ColorModal(discord.ui.Modal, title="Set Warna Embed"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.color_input = discord.ui.TextInput(
            label="Kode warna hex (contoh: #FFD54A)",
            default=view.config.get("color", "#8B0000"),
            max_length=7,
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.color_input.value.strip()
        if not val.startswith("#"):
            val = "#" + val
        self.view_ref.config["color"] = val
        await self.view_ref.save_and_refresh(interaction)


class FooterModal(discord.ui.Modal, title="Set Footer"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.footer_input = discord.ui.TextInput(
            label="Teks Footer (kosongkan untuk default)",
            default=view.config.get("footer") or "",
            max_length=200,
            required=False,
        )
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["footer"] = self.footer_input.value
        await self.view_ref.save_and_refresh(interaction)


class ContentModal(discord.ui.Modal, title="Set Teks Sambutan (di luar embed)"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.content_input = discord.ui.TextInput(
            label="Teks di atas embed (bisa mention {user})",
            style=discord.TextStyle.paragraph,
            default=view.config.get("content") or "",
            max_length=1000,
            required=False,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.config["content"] = self.content_input.value
        await self.view_ref.save_and_refresh(interaction)


class FieldModal(discord.ui.Modal, title="Tambah Field"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.name_input = discord.ui.TextInput(label="Nama Field", max_length=256)
        self.value_input = discord.ui.TextInput(
            label="Isi Field", style=discord.TextStyle.paragraph, max_length=1024
        )
        self.inline_input = discord.ui.TextInput(label="Inline? (yes/no)", default="no", max_length=3)
        self.add_item(self.name_input)
        self.add_item(self.value_input)
        self.add_item(self.inline_input)

    async def on_submit(self, interaction: discord.Interaction):
        block = {
            "type": "field",
            "name": self.name_input.value or "\u200b",
            "value": self.value_input.value or "\u200b",
            "inline": self.inline_input.value.strip().lower() in ("yes", "y", "true"),
        }
        self.view_ref.config.setdefault("blocks", []).append(block)
        await self.view_ref.save_and_refresh(interaction)


class IconFieldModal(discord.ui.Modal, title="Tambah Icon Field"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.icon_input = discord.ui.TextInput(label="Emoji (contoh: 🎉 atau <:nama:id>)", max_length=100)
        self.name_input = discord.ui.TextInput(label="Nama Field", max_length=256)
        self.value_input = discord.ui.TextInput(
            label="Isi Field", style=discord.TextStyle.paragraph, max_length=1024
        )
        self.inline_input = discord.ui.TextInput(label="Inline? (yes/no)", default="no", max_length=3)
        self.add_item(self.icon_input)
        self.add_item(self.name_input)
        self.add_item(self.value_input)
        self.add_item(self.inline_input)

    async def on_submit(self, interaction: discord.Interaction):
        block = {
            "type": "icon_field",
            "icon": self.icon_input.value,
            "name": self.name_input.value or "\u200b",
            "value": self.value_input.value or "\u200b",
            "inline": self.inline_input.value.strip().lower() in ("yes", "y", "true"),
        }
        self.view_ref.config.setdefault("blocks", []).append(block)
        await self.view_ref.save_and_refresh(interaction)


class RowLinkModal(discord.ui.Modal, title="Tambah Tombol Link"):
    def __init__(self, view: "JoinLeaveBuilderView"):
        super().__init__()
        self.view_ref = view
        self.label_input = discord.ui.TextInput(label="Label Tombol", max_length=80)
        self.url_input = discord.ui.TextInput(label="URL (harus https://...)", max_length=300)
        self.add_item(self.label_input)
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        links = self.view_ref.config.setdefault("row_links", [])
        if len(links) >= 5:
            await interaction.response.send_message("⚠️ Maksimal 5 tombol link.", ephemeral=True)
            return
        if not self.url_input.value.startswith("http"):
            await interaction.response.send_message("⚠️ URL harus diawali http:// atau https://", ephemeral=True)
            return
        links.append({"label": self.label_input.value, "url": self.url_input.value})
        await self.view_ref.save_and_refresh(interaction)


# ---------------------------------------------------------------------------
# DYNAMIC SELECT COMPONENTS
# ---------------------------------------------------------------------------

class BlockRemoveSelect(discord.ui.Select):
    def __init__(self, view: "JoinLeaveBuilderView"):
        self.view_ref = view
        blocks = view.config.get("blocks", [])
        options = []
        if not blocks:
            options.append(discord.SelectOption(label="Belum ada field / separator", value="none"))
        else:
            for i, b in enumerate(blocks):
                if b["type"] == "separator":
                    label = f"#{i + 1} — Separator"
                elif b["type"] == "icon_field":
                    label = f"#{i + 1} — {b.get('icon', '')} {b.get('name', '')}"[:100]
                else:
                    label = f"#{i + 1} — {b.get('name', '(tanpa nama)')}"[:100]
                options.append(discord.SelectOption(label=label[:100], value=str(i)))
        super().__init__(
            placeholder="🗑️ Hapus field / separator...",
            options=options[:25],
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "none":
            await interaction.response.defer()
            return
        idx = int(val)
        blocks = self.view_ref.config.get("blocks", [])
        if 0 <= idx < len(blocks):
            blocks.pop(idx)
        await self.view_ref.save_and_refresh(interaction)


class ChannelPickSelect(discord.ui.ChannelSelect):
    def __init__(self, view: "JoinLeaveBuilderView"):
        self.view_ref = view
        super().__init__(
            placeholder="📌 Set channel notifikasi...",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.config["channel_id"] = self.values[0].id
        await self.view_ref.save_and_refresh(interaction)


# ---------------------------------------------------------------------------
# MAIN VIEW
# ---------------------------------------------------------------------------

class JoinLeaveBuilderView(discord.ui.View):
    def __init__(self, store, guild: discord.Guild, jl_type: str, config: dict, author_id: int):
        super().__init__(timeout=600)
        self.store = store
        self.guild = guild
        self.jl_type = jl_type
        self.config = config
        self.author_id = author_id
        self.message: discord.Message | None = None
        self._build_dynamic_items()

    def _build_dynamic_items(self):
        for item in list(self.children):
            if isinstance(item, (BlockRemoveSelect, ChannelPickSelect)):
                self.remove_item(item)
        self.add_item(BlockRemoveSelect(self))
        self.add_item(ChannelPickSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("⚠️ Panel builder ini bukan punya kamu.", ephemeral=True)
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
        return build_joinleave_embed(self.config, member=None, guild=self.guild)

    def header_text(self) -> str:
        status = "✅ Aktif" if self.config.get("enabled") else "⛔ Nonaktif"
        channel = f"<#{self.config['channel_id']}>" if self.config.get("channel_id") else "*belum diset*"
        links = len(self.config.get("row_links", []))
        content_preview = self.config.get("content") or "*(kosong)*"
        return (
            f"### 🛠️ PANEL BUILDER — NOTIFIKASI {self.jl_type.upper()}\n"
            f"Status: **{status}**  •  Channel: {channel}  •  Tombol link: {links}/5\n"
            f"Teks sambutan (di luar embed): {content_preview}\n"
            f"-# Preview di bawah pakai data contoh — variabel otomatis diganti saat member join/leave beneran."
        )

    async def save_and_refresh(self, interaction: discord.Interaction):
        await self.store.set_path(str(self.guild.id), self.jl_type, self.config)
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
        await interaction.response.send_modal(TitleModal(self))

    @discord.ui.button(label="Description", emoji="📄", style=discord.ButtonStyle.secondary, row=0)
    async def btn_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DescriptionModal(self))

    @discord.ui.button(label="Thumbnail", emoji="🖼️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_thumbnail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ThumbnailModal(self))

    @discord.ui.button(label="Banner", emoji="🏳️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BannerModal(self))

    @discord.ui.button(label="Color", emoji="🎨", style=discord.ButtonStyle.secondary, row=0)
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self))

    # ---- Row 1 ----
    @discord.ui.button(label="Field", emoji="➕", style=discord.ButtonStyle.secondary, row=1)
    async def btn_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FieldModal(self))

    @discord.ui.button(label="Icon Field", emoji="🔸", style=discord.ButtonStyle.secondary, row=1)
    async def btn_icon_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IconFieldModal(self))

    @discord.ui.button(label="Separator", emoji="➖", style=discord.ButtonStyle.secondary, row=1)
    async def btn_separator(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config.setdefault("blocks", []).append({"type": "separator"})
        await self.save_and_refresh(interaction)

    @discord.ui.button(label="Row Link", emoji="🔗", style=discord.ButtonStyle.secondary, row=1)
    async def btn_row_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RowLinkModal(self))

    @discord.ui.button(label="Variable", emoji="🧩", style=discord.ButtonStyle.secondary, row=1)
    async def btn_variable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(VARIABLE_HELP, ephemeral=True)

    # ---- Row 4 ----
    @discord.ui.button(label="Sambutan", emoji="💬", style=discord.ButtonStyle.secondary, row=4)
    async def btn_content(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ContentModal(self))

    @discord.ui.button(label="Footer", emoji="🔻", style=discord.ButtonStyle.secondary, row=4)
    async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FooterModal(self))

    @discord.ui.button(label="Enable/Disable", emoji="🔌", style=discord.ButtonStyle.primary, row=4)
    async def btn_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["enabled"] = not self.config.get("enabled", False)
        await self.save_and_refresh(interaction)

    @discord.ui.button(label="Reset", emoji="♻️", style=discord.ButtonStyle.danger, row=4)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        default = DEFAULT_JOIN if self.jl_type == "join" else DEFAULT_LEAVE
        self.config = copy.deepcopy(default)
        await self.save_and_refresh(interaction)

    @discord.ui.button(label="Done", emoji="✅", style=discord.ButtonStyle.success, row=4)
    async def btn_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        content = self.header_text() + "\n\n**Panel ditutup. Jalankan `/joinleave builder` lagi kalau mau edit.**"
        await interaction.response.edit_message(content=content, view=self)
        self.stop()
