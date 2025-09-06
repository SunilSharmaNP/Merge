# bot.py - FIXED VERSION - All Issues Resolved
import os
import shutil
import asyncio
import logging
import math
import time
import string
import random
import aiofiles
import datetime
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.enums.parse_mode import ParseMode

from config import config
from database import db
from helpers import (
    force_subscribe_check,
    is_user_member,
    is_authorized_user,
    is_authorized_chat,
    send_log_message,
    get_main_keyboard,
    get_help_text,
    get_about_text,
    get_video_queue_keyboard,
    get_upload_choice_keyboard,
    get_admin_keyboard,
    verify_user_complete,
    is_user_banned_check,
    format_file_size
)

from downloader import download_from_url, download_from_tg
from merger import merge_videos
from uploader import GofileUploader, upload_to_telegram
from utils import cleanup_files, is_valid_url

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot
app = Client(
    "video_merger_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

# In-memory session state
user_data: dict[int, dict] = {}
broadcast_ids = {}

def clear_user_data(user_id: int):
    """Clear all session data for a user."""
    if user_id in user_data:
        download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        cleanup_files(download_dir)
        thumb = user_data[user_id].get("custom_thumbnail")
        if thumb and os.path.exists(thumb):
            os.remove(thumb)
        user_data.pop(user_id, None)

# State filters
async def is_waiting_for_broadcast_filter(_, __, message: Message):
    if not message.from_user:
        return False
    return user_data.get(message.from_user.id, {}).get("state") == "broadcast"

async def is_waiting_for_thumbnail_filter(_, __, message: Message):
    if not message.from_user:
        return False
    return user_data.get(message.from_user.id, {}).get("state") == "waiting_for_thumbnail"

async def is_waiting_for_filename_filter(_, __, message: Message):
    if not message.from_user:
        return False
    return user_data.get(message.from_user.id, {}).get("state") == "waiting_for_filename"

# Create filters
is_waiting_for_broadcast = filters.create(is_waiting_for_broadcast_filter)
is_waiting_for_thumbnail = filters.create(is_waiting_for_thumbnail_filter)
is_waiting_for_filename = filters.create(is_waiting_for_filename_filter)

# ===================== MAIN HANDLERS =====================

@app.on_message(filters.command("start") & (filters.private | filters.group))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or str(user_id)
    
    # Force subscribe check FIRST
    if not await force_subscribe_check(client, user_id):
        try:
            channel = config.FORCE_SUB_CHANNEL
            if isinstance(channel, int):
                channel = str(channel)
            
            chat_info = await client.get_chat(channel)
            
            # Get invite link
            try:
                invite_link = await client.export_chat_invite_link(chat_info.id)
            except:
                if chat_info.username:
                    invite_link = f"https://t.me/{chat_info.username}"
                else:
                    invite_link = f"https://t.me/c/{str(chat_info.id)[4:] if str(chat_info.id).startswith('-100') else chat_info.id}"
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            invite_link = f"https://t.me/{config.FORCE_SUB_CHANNEL}"

        await message.reply_text(
            "🔔 **Please join our channel first to use this bot!**\n\n"
            "After joining, click the 'I've Joined' button below.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=invite_link)],
                [InlineKeyboardButton("🔄 I've Joined", callback_data="check_subscription")]
            ]),
            quote=True
        )
        return

    # Add user to database and log
    await db.add_user(user_id, user_name, message.from_user.username)
    
    # Log new user ONLY if it's a new start
    if message.text == "/start":
        await send_log_message(
            client,
            f"👤 **New user started the bot:**\n"
            f"**Name:** {user_name}\n"
            f"**ID:** `{user_id}`\n"
            f"**Username:** @{message.from_user.username or 'None'}\n"
            f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            log_type="new_user"
        )

    # Show different messages based on chat type
    if message.chat.type == "private":
        if user_id != config.OWNER_ID and user_id not in config.ADMINS and not await is_authorized_user(user_id):
            text = (
                f"🎬 **Welcome to {config.BOT_NAME}!**\n\n"
                f"Hi {user_name}! 👋\n\n"
                f"🔒 **This bot only works in authorized groups!**\n\n"
                f"Please join our authorized merging group to use video merging features.\n"
                f"Contact the owner for group access.\n\n"
                f"**Developer:** {config.DEVELOPER}"
            )
        else:
            text = config.START_TEXT.format(
                bot_name=config.BOT_NAME,
                developer=config.DEVELOPER,
                user=user_name
            )
    else:
        if message.chat.id not in config.AUTHORIZED_CHATS:
            text = "🔒 **This group is not authorized!**\n\nPlease contact the owner for authorization."
        else:
            text = config.START_TEXT.format(
                bot_name=config.BOT_NAME,
                developer=config.DEVELOPER,
                user=user_name
            )

    # Send welcome message with picture if available
    if getattr(config, "START_PIC", None):
        await message.reply_photo(
            config.START_PIC,
            caption=text,
            reply_markup=get_main_keyboard(),
            quote=True
        )
    else:
        await message.reply_text(
            text,
            reply_markup=get_main_keyboard(),
            quote=True
        )

