import json
import os
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import JSONStore

store = JSONStore("status.json")

EMOJI_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "emojis.json")

DARK_RED = 0x8B0000

STATUS_META = {
    "online": {"default_msg": "Semua sistem berjalan normal.", "label": "ONLINE"},
    "maintenance": {"default_msg": "Bot sedang dalam perbaikan, mohon tunggu sebentar.", "label": "MAINTENANCE"},
    "update": {"default_msg": "Bot sedang menerima pembaruan fitur.", "label": "UPDATE"},
    "offline": {"default_msg": "Bot sedang tidak aktif untuk sementara waktu.", "label": "OFFLINE"},
}

STATUS_CHOICES = [
    app_commands.Choice(name="Online", value="online"),
    app_commands.Choice(name="Maintenance", value="maintenance"),
    app_commands.Choice(name="Update", value="update"),
    app_commands.Choice(name="Offline", value="offline"),
]

# Struktur config per guild:
# {
#   "channel_id": 123,
#   "bots": {
#       "joycannot": {"name": "JoyCannot", "icon": "https://...", "color": "#8B0000"},
#       "joy-universe": {"name": "JOY UNIVERSE", "icon": "https://...", "color": "#1ABC9C"}
#   }
# }
DEFAULT_STATUS_CONFIG = {
    "channel_id": None,
    "bots": {},
}


