# helpers.py - Helper Functions for Force Subscribe and Auth
import logging
from datetime import datetime
from pyrogram import Client
from pyrogram.errors import UserNotParticipant, ChannelPrivate, ChatAdminRequired
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from database import db

logger = logging.getLogger(__name__)

async def is_user_member(client: Client, user_id: int, channel_id: str) -> bool:
    """Check if user is member of force subscribe channel."""
    try:
        if not channel_id:
            return True
        
        # Handle different channel ID formats
        if channel_id.startswith('@'):
            chat_id = channel_id
        elif channel_id.startswith('-100'):
            chat_id = int(channel_id)
        else:
            chat_id = f"@{channel_id}"
        
        member = await client.get_chat_member(chat_id, user_id)
        return member.status not in ["left", "kicked"]
    except (UserNotParticipant, ChannelPrivate):
        return False
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return True  # Allow access on error

async def force_subscribe_check(client: Client, message) -> bool:
    """Comprehensive force subscribe check."""
    try:
        if not hasattr(config, 'FORCE_SUB_CHANNEL') or not config.FORCE_SUB_CHANNEL:
            return True

        user_id = message.from_user.id
        
        # Skip check for admins and owner
        if user_id == config.OWNER_ID or user_id in getattr(config, 'ADMINS', []):
            return True

        # Check membership
        if await is_user_member(client, user_id, config.FORCE_SUB_CHANNEL):
            return True

        # User not subscribed - send force subscribe message
        try:
            # Get channel info
            channel_id = config.FORCE_SUB_CHANNEL
            if channel_id.startswith('@'):
                chat_id = channel_id
            elif channel_id.startswith('-100'):
                chat_id = int(channel_id)
            else:
                chat_id = f"@{channel_id}"
            
            chat = await client.get_chat(chat_id)
            invite_link = chat.invite_link or f"https://t.me/{chat.username}" if chat.username else None
            title = chat.title or "Our Channel"
            
        except Exception as e:
            logger.error(f"Error getting chat info: {e}")
            invite_link = f"https://t.me/{config.FORCE_SUB_CHANNEL.lstrip('@')}"
            title = "our channel"

        # Create force subscribe message
        text = f"""
🔒 **Access Denied!**

To use this bot, you must join **{title}** first.

📢 Click the button below to join, then tap **Check Again**.
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📢 Join {title}", url=invite_link)] if invite_link else [],
            [InlineKeyboardButton("🔄 Check Again", callback_data="check_subscription")]
        ])
        
        # Remove empty rows
        keyboard.inline_keyboard = [row for row in keyboard.inline_keyboard if row]
        
        # Send force subscribe message with image if available
        if hasattr(config, 'FORCE_SUB_PIC') and config.FORCE_SUB_PIC:
            await message.reply_photo(
                photo=config.FORCE_SUB_PIC,
                caption=text,
                reply_markup=keyboard,
                quote=True
            )
        else:
            await message.reply_text(text, reply_markup=keyboard, quote=True)
        
        return False
        
    except Exception as e:
        logger.error(f"Error in force_subscribe_check: {e}")
        return True  # Allow access on error

async def is_user_banned_check(user_id: int) -> bool:
    """Check if user is banned with detailed logging."""
    try:
        banned = await db.is_user_banned(user_id)
        if banned:
            logger.info(f"Blocked banned user: {user_id}")
        return banned
    except Exception as e:
        logger.error(f"Error checking ban status: {e}")
        return False

async def is_authorized_user(user_id: int, chat_id: int = None) -> bool:
    """Comprehensive authorization check."""
    try:
        # Owner and admins always authorized
        if user_id == config.OWNER_ID or user_id in getattr(config, 'ADMINS', []):
            return True
        
        # Check if user is banned
        if await is_user_banned_check(user_id):
            return False
        
        # Private chat authorization
        if chat_id == user_id:  # Private chat
            user = await db.get_user(user_id)
            return user is not None
        
        # Group chat authorization
        if chat_id and chat_id != user_id:
            return await db.is_authorized_chat(chat_id)
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking authorization: {e}")
        return False

async def verify_user_complete(client: Client, message) -> bool:
    """Complete user verification including all checks."""
    user_id = message.from_user.id
    
    try:
        # 1. Check if user is banned
        if await is_user_banned_check(user_id):
            ban_text = f"""
🚫 **You are banned from using this bot.**

