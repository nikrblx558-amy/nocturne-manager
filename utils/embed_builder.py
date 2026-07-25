"""
Builder embed untuk notifikasi join/leave, berdasarkan config dari panel builder.
"""
import discord
from utils.variables import resolve_variables

# Garis tipis (box-drawing character), BUKAN blok tebal, biar rapi kayak referensi.
DIVIDER = "─" * 24

DARK_RED = 0x8B0000


def _parse_color(color_hex: str) -> discord.Color:
    try:
        return discord.Color(int(color_hex.replace("#", ""), 16))
    except Exception:
        return discord.Color(DARK_RED)


def build_joinleave_embed(config: dict, member=None, guild: discord.Guild = None) -> discord.Embed:
    color = _parse_color(config.get("color") or f"#{DARK_RED:06X}")

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

    # Footer: pakai teks custom dari builder kalau ada, fallback ke default branding.
    footer_text = resolve_variables(config.get("footer") or "", member, guild).strip()
    if not footer_text:
        footer_text = "Nocturne Manager • Join & Leave System"
    if member is not None:
        footer_text = f"{footer_text} • ID: {member.id}"

    footer_icon = str(guild.icon.url) if guild is not None and guild.icon else None
    embed.set_footer(text=footer_text, icon_url=footer_icon)

    return embed


def resolve_content(config: dict, member=None, guild: discord.Guild = None) -> str | None:
    """Teks yang dikirim di luar embed (di atas embed), misal sambutan/mention."""
    text = resolve_variables(config.get("content") or "", member, guild).strip()
    return text or None


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