@app.on_message(filters.command("help") & (filters.private | filters.group))
async def help_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Force subscribe check
    if not await force_subscribe_check(client, user_id):
        await message.reply_text("🔔 Please join our channel first to use this bot!")
        return

    # Send help with picture and full keyboard
    if getattr(config, "START_PIC", None):
        await message.reply_photo(
            config.START_PIC,
            caption=get_help_text(),
            reply_markup=get_main_keyboard(),
            quote=True
        )
    else:
        await message.reply_text(
            get_help_text(),
            reply_markup=get_main_keyboard(),
            quote=True
        )

@app.on_message(filters.command("about") & (filters.private | filters.group))
async def about_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Force subscribe check
    if not await force_subscribe_check(client, user_id):
        await message.reply_text("🔔 Please join our channel first to use this bot!")
        return

    # Send about with picture and full keyboard
    if getattr(config, "START_PIC", None):
        await message.reply_photo(
            config.START_PIC,
            caption=get_about_text(),
            reply_markup=get_main_keyboard(),
            quote=True
        )
    else:
        await message.reply_text(
            get_about_text(),
            reply_markup=get_main_keyboard(),
            quote=True
        )

@app.on_message(filters.command("merge") & (filters.private | filters.group))
async def merge_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Force subscribe check
    if not await force_subscribe_check(client, user_id):
        await message.reply_text("🔔 Please join our channel first!")
        return

    # Check authorization for merging
    if message.chat.type == "private":
        if user_id != config.OWNER_ID and user_id not in config.ADMINS and not await is_authorized_user(user_id):
            await message.reply_text(
                "🔒 **Merging only works in authorized groups!**\n\n"
                "Please join our authorized merging group to use this feature.\n"
                "Contact the owner for group access.",
                quote=True
            )
            return
    else:
        if message.chat.id not in config.AUTHORIZED_CHATS:
            await message.reply_text(
                "🔒 **This group is not authorized for merging!**\n\n"
                "Contact the owner to authorize this group.",
                quote=True
            )
            return

    # Initialize user session
    if user_id not in user_data:
        user_data[user_id] = {"videos": [], "state": None}
    
    user_data[user_id]["videos"] = []
    user_data[user_id]["state"] = "waiting_for_videos"
    
    await message.reply_text(
        "🎬 **Ready to merge videos!**\n\n"
        "📤 **Send me:**\n"
        "• Video files (up to 2GB each)\n"
        "• Video URLs (YouTube, etc.)\n"
        "• Multiple videos to merge\n\n"
        "🔢 **I'll show merge option after you add 2+ videos**",
        quote=True
    )

@app.on_message(filters.command("cancel") & (filters.private | filters.group))
async def cancel_handler(client: Client, message: Message):
    user_id = message.from_user.id
    clear_user_data(user_id)
    await message.reply_text(
        "❌ **Operation cancelled!**\n\n"
        "All videos cleared from queue.",
        reply_markup=get_main_keyboard(),
        quote=True
    )

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in config.ADMINS and user_id != config.OWNER_ID:
        return

    stats = await db.get_bot_stats()
    text = f"""📊 **Bot Statistics**

👥 **Total Users:** `{stats.get('total_users', 0)}`
🎬 **Total Merges:** `{stats.get('total_merges', 0)}`
📈 **Today's Merges:** `{stats.get('today_merges', 0)}`
🕐 **Active Users (24h):** `{stats.get('active_users_24h', 0)}`
🤖 **Bot Status:** Active ✅
💾 **Database Status:** {'Connected ✅' if db.connected else 'Disconnected ❌'}"""

    await message.reply_text(text, quote=True)

