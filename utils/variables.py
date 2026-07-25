"""
Dynamic variable resolver used in join/leave embeds.
All placeholders use the {variable_name} format.
"""
import discord
from datetime import datetime


def resolve_variables(text: str, member: "discord.Member | discord.User" = None, guild: discord.Guild = None) -> str:
    if not text:
        return text

    guild = guild or (getattr(member, "guild", None) if member else None)
    replacements = {}

    if member is not None:
        replacements.update({
            "{user}": member.mention,
            "{user_name}": member.name,
            "{user_display}": getattr(member, "display_name", member.name),
            "{user_id}": str(member.id),
            "{user_avatar}": str(member.display_avatar.url),
            "{user_created}": member.created_at.strftime("%d %B %Y"),
        })

    if guild is not None:
        replacements.update({
            "{server}": guild.name,
            "{server_icon}": str(guild.icon.url) if guild.icon else "",
            "{member_count}": str(guild.member_count),
        })

    replacements["{date}"] = datetime.now().strftime("%d %B %Y")
    replacements["{time}"] = datetime.now().strftime("%H:%M")

    for key, value in replacements.items():
        text = text.replace(key, str(value))
    return text


VARIABLE_HELP = (
    "**🧩 Variables you can use in Title / Description / Field / Footer / Content / Thumbnail / Banner:**\n"
    "`{user}` — mentions the user\n"
    "`{user_name}` — username\n"
    "`{user_display}` — nickname / display name\n"
    "`{user_id}` — user ID\n"
    "`{user_avatar}` — the user's avatar link (great for Thumbnail)\n"
    "`{user_created}` — the date the account was created\n"
    "`{server}` — server name\n"
    "`{server_icon}` — server icon link\n"
    "`{member_count}` — current member count\n"
    "`{date}` — today's date\n"
    "`{time}` — current time\n"
)
