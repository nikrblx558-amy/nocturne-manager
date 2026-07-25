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

STATUS_META = {
    "online": {"color": 0x57F287, "default_msg": "Semua sistem berjalan normal.", "label": "ONLINE"},
    "maintenance": {"color": 0xFEE75C, "default_msg": "Bot sedang dalam perbaikan, mohon tunggu sebentar.", "label": "MAINTENANCE"},
    "update": {"color": 0x5865F2, "default_msg": "Bot sedang menerima pembaruan fitur.", "label": "UPDATE"},
    "offline": {"color": 0xED4245, "default_msg": "Bot sedang tidak aktif untuk sementara waktu.", "label": "OFFLINE"},
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
#       "joycannot": {"name": "JoyCannot", "icon": "https://..."},
#       "joy-universe": {"name": "JOY UNIVERSE", "icon": "https://..."}
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


class StatusPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    status_group = app_commands.Group(
        name="status",
        description="Notifikasi status untuk bot-bot kamu (online/maintenance/update/offline)",
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
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        config["channel_id"] = channel.id
        await store.set_path(str(interaction.guild_id), config)
        await interaction.response.send_message(f"✅ Channel status notifikasi diset ke {channel.mention}.", ephemeral=True)

    # ---------------------------------------------------------------
    # MANAGE BOT LIST
    # ---------------------------------------------------------------
    @status_group.command(name="addbot", description="Daftarkan bot baru untuk dipantau statusnya")
    @app_commands.describe(name="Nama bot (contoh: JoyCannot, JOY UNIVERSE)", icon="URL avatar/icon bot (opsional)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def addbot(self, interaction: discord.Interaction, name: str, icon: str = None):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.setdefault("bots", {})

        slug = make_slug(name)
        base_slug = slug
        counter = 2
        while slug in bots:
            slug = f"{base_slug}-{counter}"
            counter += 1

        bots[slug] = {"name": name, "icon": icon}
        await store.set_path(str(interaction.guild_id), config)
        await interaction.response.send_message(
            f"✅ Bot **{name}** berhasil didaftarkan. Sekarang bisa dipilih di `/status set` dan `/status preview`.",
            ephemeral=True,
        )

    @status_group.command(name="editbot", description="Edit nama/icon bot yang sudah terdaftar")
    @app_commands.describe(bot="Pilih bot", name="Nama baru (opsional)", icon="URL icon baru (opsional)")
    @app_commands.autocomplete(bot=bot_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def editbot(self, interaction: discord.Interaction, bot: str, name: str = None, icon: str = None):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        if bot not in bots:
            await interaction.response.send_message("⚠️ Bot tidak ditemukan. Cek `/status listbots`.", ephemeral=True)
            return
        if name:
            bots[bot]["name"] = name
        if icon:
            bots[bot]["icon"] = icon
        await store.set_path(str(interaction.guild_id), config)
        await interaction.response.send_message(f"✅ Data bot **{bots[bot]['name']}** berhasil diupdate.", ephemeral=True)

    @status_group.command(name="removebot", description="Hapus bot dari daftar pantauan status")
    @app_commands.describe(bot="Pilih bot yang mau dihapus")
    @app_commands.autocomplete(bot=bot_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
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
    @app_commands.checks.has_permissions(manage_guild=True)
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
    async def preview(self, interaction: discord.Interaction, bot: str, status: app_commands.Choice[str], message: str = None):
        config = await store.get_path(str(interaction.guild_id), default=DEFAULT_STATUS_CONFIG)
        bots = config.get("bots", {})
        if bot not in bots:
            await interaction.response.send_message("⚠️ Bot tidak ditemukan. Cek `/status listbots`.", ephemeral=True)
            return
        embed = self._build_embed(bots[bot], status.value, message)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _build_embed(self, bot_data: dict, status_key: str, custom_message: str = None) -> discord.Embed:
        emojis = load_emojis()
        meta = STATUS_META[status_key]
        emoji = emojis.get(f"status_{status_key}", "•")
        separator_char = emojis.get("separator", "▬")
        separator_line = separator_char * 10

        embed = discord.Embed(
            title=f"{emoji}  STATUS: {meta['label']}",
            description=custom_message or meta["default_msg"],
            color=meta["color"],
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
