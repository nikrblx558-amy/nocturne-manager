import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import JSONStore
from utils.embed_builder import build_joinleave_embed, build_row_link_view
from cogs.panel_builder import JoinLeaveBuilderView, DEFAULT_JOIN, DEFAULT_LEAVE

store = JSONStore("joinleave.json")

TYPE_CHOICES = [
    app_commands.Choice(name="Join", value="join"),
    app_commands.Choice(name="Leave", value="leave"),
]


class JoinLeave(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    jl_group = app_commands.Group(
        name="joinleave",
        description="Pengaturan notifikasi member join & leave",
    )

    @jl_group.command(name="builder", description="Buka panel builder embed join/leave (live preview)")
    @app_commands.describe(type="Pilih builder untuk Join atau Leave")
    @app_commands.choices(type=TYPE_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def builder(self, interaction: discord.Interaction, type: app_commands.Choice[str]):
        default = DEFAULT_JOIN if type.value == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(interaction.guild_id), type.value, default=default)

        view = JoinLeaveBuilderView(
            store=store,
            guild=interaction.guild,
            jl_type=type.value,
            config=config,
            author_id=interaction.user.id,
        )
        await interaction.response.send_message(
            content=view.header_text(),
            embed=view.render_embed(),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    @jl_group.command(name="toggle", description="Aktifkan/nonaktifkan notifikasi join/leave secara cepat")
    @app_commands.choices(type=TYPE_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle(self, interaction: discord.Interaction, type: app_commands.Choice[str], enabled: bool):
        default = DEFAULT_JOIN if type.value == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(interaction.guild_id), type.value, default=default)
        config["enabled"] = enabled
        await store.set_path(str(interaction.guild_id), type.value, config)
        status = "diaktifkan ✅" if enabled else "dinonaktifkan ⛔"
        await interaction.response.send_message(f"Notifikasi **{type.value}** berhasil {status}.", ephemeral=True)

    @jl_group.command(name="test", description="Kirim contoh embed join/leave ke channel yang sudah diset")
    @app_commands.choices(type=TYPE_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test(self, interaction: discord.Interaction, type: app_commands.Choice[str]):
        default = DEFAULT_JOIN if type.value == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(interaction.guild_id), type.value, default=default)
        if not config.get("channel_id"):
            await interaction.response.send_message("⚠️ Channel belum diset. Buka `/joinleave builder` dulu.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(config["channel_id"])
        if not channel:
            await interaction.response.send_message("⚠️ Channel tidak ditemukan lagi, cek ulang di builder.", ephemeral=True)
            return

        embed = build_joinleave_embed(config, member=interaction.user, guild=interaction.guild)
        link_view = build_row_link_view(config)
        if link_view:
            await channel.send(embed=embed, view=link_view)
        else:
            await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Test embed **{type.value}** dikirim ke {channel.mention}.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._send_notification(member, "join")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._send_notification(member, "leave")

    async def _send_notification(self, member: discord.Member, jl_type: str):
        default = DEFAULT_JOIN if jl_type == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(member.guild.id), jl_type, default=default)

        if not config.get("enabled") or not config.get("channel_id"):
            return

        channel = member.guild.get_channel(config["channel_id"])
        if not channel:
            return

        embed = build_joinleave_embed(config, member=member, guild=member.guild)
        link_view = build_row_link_view(config)

        try:
            if link_view:
                await channel.send(embed=embed, view=link_view)
            else:
                await channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinLeave(bot))
