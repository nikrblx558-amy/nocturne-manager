import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import JSONStore
from utils.embed_builder import build_joinleave_layout
from cogs.panel_builder import JoinLeaveBuilderView, DEFAULT_JOIN, DEFAULT_LEAVE
from cogs.premium import get_limits

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
    if text in ("on", "yes", "true", "1", "enable", "enabled"):
        return True
    if text in ("off", "no", "false", "0", "disable", "disabled"):
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
        description="Configure member join & leave notifications",
    )

    @jl_group.command(name="builder", description="Open the join/leave embed builder (live preview)")
    @app_commands.describe(type="Open the builder for Join or Leave")
    @app_commands.choices(type=TYPE_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def builder(self, interaction: discord.Interaction, type: app_commands.Choice[str]):
        default = DEFAULT_JOIN if type.value == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(interaction.guild_id), type.value, default=default)
        limits = await get_limits(interaction.guild_id)

        view = JoinLeaveBuilderView(
            store=store,
            guild=interaction.guild,
            jl_type=type.value,
            config=config,
            author_id=interaction.user.id,
            max_row_links=limits["max_row_links"],
            is_premium=limits["premium"],
        )
        await interaction.response.send_message(
            content=view.header_text(),
            embed=view.render_embed(),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    @jl_group.command(name="toggle", description="Quickly enable/disable join or leave notifications")
    @app_commands.choices(type=TYPE_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle(self, interaction: discord.Interaction, type: app_commands.Choice[str], enabled: bool):
        default = DEFAULT_JOIN if type.value == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(interaction.guild_id), type.value, default=default)
        config["enabled"] = enabled
        await store.set_path(str(interaction.guild_id), type.value, config)
        status = "enabled ✅" if enabled else "disabled ⛔"
        await interaction.response.send_message(f"**{type.value}** notifications have been {status}.", ephemeral=True)

    @jl_group.command(name="test", description="Send a sample join/leave embed to the configured channel")
    @app_commands.choices(type=TYPE_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test(self, interaction: discord.Interaction, type: app_commands.Choice[str]):
        default = DEFAULT_JOIN if type.value == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(interaction.guild_id), type.value, default=default)
        if not config.get("channel_id"):
            await interaction.response.send_message("⚠️ No channel set yet. Open `/joinleave builder` first.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(config["channel_id"])
        if not channel:
            await interaction.response.send_message("⚠️ That channel no longer exists, check the builder again.", ephemeral=True)
            return

        await self._dispatch(channel, config, member=interaction.user, guild=interaction.guild)
        await interaction.response.send_message(f"✅ Test **{type.value}** embed sent to {channel.mention}.", ephemeral=True)

    # =================================================================
    # PREFIX COMMANDS (e.g. n!joinleave ...)
    # =================================================================
    @commands.group(name="joinleave", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def jl_prefix(self, ctx: commands.Context):
        await ctx.send(
            "Usage:\n"
            f"`{ctx.prefix}joinleave builder <join|leave>`\n"
            f"`{ctx.prefix}joinleave toggle <join|leave> <on|off>`\n"
            f"`{ctx.prefix}joinleave test <join|leave>`"
        )

    @jl_prefix.command(name="builder")
    @commands.has_permissions(manage_guild=True)
    async def jl_prefix_builder(self, ctx: commands.Context, jl_type: str):
        jl_type = _normalize_type(jl_type)
        if not jl_type:
            await ctx.send("⚠️ Type must be `join` or `leave`.")
            return
        default = DEFAULT_JOIN if jl_type == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(ctx.guild.id), jl_type, default=default)
        limits = await get_limits(ctx.guild.id)

        view = JoinLeaveBuilderView(
            store=store, guild=ctx.guild, jl_type=jl_type, config=config, author_id=ctx.author.id,
            max_row_links=limits["max_row_links"], is_premium=limits["premium"],
        )
        message = await ctx.send(content=view.header_text(), embed=view.render_embed(), view=view)
        view.message = message

    @jl_prefix.command(name="toggle")
    @commands.has_permissions(manage_guild=True)
    async def jl_prefix_toggle(self, ctx: commands.Context, jl_type: str, state: str):
        jl_type = _normalize_type(jl_type)
        enabled = _parse_bool(state)
        if not jl_type or enabled is None:
            await ctx.send(f"⚠️ Usage: `{ctx.prefix}joinleave toggle <join|leave> <on|off>`")
            return
        default = DEFAULT_JOIN if jl_type == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(ctx.guild.id), jl_type, default=default)
        config["enabled"] = enabled
        await store.set_path(str(ctx.guild.id), jl_type, config)
        status = "enabled ✅" if enabled else "disabled ⛔"
        await ctx.send(f"**{jl_type}** notifications have been {status}.")

    @jl_prefix.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def jl_prefix_test(self, ctx: commands.Context, jl_type: str):
        jl_type = _normalize_type(jl_type)
        if not jl_type:
            await ctx.send("⚠️ Type must be `join` or `leave`.")
            return
        default = DEFAULT_JOIN if jl_type == "join" else DEFAULT_LEAVE
        config = await store.get_path(str(ctx.guild.id), jl_type, default=default)
        if not config.get("channel_id"):
            await ctx.send(f"⚠️ No channel set yet. Use `{ctx.prefix}joinleave builder {jl_type}` first.")
            return
        channel = ctx.guild.get_channel(config["channel_id"])
        if not channel:
            await ctx.send("⚠️ That channel no longer exists, check the builder again.")
            return
        await self._dispatch(channel, config, member=ctx.author, guild=ctx.guild)
        await ctx.send(f"✅ Test **{jl_type}** embed sent to {channel.mention}.")

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
        layout = build_joinleave_layout(config, member=member, guild=guild)
        await channel.send(view=layout)


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinLeave(bot))
