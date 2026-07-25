"""
Builder embed untuk notifikasi join/leave, berdasarkan config dari panel builder.
"""
import discord
from utils.variables import resolve_variables

DIVIDER = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"


def _parse_color(color_hex: str) -> discord.Color:
    try:
        return discord.Color(int(color_hex.replace("#", ""), 16))
    except Exception:
        return discord.Color(0xFFD54A)


def build_joinleave_embed(config: dict, member=None, guild: discord.Guild = None) -> discord.Embed:
    color = _parse_color(config.get("color") or "#FFD54A")

    title = resolve_variables(config.get("title") or "", member, guild) or None
    description = resolve_variables(config.get("description") or "", member, guild) or None

    embed = discord.Embed(title=title, description=description, color=color)

    thumb = config.get("thumbnail")
    if thumb:
        thumb = resolve_variables(thumb, member, guild)
        if thumb.startswith("http"):
            embed.set_thumbnail(url=thumb)

    banner = config.get("banner")
    if banner:
        banner = resolve_variables(banner, member, guild)
        if banner.startswith("http"):
            embed.set_image(url=banner)

    for block in config.get("blocks", []):
        btype = block.get("type")
        if btype == "separator":
            embed.add_field(name="\u200b", value=DIVIDER, inline=False)
        elif btype == "field":
            embed.add_field(
                name=resolve_variables(block.get("name") or "\u200b", member, guild),
                value=resolve_variables(block.get("value") or "\u200b", member, guild),
                inline=bool(block.get("inline", False)),
            )
        elif btype == "icon_field":
            name = f"{block.get('icon', '')} {block.get('name', '')}".strip()
            embed.add_field(
                name=resolve_variables(name or "\u200b", member, guild),
                value=resolve_variables(block.get("value") or "\u200b", member, guild),
                inline=bool(block.get("inline", False)),
            )

    if member is not None and guild is not None:
        embed.set_footer(
            text=f"ID: {member.id}",
            icon_url=str(guild.icon.url) if guild.icon else None,
        )

    return embed


def build_row_link_view(config: dict):
    links = config.get("row_links", [])
    if not links:
        return None
    view = discord.ui.View(timeout=None)
    for link in links[:5]:
        view.add_item(
            discord.ui.Button(
                label=link["label"][:80],
                url=link["url"],
                style=discord.ButtonStyle.link,
            )
        )
    return view
