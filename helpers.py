# helpers.py - Helper Functions for Force Subscribe and Auth
from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, ChannelPrivate
from config import config
from database import db
import logging

logger = logging.getLogger(__name__)

async def is_user_member(client: Client, user_id: int, channel_id: str):
    """Check if user is member of force subscribe channel"""
    try:
        if not config.FORCE_SUB_CHANNEL:
            return True
            
        member = await client.get_chat_member(channel_id, user_id)
        return member.status not in ["left", "kicked"]
    except (UserNotParticipant, ChannelPrivate):
        return False
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return True  # Allow access on error

async def force_subscribe_check(client: Client, message):
    """Force subscribe middleware"""
    try:
        if not config.FORCE_SUB_CHANNEL:
            return True
            
        user_id = message.from_user.id
        
        # Skip check for admins
        if user_id in config.ADMINS:
            return True
            
        # Check if user is member
        is_member = await is_user_member(client, user_id, config.FORCE_SUB_CHANNEL)
        
        if not is_member:
            # Get channel info for invite link
            try:
                chat = await client.get_chat(config.FORCE_SUB_CHANNEL)
                invite_link = chat.invite_link or f"https://t.me/{chat.username}"
                channel_title = chat.title
            except Exception:
                invite_link = f"https://t.me/{config.FORCE_SUB_CHANNEL.replace('@', '')}"
                channel_title = "Our Channel"
            
            # Create force subscribe message
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"📢 Join {channel_title}", url=invite_link)],
                [InlineKeyboardButton("🔄 Check Again", callback_data="check_subscription")]
            ])
            
            force_text = f"""
🔒 **Access Denied!**

To use this bot, you must join our channel first.

📢 **Channel:** {channel_title}
👆 **Click the button above to join**

After joining, click "🔄 Check Again" to continue.
"""
            
            await message.reply_text(
                force_text,
                reply_markup=keyboard,
                quote=True
            )
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error in force subscribe check: {e}")
        return True  # Allow access on error

async def is_authorized_user(user_id: int, chat_id: int = None):
    """Check if user is authorized (admin or in authorized chat)"""
    try:
        # Check if user is admin/owner
        if user_id in config.ADMINS or user_id == config.OWNER_ID:
            return True
            
        # Check if it's a private chat with registered user
        if chat_id == user_id:  # Private chat
            user = await db.get_user(user_id)
            return user is not None and not user.get("is_banned", False)
            
        # Check if it's an authorized chat/group
        if chat_id:
            return await db.is_authorized_chat(chat_id)
            
        return False
        
    except Exception as e:
        logger.error(f"Error checking authorization: {e}")
        return False

def get_main_keyboard():
    """Get main menu keyboard"""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📚 Help", callback_data="help_menu"),
            InlineKeyboardButton("ℹ️ About", callback_data="about_menu")
        ],
        [
            InlineKeyboardButton("🏠 Home", callback_data="home_menu"),
            InlineKeyboardButton("🔙 Back", callback_data="back_to_start")
        ],
        [
            InlineKeyboardButton("📢 Updates", url=f"https://t.me/{config.UPDATE_CHANNEL}") if config.UPDATE_CHANNEL else None,
            InlineKeyboardButton("💬 Support", url=f"https://t.me/{config.SUPPORT_GROUP}") if config.SUPPORT_GROUP else None
        ],
        [
            InlineKeyboardButton(f"👨‍💻 Developer", url=f"tg://user?id={config.OWNER_ID}")
        ]
    ])
    
    # Remove None buttons
    keyboard.inline_keyboard = [[btn for btn in row if btn] for row in keyboard.inline_keyboard]
    keyboard.inline_keyboard = [row for row in keyboard.inline_keyboard if row]
    
    return keyboard

def get_video_queue_keyboard(queue_count: int = 0):
    """Get keyboard for video queue management"""
    if queue_count == 0:
        return None
    elif queue_count == 1:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Add More Videos", callback_data="add_more"),
                InlineKeyboardButton("🗑 Clear All", callback_data="clear_queue")
            ]
        ])
    else:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎬 Merge Now", callback_data="start_merge"),
                InlineKeyboardButton("🗑 Clear All", callback_data="clear_queue")
            ],
            [
                InlineKeyboardButton("➕ Add More Videos", callback_data="add_more")
            ]
        ])

def get_upload_choice_keyboard():
    """Get upload destination choice keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload to Telegram", callback_data="upload_tg")],
        [InlineKeyboardButton("🔗 Upload to GoFile.io", callback_data="upload_gofile")]
    ])

def get_admin_keyboard():
    """Get admin panel keyboard"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"),
            InlineKeyboardButton("👥 User Management", callback_data="user_management")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu"),
            InlineKeyboardButton("🔧 Settings", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton("💬 Authorized Chats", callback_data="auth_chats"),
            InlineKeyboardButton("📋 Logs", callback_data="admin_logs")
        ]
    ])

async def send_log_message(client: Client, log_type: str, message: str, user_id: int = None):
    """Send log message to appropriate channel"""
    try:
        if log_type == "new_user" and config.LOG_CHANNEL:
            await client.send_message(
                config.LOG_CHANNEL,
                f"👤 **New User Joined**\n\n"
                f"**User ID:** `{user_id}`\n"
                f"**Profile:** [View Profile](tg://user?id={user_id})\n"
                f"**Time:** `{message}`"
            )
        elif log_type == "merge_activity" and config.MERGE_LOG_CHANNEL:
            await client.send_message(
                config.MERGE_LOG_CHANNEL,
                message
            )
    except Exception as e:
        logger.error(f"Error sending log message: {e}")

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

def get_help_text():
    """Get help text"""
    return """
📚 **How to Use Video Merger Bot**

🎬 **Basic Usage:**
1. Send me videos or direct download links
2. I'll add them to your queue
3. When you have 2+ videos, click "🎬 Merge Now"
4. Choose upload destination (Telegram or GoFile)
5. Get your merged video!

📝 **Supported Formats:**
• Video files uploaded to Telegram
• Direct download links (HTTP/HTTPS)
• Multiple video formats (MP4, MKV, AVI, etc.)

⚡ **Features:**
• Ultra-fast merging for compatible videos
• Automatic quality standardization when needed
• Preserve all audio tracks and subtitles
• Professional progress tracking
• Multiple upload options

💡 **Tips:**
• Videos with same resolution/codec merge faster
• Large files may take longer to process
• Use /cancel to clear your queue anytime

❓ **Need Help?** Contact our support team!
"""

def get_about_text():
    """Get about text"""
    return f"""
ℹ️ **About Video Merger Bot**

🚀 **Advanced Video Merging Solution**

This bot uses cutting-edge FFmpeg technology to merge multiple videos with professional quality output. Whether you're combining episodes, clips, or any video content, our bot ensures the best possible results.

🌟 **Key Features:**
• Lightning-fast processing
• High-quality output preservation  
• Multi-format support
• Smart compression algorithms
• Professional user interface

📈 **Version:** 2.0 Professional
🛠 **Engine:** FFmpeg + Python
💻 **Developer:** {config.DEVELOPER}

🔗 **Links:**
• Updates: @{config.UPDATE_CHANNEL}
• Support: @{config.SUPPORT_GROUP}

💝 **Thank you for using our bot!**
"""
