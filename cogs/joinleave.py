import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import JSONStore
from utils.embed_builder import build_joinleave_embed, build_row_link_view, resolve_content
from cogs.panel_builder import JoinLeaveBuilderView, DEFAULT_JOIN, DEFAULT_LEAVE

store = JSONStore("joinleave.json")

TYPE_CHOICES = [
    app_commands.Choice(name="Join", value="join"),
    app_commands.Choice(name="Leave", value="leave"),
]


def _normalize_type(jl_type: str) -> str | None:
    jl_type = (jl_type or "").strip().lower()
    return jl_type if jl_type in ("join", "leave") else None


def _parse_bool(text: str) -> bool | None:
    text = (text or "").strip().lower()
    if text in ("on", "yes", "true", "1", "aktif", "enable", "enabled"):
        return True
    if text in ("off", "no", "false", "0", "nonaktif", "disable", "disabled"):
        return False
    return None


class JoinLeave(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =================================================================
    # SLASH COMMANDS
    # =================================================================
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

        await self._dispatch(channel, config, member=interaction.user, guild=interaction.guild)
        await interaction.response.send_message(f"✅ Test embed **{type.value}** dikirim ke {channel.mention}.", ephemeral=True)

    # =================================================================
    # PREFIX COMMANDS (n!joinleave ...)
    # =================================================================
    @commands.group(name="joinleave", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def jl_prefix(self, ctx: commands.Context):
        await ctx.send(
            "Pakai salah satu:\n"
            f"`{ctx.prefix}joinleave builder <join|leave>`\n"
            f"`{ctx.prefix}joinleave toggle <join|leave> <on|off>`\n"
            f"`{ctx.prefix}joinleave test <join|leave>`"
        )

    @jl_prefix.command(name="builder")
    @commands.has_permissions(manage_guild=True)
    async def jl_prefix_builder(self, ctx: commands.Context, jl_type: str):
        jl_type = _normalize_type(jl_type)
        if not jl_type:
            await ctx.send("⚠️ Tipe harus `join` atau `leave`.")
            return
        default = DEFAULT_JOIN if jl_type == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(ctx.guild.id), jl_type, default=default)

        view = JoinLeaveBuilderView(
            store=store, guild=ctx.guild, jl_type=jl_type, config=config, author_id=ctx.author.id
        )
        message = await ctx.send(content=view.header_text(), embed=view.render_embed(), view=view)
        view.message = message

    @jl_prefix.command(name="toggle")
    @commands.has_permissions(manage_guild=True)
    async def jl_prefix_toggle(self, ctx: commands.Context, jl_type: str, state: str):
        jl_type = _normalize_type(jl_type)
        enabled = _parse_bool(state)
        if not jl_type or enabled is None:
            await ctx.send(f"⚠️ Format: `{ctx.prefix}joinleave toggle <join|leave> <on|off>`")
            return
        default = DEFAULT_JOIN if jl_type == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(ctx.guild.id), jl_type, default=default)
        config["enabled"] = enabled
        await store.set_path(str(ctx.guild.id), jl_type, config)
        status = "diaktifkan ✅" if enabled else "dinonaktifkan ⛔"
        await ctx.send(f"Notifikasi **{jl_type}** berhasil {status}.")

    @jl_prefix.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def jl_prefix_test(self, ctx: commands.Context, jl_type: str):
        jl_type = _normalize_type(jl_type)
        if not jl_type:
            await ctx.send("⚠️ Tipe harus `join` atau `leave`.")
            return
        default = DEFAULT_JOIN if jl_type == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(ctx.guild.id), jl_type, default=default)
        if not config.get("channel_id"):
            await ctx.send(f"⚠️ Channel belum diset. Pakai `{ctx.prefix}joinleave builder {jl_type}` dulu.")
            return
        channel = ctx.guild.get_channel(config["channel_id"])
        if not channel:
            await ctx.send("⚠️ Channel tidak ditemukan lagi, cek ulang di builder.")
            return
        await self._dispatch(channel, config, member=ctx.author, guild=ctx.guild)
        await ctx.send(f"✅ Test embed **{jl_type}** dikirim ke {channel.mention}.")

    # =================================================================
    # LISTENERS
    # =================================================================
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

        try:
            await self._dispatch(channel, config, member=member, guild=member.guild)
        except discord.Forbidden:
            pass

    async def _dispatch(self, channel: discord.abc.Messageable, config: dict, member, guild: discord.Guild):
        embed = build_joinleave_embed(config, member=member, guild=guild)
        link_view = build_row_link_view(config)
        content_text = resolve_content(config, member=member, guild=guild)
        await channel.send(content=content_text, embed=embed, view=link_view)


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinLeave(bot))
