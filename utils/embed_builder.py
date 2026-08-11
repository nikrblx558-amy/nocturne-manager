"""
Embed builder for join/leave notifications.

There are TWO renderers here on purpose:
- `build_joinleave_embed()` returns a classic discord.Embed — used ONLY by
  the live-preview panel builder (JoinLeaveBuilderView), since that UI relies
  on the classic content+embed+view combo for its editing flow.
- `build_joinleave_layout()` returns a Components V2 discord.ui.LayoutView —
  used for the ACTUAL notification sent to the channel on a real join/leave
  (and for `/joinleave test`). V2 cannot be mixed with classic embeds in the
  same message, hence the two separate code paths.
"""
import discord
from discord.components import MediaGalleryItem
from utils.variables import resolve_variables

# Thin box-drawing separator line (NOT a thick block) for a clean, subtle look.
DIVIDER = "─" * 24

DARK_RED = 0x8B0000


def parse_color(color_hex: str | None, default: int = DARK_RED) -> int:
    """Parse a '#RRGGBB' string into an int color. Falls back to `default` if invalid/empty."""
    if not color_hex:
        return default
    try:
        return int(color_hex.strip().lstrip("#"), 16)
    except ValueError:
        return default


def build_joinleave_embed(config: dict, member=None, guild: discord.Guild = None) -> discord.Embed:
    color = discord.Color(parse_color(config.get("color")))

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

    # Footer: use the custom text from the builder if set, otherwise fall back to branding.
    footer_text = resolve_variables(config.get("footer") or "", member, guild).strip()
    if not footer_text:
        footer_text = "Nocturne Manager • Join & Leave System"
    if member is not None:
        footer_text = f"{footer_text} • ID: {member.id}"

    footer_icon = str(guild.icon.url) if guild is not None and guild.icon else None
    embed.set_footer(text=footer_text, icon_url=footer_icon)

    return embed


def build_joinleave_layout(config: dict, member=None, guild: discord.Guild = None) -> discord.ui.LayoutView:
    """Components V2 version of the notification actually sent to the channel."""
    color = parse_color(config.get("color"))

    title = resolve_variables(config.get("title") or "", member, guild).strip()
    description = resolve_variables(config.get("description") or "", member, guild).strip()

    text_parts = []
    if title:
        text_parts.append(f"# {title}")
    if description:
        text_parts.append(description)
    header_text = "\n\n".join(text_parts) or "\u200b"

    thumb = config.get("thumbnail")
    if thumb:
        thumb = resolve_variables(thumb, member, guild)
        if not thumb.startswith("http"):
            thumb = None

    banner = config.get("banner")
    if banner:
        banner = resolve_variables(banner, member, guild)
        if not banner.startswith("http"):
            banner = None

    footer_text = resolve_variables(config.get("footer") or "", member, guild).strip()
    if not footer_text:
        footer_text = "Nocturne Manager • Join & Leave System"
    if member is not None:
        footer_text = f"{footer_text} • ID: {member.id}"

    children = []
    if thumb:
        children.append(discord.ui.Section(discord.ui.TextDisplay(header_text), accessory=discord.ui.Thumbnail(media=thumb)))
    else:
        children.append(discord.ui.TextDisplay(header_text))

    if banner:
        children.append(discord.ui.MediaGallery(MediaGalleryItem(media=banner)))

    for block in config.get("blocks", []):
        btype = block.get("type")
        if btype == "separator":
            children.append(discord.ui.Separator())
        elif btype == "field":
            name = resolve_variables(block.get("name") or "\u200b", member, guild)
            value = resolve_variables(block.get("value") or "\u200b", member, guild)
            children.append(discord.ui.TextDisplay(f"**{name}**\n{value}"))
        elif btype == "icon_field":
            icon = block.get("icon", "")
            name = resolve_variables(block.get("name") or "", member, guild)
            value = resolve_variables(block.get("value") or "\u200b", member, guild)
            children.append(discord.ui.TextDisplay(f"**{icon} {name}**\n{value}".strip()))

    children.append(discord.ui.Separator())
    children.append(discord.ui.TextDisplay(f"-# {footer_text}"))

    link_buttons = [
        discord.ui.Button(label=link["label"][:80], url=link["url"], style=discord.ButtonStyle.link)
        for link in config.get("row_links", [])[:5]
    ]
    if link_buttons:
        children.append(discord.ui.ActionRow(*link_buttons))

    container = discord.ui.Container(*children, accent_colour=discord.Color(color))

    view = discord.ui.LayoutView(timeout=None)
    content_text = resolve_content(config, member, guild)
    if content_text:
        view.add_item(discord.ui.TextDisplay(content_text))
    view.add_item(container)
    return view


def resolve_content(config: dict, member=None, guild: discord.Guild = None) -> str | None:
    """Text shown above the main container, e.g. a greeting/mention."""
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
