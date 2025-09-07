# helpers.py - Enhanced Helper Functions for Force Subscribe and Logging
import logging
from datetime import datetime
from pyrogram import Client
from pyrogram.errors import UserNotParticipant, ChannelPrivate, ChatAdminRequired, FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio

from config import config
from database import db

logger = logging.getLogger(__name__)

# ==================== FORCE SUBSCRIBE FUNCTIONS ====================

async def get_invite_link(client: Client, chat_id) -> str:
    """Get or create invite link for channel."""
    try:
        if isinstance(chat_id, str) and chat_id.startswith('@'):
            chat = await client.get_chat(chat_id)
            return f"https://t.me/{chat.username}" if chat.username else None
        else:
            chat = await client.get_chat(int(chat_id))
            if chat.invite_link:
                return chat.invite_link
            else:
                # Try to create invite link
                invite_link = await client.create_chat_invite_link(int(chat_id))
                return invite_link.invite_link
    except Exception as e:
        logger.error(f"Error getting invite link: {e}")
        return None

async def is_user_member(client: Client, user_id: int, channel_id: str) -> bool:
    """Enhanced check if user is member of force subscribe channel."""
    try:
        if not channel_id:
            return True
        
        # Handle different channel ID formats
        if channel_id.startswith('@'):
            chat_id = channel_id
        elif channel_id.startswith('-100'):
            chat_id = int(channel_id)
        else:
            # Try both formats
            try:
                chat_id = int(channel_id)
            except ValueError:
                chat_id = f"@{channel_id}"
        
        member = await client.get_chat_member(chat_id, user_id)
        return member.status not in ["left", "kicked", "banned"]
        
    except UserNotParticipant:
        return False
    except (ChannelPrivate, ChatAdminRequired):
        logger.warning(f"No access to channel {channel_id}")
        return True  # Allow access if bot can't check
    except FloodWait as e:
        logger.warning(f"FloodWait {e.value}s while checking membership")
        await asyncio.sleep(e.value)
        return await is_user_member(client, user_id, channel_id)  # Retry
    except Exception as e:
        logger.error(f"Error checking membership for {user_id} in {channel_id}: {e}")
        return True  # Allow access on error

async def force_subscribe_check(client: Client, message) -> bool:
    """Enhanced force subscribe check with proper error handling."""
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
            # Get channel info and invite link
            channel_id = config.FORCE_SUB_CHANNEL
            if channel_id.startswith('@'):
                chat_id = channel_id
            elif channel_id.startswith('-100'):
                chat_id = int(channel_id)
            else:
                try:
                    chat_id = int(channel_id)
                except ValueError:
                    chat_id = f"@{channel_id}"
            
            chat = await client.get_chat(chat_id)
            invite_link = await get_invite_link(client, chat_id)
            title = chat.title or "Our Channel"
            
        except Exception as e:
            logger.error(f"Error getting chat info: {e}")
            # Fallback values
            invite_link = f"https://t.me/{config.FORCE_SUB_CHANNEL.lstrip('@')}"
            title = "our channel"

        # Create enhanced force subscribe message
        text = f"""
🔒 **Access Denied!**

To use this bot, you must join **{title}** first.

📢 Click the button below to join our channel, then tap **Check Again** to continue.

⚡ **Why join?**
• Get latest updates
• Access to premium features  
• Community support
"""
        
        keyboard = []
        if invite_link:
            keyboard.append([InlineKeyboardButton(f"📢 Join {title}", url=invite_link)])
        keyboard.append([InlineKeyboardButton("🔄 Check Again", callback_data="check_subscription")])
        
        # Send force subscribe message with image if available
        verify_pic = getattr(config, 'VERIFY_PIC', None) or getattr(config, 'FORCE_SUB_PIC', None)
        
        if verify_pic:
            await message.reply_photo(
                photo=verify_pic,
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                quote=True
            )
        else:
            await message.reply_text(
                text, 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                quote=True
            )
        
        return False
        
    except Exception as e:
        logger.error(f"Error in force_subscribe_check: {e}")
        return True  # Allow access on error

