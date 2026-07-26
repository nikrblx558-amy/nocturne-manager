"""
Shared branding config used across cogs (e.g. the post-application embed and
the /help command). Set these as environment variables — leave empty to hide
that part wherever it's used.
"""
import os

BOT_INVITE_URL = os.getenv("BOT_INVITE_URL")
SUPPORT_SERVER_URL = os.getenv("SUPPORT_SERVER_URL")
BOT_BANNER_URL = os.getenv("BOT_BANNER_URL")