# Video and URL handlers
@app.on_message((filters.video | filters.document) & (filters.private | filters.group))
async def video_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Force subscribe check
    if not await force_subscribe_check(client, user_id):
        await message.reply_text("🔔 Please join our channel first!")
        return

    # Check authorization
    if message.chat.type == "private":
        if user_id != config.OWNER_ID and user_id not in config.ADMINS and not await is_authorized_user(user_id):
            await message.reply_text(
                "🔒 **Video merging only works in authorized groups!**\n\n"
                "Please join our authorized merging group.\n"
                "Contact the owner for access.",
                quote=True
            )
            return
    else:
        if message.chat.id not in config.AUTHORIZED_CHATS:
            await message.reply_text(
                "🔒 **This group is not authorized!**\n\n"
                "Contact owner for authorization.",
                quote=True
            )
            return

    # Initialize user session if needed
    if user_id not in user_data:
        user_data[user_id] = {"videos": [], "state": None}

    file_info = message.video or message.document
    if not file_info:
        return

    # Check file size
    if file_info.file_size > config.MAX_FILE_SIZE:
        await message.reply_text(
            f"❌ **File too large!**\n\n"
            f"Maximum size: {format_file_size(config.MAX_FILE_SIZE)}\n"
            f"Your file: {format_file_size(file_info.file_size)}",
            quote=True
        )
        return

    # Add to queue
    video_info = {
        "type": "telegram",
        "file_id": file_info.file_id,
        "file_name": getattr(file_info, 'file_name', f"video_{len(user_data[user_id]['videos']) + 1}.mp4"),
        "file_size": file_info.file_size,
        "duration": getattr(file_info, 'duration', 0)
    }
    
    user_data[user_id]["videos"].append(video_info)
    video_count = len(user_data[user_id]["videos"])
    
    await message.reply_text(
        f"✅ **Video {video_count} added to queue!**\n\n"
        f"📁 **File:** `{video_info['file_name']}`\n"
        f"📊 **Size:** `{format_file_size(video_info['file_size'])}`\n"
        f"🎬 **Videos in queue:** `{video_count}`",
        reply_markup=get_video_queue_keyboard(video_count),
        quote=True
    )

@app.on_message(filters.text & (filters.private | filters.group))
async def text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Skip commands
    if text.startswith('/'):
        return
    
    # Force subscribe check
    if not await force_subscribe_check(client, user_id):
        await message.reply_text("🔔 Please join our channel first!")
        return

    # Handle different states
    if user_id in user_data:
        state = user_data[user_id].get("state")
        
        if state == "broadcast" and (user_id == config.OWNER_ID or user_id in config.ADMINS):
            await handle_broadcast(client, message)
            return
        elif state == "waiting_for_filename":
            await handle_filename_input(client, message)
            return

    # Check if it's a URL
    if is_valid_url(text):
        await handle_url(client, message)
    else:
        # For non-URL text in authorized chats, show help
        if message.chat.type == "private":
            if user_id == config.OWNER_ID or user_id in config.ADMINS or await is_authorized_user(user_id):
                await message.reply_text(
                    "💡 **Send me:**\n"
                    "• Video files\n" 
                    "• Video URLs\n"
                    "• Use /merge to start\n"
                    "• Use /help for more info",
                    quote=True
                )
        elif message.chat.id in config.AUTHORIZED_CHATS:
            await message.reply_text(
                "💡 **Send me:**\n"
                "• Video files\n"
                "• Video URLs\n" 
                "• Use /merge to start",
                quote=True
            )

async def handle_url(client: Client, message: Message):
    user_id = message.from_user.id
    url = message.text.strip()
    
    # Check authorization
    if message.chat.type == "private":
        if user_id != config.OWNER_ID and user_id not in config.ADMINS and not await is_authorized_user(user_id):
            await message.reply_text(
                "🔒 **Video merging only works in authorized groups!**\n\n"
                "Please join our authorized merging group.\n"
                "Contact the owner for access.",
                quote=True
            )
            return
    else:
        if message.chat.id not in config.AUTHORIZED_CHATS:
            await message.reply_text(
                "🔒 **This group is not authorized!**\n\n"
                "Contact owner for authorization.",
                quote=True
            )
            return

    # Initialize user session if needed
    if user_id not in user_data:
        user_data[user_id] = {"videos": [], "state": None}

    # Add URL to queue
    video_info = {
        "type": "url",
        "url": url,
        "file_name": f"video_{len(user_data[user_id]['videos']) + 1}.mp4"
    }
    
    user_data[user_id]["videos"].append(video_info)
    video_count = len(user_data[user_id]["videos"])
    
    await message.reply_text(
        f"✅ **URL {video_count} added to queue!**\n\n"
        f"🔗 **URL:** `{url[:50]}...`\n"
        f"🎬 **Videos in queue:** `{video_count}`",
        reply_markup=get_video_queue_keyboard(video_count),
        quote=True
    )

