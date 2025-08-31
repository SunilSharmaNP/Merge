# helpers.py - Helper Functions for Force Subscribe and Auth
import logging

from pyrogram import Client
from pyrogram.errors import UserNotParticipant, ChannelPrivate
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from database import db

logger = logging.getLogger(__name__)

async def is_user_member(client: Client, user_id: int, channel_id: str) -> bool:
    """Check if user is member of force subscribe channel."""
    try:
        if not config.FORCE_SUB_CHANNEL:
            return True
        member = await client.get_chat_member(channel_id, user_id)
        return member.status not in ["left", "kicked"]
    except (UserNotParticipant, ChannelPrivate):
        return False
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return True  # On error, allow access

async def force_subscribe_check(client: Client, message) -> bool:
    """Ensure user has joined the FORCE_SUB_CHANNEL."""
    try:
        if not config.FORCE_SUB_CHANNEL:
            return True

        user_id = message.from_user.id
        if user_id in config.ADMINS:
            return True

        if await is_user_member(client, user_id, config.FORCE_SUB_CHANNEL):
            return True

        # Not a member → prompt to join
        try:
            chat = await client.get_chat(config.FORCE_SUB_CHANNEL)
            invite = chat.invite_link or f"https://t.me/{chat.username}"
            title = chat.title
        except Exception:
            invite = f"https://t.me/{config.FORCE_SUB_CHANNEL.lstrip('@')}"
            title = "our channel"

        text = (
            f"🔒 **Access Denied!**\n\n"
            f"You must join **{title}** to use this bot.\n\n"
            f"📢 Click below to join, then tap **Check Again**."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url=invite)],
            [InlineKeyboardButton("🔄 Check Again", callback_data="check_subscription")]
        ])
        await message.reply_text(text, reply_markup=kb, quote=True)
        return False
    except Exception as e:
        logger.error(f"Error in force_subscribe_check: {e}")
        return True

async def is_authorized_user(user_id: int, chat_id: int = None) -> bool:
    """Check if user or chat is authorized to use the bot."""
    try:
        if user_id in config.ADMINS or user_id == config.OWNER_ID:
            return True

        # Private chat → registered, not banned user
        if chat_id == user_id:
            user = await db.get_user(user_id)
            return bool(user and not user.get("is_banned", False))

        # Group chat → must be in authorized_chats
        if chat_id:
            return await db.is_authorized_chat(chat_id)

        return False
    except Exception as e:
        logger.error(f"Error checking authorization: {e}")
        return False

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Return the main menu keyboard."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Help", callback_data="help_menu"),
         InlineKeyboardButton("ℹ️ About", callback_data="about_menu")],
        [InlineKeyboardButton("🏠 Home", callback_data="home_menu"),
         InlineKeyboardButton("🔙 Back", callback_data="back_to_start")],
        [
            InlineKeyboardButton("📢 Updates", url=f"https://t.me/{config.UPDATE_CHANNEL}")
            if config.UPDATE_CHANNEL else None,
            InlineKeyboardButton("💬 Support", url=f"https://t.me/{config.SUPPORT_GROUP}")
            if config.SUPPORT_GROUP else None
        ],
        [InlineKeyboardButton("👨‍💻 Developer", url=f"tg://user?id={config.OWNER_ID}")]
    ])
    # Remove empty buttons
    kb.inline_keyboard = [
        [btn for btn in row if btn] for row in kb.inline_keyboard
    ]
    kb.inline_keyboard = [row for row in kb.inline_keyboard if row]
    return kb

def get_video_queue_keyboard(count: int) -> InlineKeyboardMarkup | None:
    """Keyboard to manage video queue."""
    if count <= 0:
        return None
    if count == 1:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add More", callback_data="add_more"),
             InlineKeyboardButton("🗑 Clear All", callback_data="clear_queue")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Merge Now", callback_data="start_merge"),
         InlineKeyboardButton("🗑 Clear All", callback_data="clear_queue")],
        [InlineKeyboardButton("➕ Add More", callback_data="add_more")]
    ])

def get_upload_choice_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for upload destination choice."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Telegram", callback_data="upload_tg")],
        [InlineKeyboardButton("🔗 GoFile.io", callback_data="upload_gofile")]
    ])

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for the admin panel."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"),
         InlineKeyboardButton("👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("🔧 Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("💬 Auth Chats", callback_data="admin_auth"),
         InlineKeyboardButton("📋 Logs", callback_data="admin_logs")]
    ])

async def send_log_message(client: Client, log_type: str, text: str, user_id: int = None):
    """Send a formatted log message to the configured log channels."""
    try:
        if log_type == "new_user" and config.LOG_CHANNEL:
            await client.send_message(
                config.LOG_CHANNEL,
                f"👤 **New User**\nUser ID: `{user_id}`\nTime: `{text}`"
            )
        elif log_type == "merge_activity" and config.MERGE_LOG_CHANNEL:
            await client.send_message(
                config.MERGE_LOG_CHANNEL,
                f"🎬 **Merge Completed**\n{text}"
            )
    except Exception as e:
        logger.error(f"Error sending log message: {e}")

def format_file_size(size: int) -> str:
    """Convert bytes to human-readable string."""
    if size == 0:
        return "0B"
    units = ["B","KB","MB","GB","TB"]
    import math
    idx = int(math.floor(math.log(size,1024)))
    val = round(size / (1024**idx), 2)
    return f"{val} {units[idx]}"

def get_help_text() -> str:
    """Return help text."""
    return (
        "📚 **How to Use Video Merger Bot**\n\n"
        "1. Send videos or direct download links.\n"
        "2. I'll add them to your queue.\n"
        "3. Click **Merge Now** when you have 2+ items.\n"
        "4. Choose upload destination (Telegram / GoFile).\n"
        "5. Download your merged video!\n\n"
        "Use /cancel to clear the queue anytime."
    )

def get_about_text() -> str:
    """Return about text."""
    return (
        f"ℹ️ **About {config.BOT_NAME}**\n\n"
        "This bot merges videos professionally using FFmpeg.\n"
        f"Developer: {config.DEVELOPER}\n"
        "Visit updates: "
        f"https://t.me/{config.UPDATE_CHANNEL}"
    )