def load_emojis() -> dict:
    try:
        with open(EMOJI_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def make_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "bot"


def parse_color(text: str | None, default: int = DARK_RED) -> int:
    if not text:
        return default
    text = text.strip().lstrip("#")
    try:
        return int(text, 16)
    except ValueError:
        return default


def owner_only():
    """Semua command /status cuma bisa dipakai owner aplikasi bot (kamu),
    ditolak untuk siapapun selain owner, termasuk admin server."""

    async def predicate(interaction: discord.Interaction) -> bool:
        is_owner = await interaction.client.is_owner(interaction.user)
        if not is_owner:
            raise app_commands.CheckFailure("owner_only")
        return True

    return app_commands.check(predicate)


class StatusPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    status_group = app_commands.Group(
        name="status",
        description="[Owner only] Notifikasi status untuk bot-bot kamu",
    )

    async def bot_autocomplete(self, interaction: discord.Interaction, current: str):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        results = [
            app_commands.Choice(name=data["name"], value=slug)
            for slug, data in bots.items()
            if current.lower() in data["name"].lower()
        ]
        return results[:25]

    # ---------------------------------------------------------------
    # SETUP CHANNEL
    # ---------------------------------------------------------------
    @status_group.command(name="setup", description="Atur channel tujuan notifikasi status bot")
    @app_commands.describe(channel="Channel tempat semua notifikasi status bot dikirim")
    @owner_only()
    async def setup_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        config["channel_id"] = channel.id
        await store.set_path(str(interaction.guild_id), config)
        await interaction.response.send_message(f"✅ Channel status notifikasi diset ke {channel.mention}.", ephemeral=True)

    # ---------------------------------------------------------------
    # MANAGE BOT LIST
    # ---------------------------------------------------------------
    @status_group.command(name="addbot", description="Daftarkan bot baru untuk dipantau statusnya")
    @app_commands.describe(
        name="Nama bot (contoh: JoyCannot, JOY UNIVERSE)",
        icon="URL avatar/icon bot (opsional)",
        color="Kode warna hex embed, contoh #8B0000 (opsional, default dark red)",
    )
    @owner_only()
    async def addbot(self, interaction: discord.Interaction, name: str, icon: str = None, color: str = None):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.setdefault("bots", {})

        slug = make_slug(name)
        base_slug = slug
        counter = 2
        while slug in bots:
            slug = f"{base_slug}-{counter}"
            counter += 1

        bots[slug] = {"name": name, "icon": icon, "color": color}
        await store.set_path(str(interaction.guild_id), config)
        await interaction.response.send_message(
            f"✅ Bot **{name}** berhasil didaftarkan. Sekarang bisa dipilih di `/status set` dan `/status preview`.",
            ephemeral=True,
        )

    @status_group.command(name="editbot", description="Edit nama/icon/warna bot yang sudah terdaftar")
    @app_commands.describe(
        bot="Pilih bot", name="Nama baru (opsional)", icon="URL icon baru (opsional)",
        color="Kode warna hex baru, contoh #8B0000 (opsional)",
    )
    @app_commands.autocomplete(bot=bot_autocomplete)
    @owner_only()
    async def editbot(self, interaction: discord.Interaction, bot: str, name: str = None, icon: str = None, color: str = None):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        if bot not in bots:
            await interaction.response.send_message("⚠️ Bot tidak ditemukan. Cek `/status listbots`.", ephemeral=True)
            return
        if name:
            bots[bot]["name"] = name
        if icon:
            bots[bot]["icon"] = icon
        if color:
            bots[bot]["color"] = color
        await store.set_path(str(interaction.guild_id), config)
        await interaction.response.send_message(f"✅ Data bot **{bots[bot]['name']}** berhasil diupdate.", ephemeral=True)

    @status_group.command(name="removebot", description="Hapus bot dari daftar pantauan status")
    @app_commands.describe(bot="Pilih bot yang mau dihapus")
    @app_commands.autocomplete(bot=bot_autocomplete)
    @owner_only()
    async def removebot(self, interaction: discord.Interaction, bot: str):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        if bot not in bots:
            await interaction.response.send_message("⚠️ Bot tidak ditemukan. Cek `/status listbots`.", ephemeral=True)
            return
        name = bots.pop(bot)["name"]
        await store.set_path(str(interaction.guild_id), config)
        await interaction.response.send_message(f"🗑️ Bot **{name}** dihapus dari daftar pantauan.", ephemeral=True)

    @status_group.command(name="listbots", description="Lihat semua bot yang terdaftar di sistem status")
    @owner_only()
    async def listbots(self, interaction: discord.Interaction):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        if not bots:
            await interaction.response.send_message("Belum ada bot terdaftar. Pakai `/status addbot` dulu.", ephemeral=True)
            return
        lines = [f"• **{data['name']}**  `({slug})`" for slug, data in bots.items()]
        channel_txt = f"<#{config['channel_id']}>" if config.get("channel_id") else "*belum diset*"
        await interaction.response.send_message(
            f"**🤖 Daftar bot terpantau** (channel: {channel_txt})\n" + "\n".join(lines),
            ephemeral=True,
        )

    # ---------------------------------------------------------------
    # SEND / PREVIEW STATUS
    # ---------------------------------------------------------------
    @status_group.command(name="set", description="Kirim embed status salah satu bot ke channel yang sudah diset")
    @app_commands.describe(bot="Pilih bot", status="Pilih status", message="Pesan kustom (opsional)")
    @app_commands.choices(status=STATUS_CHOICES)
    @app_commands.autocomplete(bot=bot_autocomplete)
    @owner_only()
    async def set_status(self, interaction: discord.Interaction, bot: str, status: app_commands.Choice[str], message: str = None):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})

        if not config.get("channel_id"):
            await interaction.response.send_message("⚠️ Channel belum diset. Gunakan `/status setup` dulu.", ephemeral=True)
            return
        if bot not in bots:
            await interaction.response.send_message("⚠️ Bot tidak ditemukan. Cek `/status listbots` atau daftarkan dulu pakai `/status addbot`.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(config["channel_id"])
        if not channel:
            await interaction.response.send_message("⚠️ Channel tidak ditemukan, cek ulang `/status setup`.", ephemeral=True)
            return

        embed = self._build_embed(bots[bot], status.value, message)
        await channel.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Status **{bots[bot]['name']}** → **{status.name}** dikirim ke {channel.mention}.",
            ephemeral=True,
        )

    @status_group.command(name="preview", description="Lihat preview embed status bot tanpa mengirim ke channel")
    @app_commands.choices(status=STATUS_CHOICES)
    @app_commands.autocomplete(bot=bot_autocomplete)
    @owner_only()
    async def preview(self, interaction: discord.Interaction, bot: str, status: app_commands.Choice[str], message: str = None):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        if bot not in bots:
            await interaction.response.send_message("⚠️ Bot tidak ditemukan. Cek `/status listbots`.", ephemeral=True)
            return
        embed = self._build_embed(bots[bot], status.value, message)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =================================================================
    # PREFIX COMMANDS (n!status ...) — owner only
    # =================================================================
    @commands.group(name="status", invoke_without_command=True)
    @commands.is_owner()
    async def status_prefix(self, ctx: commands.Context):
        await ctx.send(
            "Pakai salah satu:\n"
            f"`{ctx.prefix}status setup <#channel>`\n"
            f"`{ctx.prefix}status addbot <nama> [icon] [color]`\n"
            f"`{ctx.prefix}status listbots`\n"
            f"`{ctx.prefix}status set <slug_bot> <online|maintenance|update|offline> [pesan]`"
        )

    @status_prefix.command(name="setup")
    @commands.is_owner()
    async def status_prefix_setup(self, ctx: commands.Context, channel: discord.TextChannel):
        config = await store.get_path(str(ctx.guild.id), default=DEFAULT_STATUS_CONFIG)
        config["channel_id"] = channel.id
        await store.set_path(str(ctx.guild.id), config)
        await ctx.send(f"✅ Channel status notifikasi diset ke {channel.mention}.")

    @status_prefix.command(name="addbot")
    @commands.is_owner()
    async def status_prefix_addbot(self, ctx: commands.Context, name: str, icon: str = None, color: str = None):
        config = await store.get_path(str(ctx.guild.id), default=DEFAULT_STATUS_CONFIG)
        bots = config.setdefault("bots", {})
        slug = make_slug(name)
        base_slug = slug
        counter = 2
        while slug in bots:
            slug = f"{base_slug}-{counter}"
            counter += 1
        bots[slug] = {"name": name, "icon": icon, "color": color}
        await store.set_path(str(ctx.guild.id), config)
        await ctx.send(f"✅ Bot **{name}** didaftarkan dengan slug `{slug}`.")

    @status_prefix.command(name="listbots")
    @commands.is_owner()
    async def status_prefix_listbots(self, ctx: commands.Context):
        config = await store.get_path(str(ctx.guild.id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        if not bots:
            await ctx.send("Belum ada bot terdaftar.")
            return
        lines = [f"• **{data['name']}**  `({slug})`" for slug, data in bots.items()]
        await ctx.send(f"**🤖 Daftar bot terpantau**\n" + "\n".join(lines))

    @status_prefix.command(name="set")
    @commands.is_owner()
    async def status_prefix_set(self, ctx: commands.Context, bot_slug: str, status_key: str, *, message: str = None):
        status_key = status_key.strip().lower()
        if status_key not in STATUS_META:
            await ctx.send("⚠️ Status harus salah satu: `online`, `maintenance`, `update`, `offline`.")
            return
        config = await store.get_path(str(ctx.guild.id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        if not config.get("channel_id"):
            await ctx.send(f"⚠️ Channel belum diset. Pakai `{ctx.prefix}status setup <#channel>` dulu.")
            return
        if bot_slug not in bots:
            await ctx.send("⚠️ Bot tidak ditemukan. Cek `{}status listbots`.".format(ctx.prefix))
            return
        channel = ctx.guild.get_channel(config["channel_id"])
        if not channel:
            await ctx.send("⚠️ Channel tidak ditemukan lagi, cek ulang setup.")
            return
        embed = self._build_embed(bots[bot_slug], status_key, message)
        await channel.send(embed=embed)
        await ctx.send(f"✅ Status **{bots[bot_slug]['name']}** → **{status_key}** dikirim ke {channel.mention}.")

    def _build_embed(self, bot_data: dict, status_key: str, custom_message: str = None) -> discord.Embed:
        emojis = load_emojis()
        meta = STATUS_META[status_key]
        emoji = emojis.get(f"status_{status_key}", "•")
        # Garis tipis (box-drawing), bukan blok tebal.
        separator_char = emojis.get("separator", "─")
        separator_line = separator_char * 20

        color = parse_color(bot_data.get("color"), default=DARK_RED)

        embed = discord.Embed(
            title=f"{emoji} STATUS: {meta['label']}",
            description=custom_message or meta["default_msg"],
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        bot_name = bot_data.get("name") or "Bot"
        bot_icon = bot_data.get("icon")
        if bot_icon:
            embed.set_author(name=bot_name, icon_url=bot_icon)
            embed.set_thumbnail(url=bot_icon)
        else:
            embed.set_author(name=bot_name)

        embed.add_field(name="\u200b", value=separator_line, inline=False)
        embed.set_footer(text="Nocturne Manager • Status System")
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(StatusPanel(bot))