Contact the owner if you think this is a mistake.
👨‍💻 Owner: [Click here](tg://user?id={config.OWNER_ID})
"""
            await message.reply_text(ban_text, quote=True)
            return False
        
        # 2. Force subscribe check
        if not await force_subscribe_check(client, message):
            return False
        
        # 3. Add user to database if new
        user = await db.get_user(user_id)
        if not user:
            success = await db.add_user(
                user_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name
            )
            
            if success:
                # Send new user log
                await send_log_message(
                    client, "new_user",
                    f"👤 **New User Joined**\n\n**Name:** {message.from_user.first_name}\n**Username:** @{message.from_user.username or 'None'}\n**ID:** `{user_id}`\n**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    user_id
                )
        else:
            # Update user activity
            await db.update_user_activity(user_id)
        
        return True
        
    except Exception as e:
        logger.error(f"Error in verify_user_complete: {e}")
        return True  # Allow access on error

async def send_log_message(client: Client, log_type: str, message: str, user_id: int = None):
    """Send log messages to appropriate channels."""
    try:
        if log_type == "new_user" and hasattr(config, 'LOG_CHANNEL') and config.LOG_CHANNEL:
            await client.send_message(config.LOG_CHANNEL, message)
        
        elif log_type == "merge_activity" and hasattr(config, 'MERGE_LOG_CHANNEL') and config.MERGE_LOG_CHANNEL:
            await client.send_message(config.MERGE_LOG_CHANNEL, message)
        
        elif hasattr(config, 'LOG_CHANNEL') and config.LOG_CHANNEL:
            # Fallback to main log channel
            await client.send_message(config.LOG_CHANNEL, message)
            
    except Exception as e:
        logger.error(f"Error sending log message: {e}")

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Return the main menu keyboard."""
    buttons = [
        [InlineKeyboardButton("📚 Help", callback_data="help_menu"),
         InlineKeyboardButton("ℹ️ About", callback_data="about_menu")],
        [InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]
    ]
    
    # Add update channel button if configured
    if hasattr(config, 'UPDATE_CHANNEL') and config.UPDATE_CHANNEL:
        buttons.append([
            InlineKeyboardButton("📢 Updates", url=f"https://t.me/{config.UPDATE_CHANNEL.lstrip('@')}")
        ])
    
    # Add support group button if configured
    if hasattr(config, 'SUPPORT_GROUP') and config.SUPPORT_GROUP:
        buttons.append([
            InlineKeyboardButton("💬 Support", url=f"https://t.me/{config.SUPPORT_GROUP.lstrip('@')}")
        ])
    
    # Add developer button
    buttons.append([
        InlineKeyboardButton("👨‍💻 Developer", url=f"tg://user?id={config.OWNER_ID}")
    ])
    
    return InlineKeyboardMarkup(buttons)

def get_video_queue_keyboard(count: int) -> InlineKeyboardMarkup:
    """Get keyboard for video queue management."""
    if count <= 0:
        return None
    elif count == 1:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add More", callback_data="add_more"),
             InlineKeyboardButton("🗑 Clear", callback_data="clear_queue")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Merge Now", callback_data="start_merge"),
             InlineKeyboardButton("🗑 Clear", callback_data="clear_queue")],
            [InlineKeyboardButton("➕ Add More", callback_data="add_more")]
        ])

def get_upload_choice_keyboard() -> InlineKeyboardMarkup:
    """Get upload destination choice keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload to Telegram", callback_data="upload_tg")],
        [InlineKeyboardButton("🔗 Upload to GoFile", callback_data="upload_gofile")]
    ])

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Get admin panel keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"),
         InlineKeyboardButton("👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("🔧 Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("💬 Auth Chats", callback_data="admin_auth"),
         InlineKeyboardButton("📋 Logs", callback_data="admin_logs")]
    ])

def format_file_size(size: int) -> str:
    """Convert bytes to human-readable format."""
    if size == 0:
        return "0B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f"{s} {units[i]}"

def get_help_text() -> str:
    """Return help text."""
    return """
📚 **How to Use Video Merger Bot**

🎬 **Basic Usage:**
1. Send me videos or direct download links
2. I'll add them to your merge queue
3. When you have 2+ videos, click "🎬 Merge Now"
4. Choose upload destination (Telegram or GoFile)
5. Get your merged video!

📝 **Supported Formats:**
• Video files uploaded to Telegram
• Direct download links (HTTP/HTTPS)
• Multiple video formats (MP4, MKV, AVI, etc.)

⚡ **Features:**
• Fast merging for compatible videos
• Automatic quality optimization
• Custom thumbnails support
• Progress tracking
• Multiple upload options

💡 **Tips:**
• Videos with same resolution merge faster
• Use /cancel to clear your queue anytime
• Large files may take longer to process

❓ **Need Help?** Contact our support team!
"""

def get_about_text() -> str:
    """Return about text."""
    return f"""
ℹ️ **About {config.BOT_NAME}**

🚀 **Professional Video Merging Solution**

This bot uses advanced FFmpeg technology to merge multiple videos with high-quality output. Perfect for combining episodes, clips, or any video content.

🌟 **Key Features:**
• Lightning-fast processing
• High-quality output preservation
• Multi-format support  
• Smart compression algorithms
• Professional user interface

📈 **Version:** 2.0 Professional
🛠 **Engine:** FFmpeg + Python
💻 **Developer:** {config.DEVELOPER}

💝 **Thank you for using our bot!**
"""
