"""
Resolver variabel dinamis untuk embed join/leave.
Semua placeholder pakai format {nama_variabel}.
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
    "**🧩 Variabel yang bisa dipakai di Title / Description / Field / Thumbnail / Banner:**\n"
    "`{user}` — mention user\n"
    "`{user_name}` — username\n"
    "`{user_display}` — nickname / display name\n"
    "`{user_id}` — ID user\n"
    "`{user_avatar}` — link avatar user (cocok dipakai di Thumbnail)\n"
    "`{user_created}` — tanggal akun Discord dibuat\n"
    "`{server}` — nama server\n"
    "`{server_icon}` — link icon server\n"
    "`{member_count}` — jumlah member sekarang\n"
    "`{date}` — tanggal hari ini\n"
    "`{time}` — jam sekarang\n"
)