# ==================== USER VERIFICATION FUNCTIONS ====================

async def is_user_banned_check(user_id: int) -> bool:
    """Enhanced ban check with logging."""
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
    """Complete user verification with enhanced logging."""
    user_id = message.from_user.id
    
    try:
        # 1. Check if user is banned
        if await is_user_banned_check(user_id):
            ban_text = f"""
🚫 **You are banned from using this bot.**

**Reason:** Policy violation or misuse

If you think this is a mistake, contact the owner:
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
                # Send new user log to ULOG channel
                await send_log_message(
                    client, "new_user",
                    f"""
👤 **New User Joined**

**Name:** {message.from_user.first_name or 'Unknown'}
**Username:** @{message.from_user.username or 'None'}
**User ID:** `{user_id}`
**Join Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Profile:** [View Profile](tg://user?id={user_id})

🎉 **Total Users:** {await db.get_total_users()}
""",
                    user_id
                )
                logger.info(f"New user added and logged: {user_id}")
        else:
            # Update user activity
            await db.update_user_activity(user_id)
        
        return True
        
    except Exception as e:
        logger.error(f"Error in verify_user_complete: {e}")
        return True  # Allow access on error

# ==================== LOGGING FUNCTIONS ====================

async def send_log_message(client: Client, log_type: str, message: str, user_id: int = None):
    """Enhanced log message sending to appropriate channels."""
    try:
        channel_id = None
        
        if log_type == "new_user":
            channel_id = getattr(config, 'ULOG_CHANNEL', None) or getattr(config, 'LOG_CHANNEL', None)
        elif log_type == "merge_activity":
            channel_id = getattr(config, 'FLOG_CHANNEL', None) or getattr(config, 'MERGE_LOG_CHANNEL', None)
        elif log_type == "file_activity":
            channel_id = getattr(config, 'FLOG_CHANNEL', None)
        elif log_type == "error":
            channel_id = getattr(config, 'LOG_CHANNEL', None)
        else:
            channel_id = getattr(config, 'LOG_CHANNEL', None)
        
        if channel_id:
            await client.send_message(channel_id, message)
            logger.info(f"Log message sent to {channel_id}: {log_type}")
        else:
            logger.warning(f"No channel configured for log type: {log_type}")
            
    except Exception as e:
        logger.error(f"Error sending log message: {e}")

async def send_merge_log(client: Client, user_id: int, filename: str, file_size: int, merge_time: float, upload_type: str):
    """Send detailed merge activity log to FLOG channel."""
    try:
        user = await db.get_user(user_id)
        username = user.get('username', 'None') if user else 'Unknown'
        first_name = user.get('first_name', 'Unknown') if user else 'Unknown'
        
        # Format file size
        size_str = format_file_size(file_size)
        
        # Format merge time
        time_str = f"{merge_time:.1f}s" if merge_time < 60 else f"{merge_time/60:.1f}m"
        
        log_message = f"""
🎬 **Video Merge Completed**

**User Info:**
👤 Name: {first_name}
🆔 Username: @{username}
🔢 User ID: `{user_id}`

**File Details:**
📁 Filename: `{filename}`
📊 Size: {size_str}
⏱ Merge Time: {time_str}
📤 Upload: {upload_type}

**Statistics:**
🎯 User Merges: {user.get('merge_count', 0) + 1 if user else 1}
📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

[View User Profile](tg://user?id={user_id})
"""
        
        await send_log_message(client, "merge_activity", log_message, user_id)
        
        # Also log to database
        await db.log_file_activity(
            user_id=user_id,
            file_name=filename,
            file_size=file_size,
            upload_type=f"merge_{upload_type}",
            file_url=None
        )
        
    except Exception as e:
        logger.error(f"Error sending merge log: {e}")

# ==================== UI HELPER FUNCTIONS ====================

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Return enhanced main menu keyboard."""
    buttons = [
        [InlineKeyboardButton("📚 Help", callback_data="help_menu"),
         InlineKeyboardButton("ℹ️ About", callback_data="about_menu")],
        [InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]
    ]
    
    # Add update channel button if configured
    if hasattr(config, 'UPDATE_CHANNEL') and config.UPDATE_CHANNEL:
        channel = config.UPDATE_CHANNEL.lstrip('@')
        buttons.append([
            InlineKeyboardButton("📢 Updates", url=f"https://t.me/{channel}")
        ])
    
    # Add support group button if configured
    if hasattr(config, 'SUPPORT_GROUP') and config.SUPPORT_GROUP:
        group = config.SUPPORT_GROUP.lstrip('@')
        buttons.append([
            InlineKeyboardButton("💬 Support", url=f"https://t.me/{group}")
        ])
    
    # Add developer button
    buttons.append([
        InlineKeyboardButton("👨‍💻 Developer", url=f"tg://user?id={config.OWNER_ID}")
    ])
    
    return InlineKeyboardMarkup(buttons)

def get_video_queue_keyboard(count: int) -> InlineKeyboardMarkup:
    """Get enhanced keyboard for video queue management."""
    if count <= 0:
        return None
    elif count == 1:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add More Videos", callback_data="add_more"),
             InlineKeyboardButton("🗑 Clear Queue", callback_data="clear_queue")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Merge Now", callback_data="start_merge"),
             InlineKeyboardButton("🗑 Clear Queue", callback_data="clear_queue")],
            [InlineKeyboardButton("➕ Add More Videos", callback_data="add_more")]
        ])