# ===================== CALLBACK HANDLERS =====================

@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    try:
        if data == "check_subscription":
            if await force_subscribe_check(client, user_id):
                await callback_query.edit_message_text(
                    "✅ **Subscription verified!**\n\n"
                    "Welcome to the bot! Use /start to begin.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 Start Bot", callback_data="back_to_start")]
                    ])
                )
            else:
                await callback_query.answer("❌ Please join the channel first!", show_alert=True)
        
        elif data == "back_to_start":
            user_name = callback_query.from_user.first_name or str(user_id)
            text = config.START_TEXT.format(
                bot_name=config.BOT_NAME,
                developer=config.DEVELOPER,
                user=user_name
            )
            
            if getattr(config, "START_PIC", None):
                await callback_query.edit_message_media(
                    media={"type": "photo", "media": config.START_PIC, "caption": text},
                    reply_markup=get_main_keyboard()
                )
            else:
                await callback_query.edit_message_text(
                    text,
                    reply_markup=get_main_keyboard()
                )
        
        elif data == "help":
            if getattr(config, "START_PIC", None):
                await callback_query.edit_message_media(
                    media={"type": "photo", "media": config.START_PIC, "caption": get_help_text()},
                    reply_markup=get_main_keyboard()
                )
            else:
                await callback_query.edit_message_text(
                    get_help_text(),
                    reply_markup=get_main_keyboard()
                )
        
        elif data == "about":
            if getattr(config, "START_PIC", None):
                await callback_query.edit_message_media(
                    media={"type": "photo", "media": config.START_PIC, "caption": get_about_text()},
                    reply_markup=get_main_keyboard()
                )
            else:
                await callback_query.edit_message_text(
                    get_about_text(),
                    reply_markup=get_main_keyboard()
                )
        
        elif data == "developer":
            await callback_query.answer(
                f"👨‍💻 Developer: {config.DEVELOPER}\n"
                "Thanks for using our bot! ❤️",
                show_alert=True
            )
        
        elif data == "merge_now":
            await handle_merge_now(client, callback_query)
        
        elif data == "add_more_videos":
            await callback_query.edit_message_text(
                "📤 **Send more videos or URLs to add to your queue!**\n\n"
                "• Video files (up to 2GB each)\n"
                "• Video URLs\n"
                "• Use /cancel to clear queue",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]
                ])
            )
        
        elif data == "clear_all_videos":
            clear_user_data(user_id)
            await callback_query.edit_message_text(
                "🗑️ **All videos cleared from queue!**\n\n"
                "Send new videos to start over.",
                reply_markup=get_main_keyboard()
            )
        
        elif data.startswith("upload_"):
            upload_type = data.split("_")[1]
            await handle_upload_choice(client, callback_query, upload_type)
        
        # Admin callbacks
        elif data.startswith("admin_"):
            if user_id == config.OWNER_ID or user_id in config.ADMINS:
                await handle_admin_callbacks(client, callback_query)
        
        else:
            await callback_query.answer("Unknown action!")
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await callback_query.answer("An error occurred!")

