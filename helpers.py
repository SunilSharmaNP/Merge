# helpers.py - FIXED VERSION with Bulletproof Force Subscribe & Authorization

import os
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant, PeerIdInvalid, ChannelInvalid
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
        if isinstance(channel, int):
            # Convert to string if it's an integer ID
            channel = str(channel)

        member = await client.get_chat_member(channel, user_id)
        return member.status not in ["left", "kicked"]
    except (PeerIdInvalid, ChannelInvalid) as e:
        logger.error(f"Invalid FORCE_SUB_CHANNEL: {config.FORCE_SUB_CHANNEL}, Error: {e}")
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Force subscribe check error: {e}")
        return True

async def send_log_message(client: Client, message: str, log_type: str = "general"):
    """Send a log message to the configured log channel with improved error handling."""
    target = {
        "new_user": config.NEW_USER_LOG_CHANNEL,
        "merged_file": config.MERGED_FILE_LOG_CHANNEL
    }.get(log_type, config.LOG_CHANNEL)

    if not target:
        logger.debug(f"No log channel configured for {log_type}")
        return

    try:
        # Handle both integer IDs and string usernames
        if isinstance(target, int):
            target = str(target)
        elif isinstance(target, str):
            target = target.strip()
            
        # Validate target before sending
        if not target:
            logger.debug(f"Empty log channel for {log_type}")
            return
            
        # Try to get chat info first to validate
        try:
            await client.get_chat(target)
        except Exception as validation_error:
            logger.error(f"Cannot access log channel {target}: {validation_error}")
            return
            
        # Send the message
        await client.send_message(target, message)
        logger.debug(f"Log message sent to {target}")
        
    except Exception as e:
        logger.error(f"Invalid log channel: {target}, Error: {e}")
        # Disable this channel to avoid repeated errors
        if log_type == "new_user":
            config.NEW_USER_LOG_CHANNEL = None
        elif log_type == "merged_file": 
            config.MERGED_FILE_LOG_CHANNEL = None
        else:
            config.LOG_CHANNEL = None
        logger.warning(f"Disabled invalid log channel for {log_type}")

async def is_user_member(client: Client, user_id: int, chat_id: int) -> bool:
    """Check if user is member of a chat"""
    try:
        user = await client.get_chat_member(chat_id, user_id)
        return user.status not in ["left", "kicked"]
    except:
        return False

async def is_authorized_user(user_id: int) -> bool:
    """Check if user is authorized to use bot in private"""
    if user_id == config.OWNER_ID or user_id in config.ADMINS:
        return True
    return await db.is_user_authorized(user_id)

async def is_authorized_chat(chat_id: int) -> bool:
    """Check if chat is authorized for bot usage"""
    return chat_id in config.AUTHORIZED_CHATS

async def verify_user_complete(client: Client, message: Message) -> bool:
    """Complete user verification - BULLETPROOF VERSION"""
    user_id = message.from_user.id
    chat_type = message.chat.type

    # Check if user is banned
    if await db.is_user_banned(user_id):
        await message.reply_text(
            "🚫 **You are banned from using this bot!**\n\n"
            "If you think this is a mistake, please contact support.",
            quote=True
        )
        return False

    # Force subscribe check - BLOCKS UNTIL JOINED
    if not await force_subscribe_check(client, user_id):
        try:
            # Get channel info
            channel = config.FORCE_SUB_CHANNEL
            if isinstance(channel, int):
                channel = str(channel)

            chat_info = await client.get_chat(channel)

            # Get invite link
            try:
                invite_link = await client.export_chat_invite_link(chat_info.id)
            except:
                # If we can't export invite link, try to create a t.me link
                if chat_info.username:
                    invite_link = f"https://t.me/{chat_info.username}"
                else:
                    # For private channels, we need to use the ID
                    chat_id_str = str(chat_info.id)
                    if chat_id_str.startswith('-100'):
                        invite_link = f"https://t.me/c/{chat_id_str[4:]}"
                    else:
                        invite_link = f"https://t.me/c/{chat_id_str}"
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            chat_info = None
            invite_link = f"https://t.me/{config.FORCE_SUB_CHANNEL}"

        channel_name = chat_info.title if chat_info else "Our Channel"

        await message.reply_text(
            f"🔔 **You must join our channel to use this bot!**\n\n"
            f"📢 **Channel:** {channel_name}\n\n"
            f"👆 **Click the button below to join and then try again:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=invite_link)],
                [InlineKeyboardButton("🔄 I've Joined", callback_data="check_subscription")]
            ]),
            quote=True
        )
        return False

    # Private chat authorization check - ONLY AFTER FORCE SUBSCRIBE
    if chat_type == "private":
        # Owner and admins can always use in private
        if user_id == config.OWNER_ID or user_id in config.ADMINS:
            return True
            
        # For other users, check authorization
        if not await is_authorized_user(user_id):
            await message.reply_text(
                "🔒 **This bot only works in authorized groups!**\n\n"
                "Please join our authorized merging group to use this bot.\n"
                "Contact the owner for more information.",
                quote=True
            )
            return False

    # Group/Channel authorization check
    else:
        if not await is_authorized_chat(message.chat.id):
            await message.reply_text(
                "🔒 **This chat is not authorized!**\n\n"
                "Bot can only be used in authorized chats.\n"
                "Please contact admin for authorization."
            )
            return False

    return True

