# helpers.py - FIXED VERSION with proper channel handling and advanced UI

import os
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant, PeerIdInvalid, ChannelInvalid, ChatAdminRequired
from config import config
from database import db
import logging

logger = logging.getLogger(__name__)

async def force_subscribe_check(client: Client, user_id: int) -> bool:
    """Check if the user has joined the FORCE_SUB_CHANNEL."""
    if not config.FORCE_SUB_CHANNEL:
        return True
    
    try:
        # Handle both integer IDs and string usernames
        channel = config.FORCE_SUB_CHANNEL
        member = await client.get_chat_member(channel, user_id)
        return member.status not in ["left", "kicked"]
    except (PeerIdInvalid, ChannelInvalid) as e:
        logger.warning(f"Invalid FORCE_SUB_CHANNEL: {config.FORCE_SUB_CHANNEL}, Error: {e}")
        return True  # Allow access if channel is invalid
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Force subscribe check error: {e}")
        return True  # Allow access on error to prevent blocking

async def send_log_message(client: Client, message: str, log_type: str = "general"):
    """Send a log message to the configured log channel."""
    target_map = {
        "new_user": config.NEW_USER_LOG_CHANNEL,
        "merged_file": config.MERGED_FILE_LOG_CHANNEL,
        "general": config.LOG_CHANNEL
    }
    
    target = target_map.get(log_type, config.LOG_CHANNEL)
    
    if not target:
        logger.warning(f"No log channel configured for {log_type}")
        return False
        
    try:
        await client.send_message(target, message)
        return True
    except (PeerIdInvalid, ChannelInvalid) as e:
        logger.error(f"Invalid log channel {target}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error sending log message: {e}")
        return False

async def is_user_member(client: Client, user_id: int, chat_id: int) -> bool:
    """Check if user is member of a chat"""
    try:
        user = await client.get_chat_member(chat_id, user_id)
        return user.status not in ["left", "kicked"]
    except Exception:
        return False

async def is_authorized_user(user_id: int) -> bool:
    """Check if user is authorized to use bot in private"""
    # Check config first
    if user_id == config.OWNER_ID or user_id in config.ADMINS or user_id in config.AUTHORIZED_USERS:
        return True
    # Then check database
    return await db.is_user_authorized(user_id)

async def is_authorized_chat(chat_id: int) -> bool:
    """Check if chat is authorized for bot usage"""
    return chat_id in config.AUTHORIZED_CHATS

def get_main_keyboard():
    """Get advanced main keyboard for start message"""
    keyboard = []

    # Row 1: Core functions
    keyboard.append([
        InlineKeyboardButton("❓ Help", callback_data="help"),
        InlineKeyboardButton("ℹ️ About", callback_data="about")
    ])

    # Row 2: Navigation
    keyboard.append([
        InlineKeyboardButton("🏠 Home", callback_data="back_to_start"),
        InlineKeyboardButton("👨‍💻 Developer", callback_data="developer")
    ])

    # Row 3: Links (if available)
    links_row = []
    if config.UPDATE_CHANNEL:
        links_row.append(InlineKeyboardButton("📢 Updates", url=config.UPDATE_CHANNEL))
    if config.SUPPORT_GROUP:
        links_row.append(InlineKeyboardButton("💬 Support", url=config.SUPPORT_GROUP))
    
    if links_row:
        keyboard.append(links_row)

    return InlineKeyboardMarkup(keyboard)

def get_video_queue_keyboard(video_count: int):
    """Get keyboard for video queue management"""
    keyboard = []

    if video_count == 1:
        # Only one video - show add more and clear options
        keyboard.append([
            InlineKeyboardButton("➕ Add More Videos", callback_data="add_more_videos")
        ])
        keyboard.append([
            InlineKeyboardButton("🗑️ Clear All", callback_data="clear_all_videos")
        ])
    else:
        # Multiple videos - show merge now option
        keyboard.append([
            InlineKeyboardButton("🎬 Merge Now", callback_data="merge_now")
        ])
        keyboard.append([
            InlineKeyboardButton("➕ Add More Videos", callback_data="add_more_videos"),
            InlineKeyboardButton("🗑️ Clear All", callback_data="clear_all_videos")
        ])

    # Home button
    keyboard.append([
        InlineKeyboardButton("🏠 Home", callback_data="back_to_start")
    ])

    return InlineKeyboardMarkup(keyboard)