async def handle_merge_now(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if user_id not in user_data or not user_data[user_id].get("videos"):
        await callback_query.edit_message_text("❌ No videos in queue!")
        return
    
    videos = user_data[user_id]["videos"]
    if len(videos) < 2:
        await callback_query.edit_message_text("❌ Need at least 2 videos to merge!")
        return
    
    # Start merging process
    await callback_query.edit_message_text(
        f"🎬 **Starting merge process...**\n\n"
        f"📁 **Videos to merge:** {len(videos)}\n"
        f"⏳ **Please wait...**"
    )
    
    try:
        # Use the existing merge_videos function
        result = await merge_videos(
            videos,
            user_id,
            callback_query.message,
            callback_query.from_user.first_name or str(user_id)
        )
        
        if result:
            # Show upload options
            await callback_query.edit_message_text(
                "✅ **Merge completed successfully!**\n\n"
                "📤 **Choose upload method:**",
                reply_markup=get_upload_choice_keyboard()
            )
        else:
            await callback_query.edit_message_text(
                "❌ **Merge failed!**\n\n"
                "Please try again or contact support.",
                reply_markup=get_main_keyboard()
            )
    
    except Exception as e:
        logger.error(f"Merge error: {e}")
        await callback_query.edit_message_text(
            "❌ **Merge failed!**\n\n"
            f"Error: {str(e)}",
            reply_markup=get_main_keyboard()
        )

async def handle_upload_choice(client: Client, callback_query: CallbackQuery, upload_type: str):
    user_id = callback_query.from_user.id
    
    # Check if merged file exists
    merged_file = user_data[user_id].get("merged_file")
    if not merged_file or not os.path.exists(merged_file):
        await callback_query.edit_message_text("❌ No merged file found!")
        return
    
    if upload_type == "telegram":
        await upload_to_telegram(
            client, 
            merged_file, 
            callback_query.message,
            user_data[user_id].get("custom_thumbnail")
        )
    elif upload_type == "gofile":
        uploader = GofileUploader()
        try:
            result = await uploader.upload_file(merged_file, callback_query.message)
            if result:
                await callback_query.edit_message_text(
                    f"✅ **Upload completed!**\n\n"
                    f"🔗 **Download Link:** {result}",
                    reply_markup=get_main_keyboard()
                )
        finally:
            await uploader.close()

async def handle_broadcast(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_data or user_data[user_id].get("state") != "broadcast":
        return
    
    users = await db.get_all_users()
    if not users:
        await message.reply_text("❌ No users found to broadcast!")
        return
    
    # Start broadcast
    user_data[user_id]["state"] = None
    
    broadcast_msg = await message.reply_text(
        f"📢 **Starting broadcast to {len(users)} users...**\n\n"
        f"✅ Success: 0\n"
        f"❌ Failed: 0\n"
        f"⏳ Progress: 0%"
    )
    
    success = failed = 0
    
    for i, user in enumerate(users):
        try:
            await client.send_message(user, message.text)
            success += 1
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed for {user}: {e}")
        
        # Update progress every 10 users
        if (i + 1) % 10 == 0:
            progress = ((i + 1) / len(users)) * 100
            await broadcast_msg.edit_text(
                f"📢 **Broadcasting...**\n\n"
                f"✅ Success: {success}\n"
                f"❌ Failed: {failed}\n"
                f"⏳ Progress: {progress:.1f}%"
            )
    
    # Final result
    await broadcast_msg.edit_text(
        f"📢 **Broadcast completed!**\n\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"📊 Total: {len(users)}"
    )
    
    # Log broadcast
    await db.log_broadcast(str(message.id), success, failed, len(users))

async def handle_filename_input(client: Client, message: Message):
    user_id = message.from_user.id
    filename = message.text.strip()
    
    if user_id in user_data:
        user_data[user_id]["custom_filename"] = filename
        user_data[user_id]["state"] = None
        
        await message.reply_text(
            f"✅ **Custom filename set:**\n\n"
            f"📁 **Filename:** `{filename}`\n\n"
            "Now send videos to merge!",
            reply_markup=get_main_keyboard(),
            quote=True
        )

async def handle_admin_callbacks(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "admin_stats":
        stats = await db.get_bot_stats()
        text = f"""📊 **Admin Statistics**

👥 **Total Users:** `{stats.get('total_users', 0)}`
🚫 **Banned Users:** `{stats.get('banned_users', 0)}`
✅ **Authorized Users:** `{stats.get('authorized_users', 0)}`
🎬 **Total Merges:** `{stats.get('total_merges', 0)}`
📈 **Today's Merges:** `{stats.get('today_merges', 0)}`
🕐 **Active Users (24h):** `{stats.get('active_users_24h', 0)}`
📅 **Bot Started:** `{stats.get('bot_start_date', 'Unknown')}`

🤖 **Status:** Active ✅
💾 **Database:** {'Connected ✅' if db.connected else 'Disconnected ❌'}"""
        
        await callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
            ])
        )
    
    elif data == "admin_broadcast":
        user_data[user_id] = {"state": "broadcast"}
        await callback_query.edit_message_text(
            "📢 **Broadcast Message**\n\n"
            "Send me the message you want to broadcast to all users:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="back_to_start")]
            ])
        )

# ===================== STARTUP =====================

async def main():
    """Start the bot"""
    # Connect to database
    await db.connect()
    
    # Start bot
    await app.start()
    logger.info(f"Bot started successfully! (@{(await app.get_me()).username})")
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