def get_main_keyboard():
    """Get main keyboard for start message"""
    """Get main keyboard for start message with URL validation"""
    keyboard = []
    # Row 1: Help and About
        InlineKeyboardButton("ℹ️ About", callback_data="about")
    ])
    # Row 2: Update Channel and Support Group
    # Row 2: Update Channel and Support Group (with URL validation)
    row2 = []
    
    # Validate UPDATE_CHANNEL URL
    if config.UPDATE_CHANNEL:
        row2.append(InlineKeyboardButton("📢 Updates", url=config.UPDATE_CHANNEL))
        update_url = str(config.UPDATE_CHANNEL).strip()
        if update_url.startswith('@'):
            update_url = f"https://t.me/{update_url[1:]}"
        elif not update_url.startswith('https://'):
            update_url = f"https://t.me/{update_url}"
            
        # Only add if it's a valid format
        if update_url.startswith('https://t.me/'):
            row2.append(InlineKeyboardButton("📢 Updates", url=update_url))
        else:
            logger.warning(f"Invalid UPDATE_CHANNEL URL: {config.UPDATE_CHANNEL}")
    
    # Validate SUPPORT_GROUP URL
    if config.SUPPORT_GROUP:
        row2.append(InlineKeyboardButton("💬 Support", url=config.SUPPORT_GROUP))
        support_url = str(config.SUPPORT_GROUP).strip()
        if support_url.startswith('@'):
            support_url = f"https://t.me/{support_url[1:]}"
        elif not support_url.startswith('https://'):
            support_url = f"https://t.me/{support_url}"
            
        # Only add if it's a valid format
        if support_url.startswith('https://t.me/'):
            row2.append(InlineKeyboardButton("💬 Support", url=support_url))
        else:
            logger.warning(f"Invalid SUPPORT_GROUP URL: {config.SUPPORT_GROUP}")
    
    if row2:
        keyboard.append(row2)
    # Row 3: Developer
    # Row 3: Developer (callback only, no URL)
    keyboard.append([
        InlineKeyboardButton("👨💻 Developer", callback_data="developer")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_video_queue_keyboard(video_count: int):
    """Get keyboard for video queue management"""
    keyboard = []

    if video_count == 1:
        # Only one video - show add more and clear options
        keyboard.append([
            InlineKeyboardButton("➕ Add More Videos", callback_data="add_more_videos"),
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
            InlineKeyboardButton("🔙 Back", callback_data="back_to_start")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)

def get_upload_choice_keyboard():
    """Get upload choice keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📤 Telegram", callback_data="upload_telegram"),
            InlineKeyboardButton("☁️ GoFile", callback_data="upload_gofile")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="back_to_start")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)

def get_help_text():
    """Get help text with bot name and developer info"""
    return config.HELP_TEXT

def get_about_text():
    """Get about text with dynamic info"""
    return config.ABOUT_TEXT.format(
        bot_name=config.BOT_NAME,
        developer=config.DEVELOPER,
        update_channel=config.UPDATE_CHANNEL or "Not Set",
        support_group=config.SUPPORT_GROUP or "Not Set"
    )

async def is_user_banned_check(user_id: int) -> bool:
    """Check if user is banned - wrapper function"""
    return await db.is_user_banned(user_id)

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"