def get_upload_choice_keyboard():
    """Get upload choice keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📤 Telegram", callback_data="upload_telegram"),
            InlineKeyboardButton("☁️ GoFile", callback_data="upload_gofile")
        ],
        [
            InlineKeyboardButton("🏠 Home", callback_data="back_to_start")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    """Get admin panel keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("👥 User Management", callback_data="admin_users"),
            InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton("📝 Logs", callback_data="admin_logs"),
            InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")
        ],
        [
            InlineKeyboardButton("🏠 Home", callback_data="back_to_start")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)

def get_help_text():
    """Get help text"""
    return f"""📖 **Help & Instructions**

🎬 **How to use {config.BOT_NAME}:**

**Step 1: Join Required Channels**
• Join our channel first (forced)
• Join authorized groups for merging

**Step 2: Send Videos**
• Send video files directly (max 2GB each)
• Send video URLs (YouTube, etc.)
• Add multiple videos to your queue

**Step 3: Merge Process**  
• Use /merge command to start
• "Add More Videos" - Add additional files
• "Merge Now" - Start merging (requires 2+ videos)
• "Clear All" - Remove all from queue

**Step 4: Download Result**
• Choose upload method (Telegram/GoFile)
• Download your merged video
• High-quality output guaranteed

**📋 Available Commands:**
• `/start` - Start the bot
• `/help` - Show this help
• `/about` - About the bot  
• `/merge` - Start merge process
• `/cancel` - Clear queue and cancel

**🔒 Authorization:**
• Private chat: Owner/Admins only
• Group chat: Authorized groups only
• Contact owner for access

**⚡ Pro Tips:**
• Videos with same resolution merge faster
• Supported: MP4, AVI, MKV, MOV, etc.
• Maximum file size: 2GB per video
• Queue unlimited videos before merging

**🛠️ Need help?** Join our support group!

**Developer:** {config.DEVELOPER}"""

def get_about_text():
    """Get about text"""
    return f"""ℹ️ **About {config.BOT_NAME}**

🤖 **Bot Name:** {config.BOT_NAME}
👨‍💻 **Developer:** {config.DEVELOPER}
📅 **Version:** v2.0 Professional
🚀 **Language:** Python
⚙️ **Framework:** Pyrogram

**🌟 Key Features:**
• ✅ Multiple video merging
• ✅ URL support (YouTube, etc.)
• ✅ Advanced queue management
• ✅ Professional UI/UX
• ✅ MongoDB database
• ✅ Admin panel & broadcasting
• ✅ Force subscribe system
• ✅ User authorization
• ✅ Progress indicators
• ✅ High-quality output

**📊 Performance:**
• Lightning fast processing
• Lossless quality merging
• Multiple format support
• Cloud storage integration
• Real-time progress tracking

**🔒 Security Features:**
• User authorization system
• Group-based access control
• Admin management tools
• Comprehensive logging
• Error handling & recovery

**💝 Support Development:**
If you like this bot, please:
• ⭐ Share with friends
• 📢 Join our community
• 💬 Provide feedback

**🔗 Important Links:**
• **Update Channel:** {config.UPDATE_CHANNEL or 'Not Set'}
• **Support Group:** {config.SUPPORT_GROUP or 'Not Set'}

© 2024 - Made with ❤️ by {config.DEVELOPER}

*Professional Video Merger Bot*"""

async def is_user_banned_check(user_id: int) -> bool:
    """Check if user is banned"""
    return await db.is_user_banned(user_id)

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    try:
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    except (ValueError, OverflowError):
        return "Unknown size"

async def verify_user_complete(client: Client, message: Message) -> bool:
    """Complete user verification - SIMPLIFIED VERSION"""
    user_id = message.from_user.id

    # 1. Ban check first
    if await db.is_user_banned(user_id):
        await message.reply_text(
            "🚫 **You are banned from using this bot!**\n\n"
            "If you think this is a mistake, please contact support.",
            quote=True
        )
        return False

    # 2. Force subscribe check
    if not await force_subscribe_check(client, user_id):
        return False  # Force subscribe message handled in main handlers

    return True