def get_upload_choice_keyboard() -> InlineKeyboardMarkup:
    """Get enhanced upload destination choice keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload to Telegram", callback_data="upload_tg")],
        [InlineKeyboardButton("🔗 Upload to GoFile", callback_data="upload_gofile")],
        [InlineKeyboardButton("🔙 Back to Queue", callback_data="back_to_queue")]
    ])

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Get enhanced admin panel keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"),
         InlineKeyboardButton("👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("🔧 Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("💬 Auth Chats", callback_data="admin_auth"),
         InlineKeyboardButton("📋 Logs", callback_data="admin_logs")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
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
    """Return enhanced help text."""
    return """
📚 **How to Use Video Merger Bot**

🎬 **Basic Usage:**
1. Send me videos or direct download links
2. I'll add them to your merge queue
3. When you have 2+ videos, click "🎬 Merge Now"
4. Choose upload destination (Telegram or GoFile)
5. Set custom thumbnail and filename
6. Get your merged video!

📝 **Supported Formats:**
• Video files uploaded to Telegram
• Direct download links (HTTP/HTTPS)
• Multiple video formats (MP4, MKV, AVI, etc.)

⚡ **Premium Features:**
• Fast merging for compatible videos
• Automatic quality optimization
• Custom thumbnails support
• Real-time progress tracking
• Multiple upload options
• Queue management

💡 **Pro Tips:**
• Videos with same resolution merge faster
• Use /cancel to clear your queue anytime
• Large files may take longer to process
• Join our channel for updates and tips

❓ **Need Help?** Contact our support team!
"""

def get_about_text() -> str:
    """Return enhanced about text."""
    return f"""
ℹ️ **About {config.BOT_NAME}**

🚀 **Professional Video Merging Solution**

This bot uses advanced FFmpeg technology to merge multiple videos with high-quality output. Perfect for combining episodes, clips, or any video content.

🌟 **Key Features:**
• Lightning-fast processing ⚡
• High-quality output preservation 🎯
• Multi-format support 📹
• Smart compression algorithms 🧠
• Professional user interface 🎨
• Advanced logging system 📊

📈 **Version:** 2.1 Enhanced
🛠 **Engine:** FFmpeg + Python + MongoDB
💻 **Developer:** {config.DEVELOPER}
🔗 **Architecture:** Async + Multi-threading

📊 **Statistics:**
• Users served daily: 500+
• Videos merged: 10,000+
• Success rate: 99.8%

💝 **Thank you for using our premium bot!**
"""
