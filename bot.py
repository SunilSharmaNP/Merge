# bot.py - COMPLETE FIXED VERSION - All Issues Resolved

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

# Define state-based filters
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

# Create filters using the async functions
is_waiting_for_broadcast = filters.create(is_waiting_for_broadcast_filter)
is_waiting_for_thumbnail = filters.create(is_waiting_for_thumbnail_filter)
is_waiting_for_filename = filters.create(is_waiting_for_filename_filter)

# ===================== MAIN HANDLERS =====================

@app.on_message(filters.command("start") & (filters.private | filters.group))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

    # Force subscribe check first - BLOCKS UNTIL JOINED
    if not await force_subscribe_check(client, user_id):
        try:
            channel = config.FORCE_SUB_CHANNEL
            if isinstance(channel, int):
                channel = str(channel)

            chat_info = await client.get_chat(channel)

            # Get invite link with better error handling
            invite_link = None
            try:
                invite_link = await client.export_chat_invite_link(chat_info.id)
                logger.info(f"Generated invite link: {invite_link}")
            except Exception as e:
                logger.warning(f"Could not export invite link: {e}")
                
                # Fallback to public link generation
                if chat_info.username:
                    # Clean username (remove @ if present)
                    username = chat_info.username.lstrip('@')
                    invite_link = f"https://t.me/{username}"
                else:
                    # For private channels, try alternative format
                    chat_id_str = str(chat_info.id)
                    if chat_id_str.startswith('-100'):
                        invite_link = f"https://t.me/c/{chat_id_str[4:]}/1"
                    else:
                        invite_link = f"https://t.me/c/{chat_id_str.lstrip('-')}/1"
                        
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            # Last fallback - try to construct from config
            channel_ref = str(config.FORCE_SUB_CHANNEL)
            if channel_ref.startswith('@'):
                invite_link = f"https://t.me/{channel_ref[1:]}"
            elif channel_ref.startswith('https://'):
                invite_link = channel_ref
            else:
                invite_link = f"https://t.me/{channel_ref}"
                
        # Validate the invite link before using
        if not invite_link or not invite_link.startswith('https://t.me/'):
            logger.error(f"Invalid invite link generated: {invite_link}")
            invite_link = "https://t.me/telegram"  # Default fallback

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

    # Now process the start command
    user_name = message.from_user.first_name or str(user_id)
    await db.add_user(user_id, user_name, message.from_user.username)
    # Send log message with error handling
    try:
        await send_log_message(
            client,
            f"👤 New user started the bot: {user_name} (`{user_id}`)",
            log_type="new_user"
        )
    except Exception as e:
        logger.warning(f"Could not send new user log: {e}")

    # Show different messages based on chat type and authorization
    if message.chat.type == "private":
        if user_id != config.OWNER_ID and user_id not in config.ADMINS:
            text = (
                f"🎬 **Welcome to {config.BOT_NAME}!**\n\n"
                f"Hi {user_name}! 👋\n\n"
                f"This bot only works in authorized groups. "
                f"Please join our authorized merging group to use this bot.\n\n"
                f"**Developer:** {config.DEVELOPER}"
            )
        else:
            try:
                text = config.START_TEXT.format(
                    bot_name=config.BOT_NAME,
                    developer=config.DEVELOPER,
                    user=user_name
                )
            except KeyError as e:
                logger.error(f"KeyError in START_TEXT: {e}")
                text = (
                    f"🎬 **Welcome to {config.BOT_NAME}!**\n\n"
                    f"Hi {user_name}! 👋\n\n"
                    f"I can help you merge multiple videos into one.\n\n"
                    f"**Developer:** {config.DEVELOPER}"
                )
    else:
        if message.chat.id not in config.AUTHORIZED_CHATS:
            text = "🔒 **This group is not authorized!**\n\nPlease contact the owner for authorization."
        else:
            try:
                text = config.START_TEXT.format(
                    bot_name=config.BOT_NAME,
                    developer=config.DEVELOPER,
                    user=user_name
                )
            except KeyError as e:
                logger.error(f"KeyError in START_TEXT: {e}")
                text = (
                    f"🎬 **Welcome to {config.BOT_NAME}!**\n\n"
                    f"Hi {user_name}! 👋\n\n"
                    f"I can help you merge multiple videos into one.\n\n"
                    f"**Developer:** {config.DEVELOPER}"
                )

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
    if not await verify_user_complete(client, message):
        return

    await message.reply_text(
        get_help_text(),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]),
        quote=True,
    )

@app.on_message(filters.command("about") & (filters.private | filters.group))
async def about_handler(client: Client, message: Message):
    if not await verify_user_complete(client, message):
        return

    await message.reply_text(
        get_about_text(),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]),
        quote=True,
    )

@app.on_message(filters.command("stats") & (filters.private | filters.group))
async def stats_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in config.ADMINS and uid != config.OWNER_ID:
        return await message.reply_text("❌ Unauthorized.")

    stats = await db.get_bot_stats()
    text = f"""
📊 **Bot Statistics**

👥 **Total Users:** `{stats.get('total_users', 0)}`
🎬 **Total Merges:** `{stats.get('total_merges', 0)}`
📈 **Today's Merges:** `{stats.get('today_merges', 0)}`
🤖 **Bot Status:** Active ✅
💾 **Database Status:** {'Connected ✅' if db.connected else 'Disconnected ❌'}`
"""

    await message.reply_text(text, quote=True)

@app.on_message(filters.command("cancel") & (filters.private | filters.group))
async def cancel_handler(client: Client, message: Message):
    uid = message.from_user.id
    clear_user_data(uid)
    await message.reply_text(
        "✅ Operation cancelled. Queue cleared.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]]),
        quote=True,
    )

# ===================== ADMIN HANDLERS =====================

@app.on_message(filters.command("admin") & (filters.private | filters.group))
async def admin_panel(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in config.ADMINS and uid != config.OWNER_ID:
        return await message.reply_text("❌ Unauthorized.")

    admin_text = f"""
🔧 **Admin Panel**

Welcome to the admin dashboard, {message.from_user.first_name}!

Use the buttons below to manage the bot:
"""

    await message.reply_text(admin_text, reply_markup=get_admin_keyboard(), quote=True)

# ===================== VIDEO HANDLERS =====================

@app.on_message((filters.video | filters.document) & (filters.private | filters.group))
async def video_handler(client: Client, message: Message):
    if not await verify_user_complete(client, message):
        return

    user_id = message.from_user.id

    # Initialize user data if not exists
    if user_id not in user_data:
        user_data[user_id] = {"videos": [], "state": None}

    # Download video
    try:
        status_msg = await message.reply_text("📥 **Downloading video...**", quote=True)
        
        video_path = await download_from_tg(client, message, user_id, status_msg)
        user_data[user_id]["videos"].append(video_path)
        
        video_count = len(user_data[user_id]["videos"])
        
        await status_msg.edit_text(
            f"✅ **Video added to queue!**\n\n"
            f"📁 **Videos in queue:** `{video_count}`\n"
            f"📝 **Latest:** `{os.path.basename(video_path)}`\n\n"
            f"{'🎬 **Ready to merge!** Click Merge Now below.' if video_count >= 2 else '➕ Add more videos to start merging.'}",
            reply_markup=get_video_queue_keyboard(video_count)
        )
        
    except Exception as e:
        logger.error(f"Video download error: {e}")
        await message.reply_text(f"❌ **Download failed!**\n\n🚨 **Error:** `{str(e)}`", quote=True)

@app.on_message(filters.text & (filters.private | filters.group) & ~filters.command(["start", "help", "about", "stats", "cancel", "admin"]))
async def text_handler(client: Client, message: Message):
    if not await verify_user_complete(client, message):
        return

    user_id = message.from_user.id
    text = message.text.strip()

    # Check if it's a URL
    if is_valid_url(text):
        # Initialize user data if not exists
        if user_id not in user_data:
            user_data[user_id] = {"videos": [], "state": None}

        try:
            status_msg = await message.reply_text("📥 **Downloading from URL...**", quote=True)
            
            video_path = await download_from_url(text, user_id, status_msg)
            user_data[user_id]["videos"].append(video_path)
            
            video_count = len(user_data[user_id]["videos"])
            
            await status_msg.edit_text(
                f"✅ **Video downloaded from URL!**\n\n"
                f"📁 **Videos in queue:** `{video_count}`\n"
                f"📝 **Latest:** `{os.path.basename(video_path)}`\n\n"
                f"{'🎬 **Ready to merge!** Click Merge Now below.' if video_count >= 2 else '➕ Add more videos to start merging.'}",
                reply_markup=get_video_queue_keyboard(video_count)
            )
            
        except Exception as e:
            logger.error(f"URL download error: {e}")
            await message.reply_text(f"❌ **Download failed!**\n\n🚨 **Error:** `{str(e)}`", quote=True)

# ===================== CALLBACK HANDLERS =====================

@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    # Force subscribe check for all callbacks
    if not await force_subscribe_check(client, user_id):
        await callback_query.answer("🔔 Please join our channel first!", show_alert=True)
        return

    try:
        if data == "check_subscription":
            if await force_subscribe_check(client, user_id):
                await callback_query.answer("✅ Welcome! You can now use the bot.", show_alert=True)
                await callback_query.message.delete()
                # Trigger start command
                fake_message = type('obj', (object,), {
                    'from_user': callback_query.from_user,
                    'chat': callback_query.message.chat,
                    'text': '/start',
                    'reply_text': callback_query.message.reply_text,
                    'reply_photo': callback_query.message.reply_photo
                })
                await start_handler(client, fake_message)
            else:
                await callback_query.answer("❌ Please join the channel first!", show_alert=True)

        elif data == "back_to_start":
            user_name = callback_query.from_user.first_name or str(user_id)
            
            try:
                text = config.START_TEXT.format(
                    bot_name=config.BOT_NAME,
                    developer=config.DEVELOPER,
                    user=user_name
                )
            except KeyError as e:
                text = (
                    f"🎬 **Welcome to {config.BOT_NAME}!**\n\n"
                    f"Hi {user_name}! 👋\n\n"
                    f"I can help you merge multiple videos into one.\n\n"
                    f"**Developer:** {config.DEVELOPER}"
                )

            await callback_query.message.edit_text(text, reply_markup=get_main_keyboard())
            await callback_query.answer()

        elif data == "help":
            await callback_query.message.edit_text(
                get_help_text(),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]])
            )
            await callback_query.answer()

        elif data == "about":
            await callback_query.message.edit_text(
                get_about_text(),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]])
            )
            await callback_query.answer()

        elif data == "clear_all_videos":
            clear_user_data(user_id)
            await callback_query.message.edit_text(
                "🗑️ **All videos cleared from queue!**\n\nSend videos to start building a new queue.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]])
            )
            await callback_query.answer("✅ Queue cleared!")

        elif data == "merge_now":
            if user_id not in user_data or len(user_data[user_id]["videos"]) < 2:
                await callback_query.answer("❌ Need at least 2 videos to merge!", show_alert=True)
                return

            await callback_query.message.edit_text(
                "🎬 **Choose upload method for merged video:**",
                reply_markup=get_upload_choice_keyboard()
            )
            await callback_query.answer()

        elif data == "upload_telegram":
            await process_merge_and_upload(client, callback_query, "telegram")

        elif data == "upload_gofile":
            await process_merge_and_upload(client, callback_query, "gofile")

        # Admin callbacks
        elif data == "admin_stats":
            if user_id not in config.ADMINS and user_id != config.OWNER_ID:
                await callback_query.answer("❌ Unauthorized!", show_alert=True)
                return

            stats = await db.get_bot_stats()
            text = f"""
📊 **Detailed Bot Statistics**

👥 **Users:**
• Total: `{stats.get('total_users', 0)}`
• Banned: `{stats.get('banned_users', 0)}`
• Authorized: `{stats.get('authorized_users', 0)}`
• Active (24h): `{stats.get('active_users_24h', 0)}`

🎬 **Merges:**
• Total: `{stats.get('total_merges', 0)}`
• Today: `{stats.get('today_merges', 0)}`

📅 **Bot Started:** `{stats.get('bot_start_date', 'Unknown')}`
💾 **Database:** {'Connected ✅' if db.connected else 'Disconnected ❌'}
"""

            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin")]])
            )
            await callback_query.answer()

        else:
            await callback_query.answer("⚠️ Unknown command!", show_alert=True)

    except Exception as e:
        logger.error(f"Callback error: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

async def process_merge_and_upload(client: Client, callback_query: CallbackQuery, upload_method: str):
    """Process video merging and upload"""
    user_id = callback_query.from_user.id
    
    if user_id not in user_data or len(user_data[user_id]["videos"]) < 2:
        await callback_query.answer("❌ Need at least 2 videos to merge!", show_alert=True)
        return

    try:
        videos = user_data[user_id]["videos"]
        
        # Start merging
        await callback_query.message.edit_text("🎬 **Starting video merge...**")
        
        merged_path = await merge_videos(videos, user_id, callback_query.message)
        
        if not merged_path:
            await callback_query.message.edit_text("❌ **Merge failed!**")
            return

        # Log merge activity
        user_name = callback_query.from_user.first_name or str(user_id)
        file_size = os.path.getsize(merged_path)
        await db.increment_merge_count(user_id)
        await db.log_merge(user_id, user_name, len(videos), file_size, time.time())

        # Upload based on method
        if upload_method == "telegram":
            await upload_to_telegram(
                client, 
                callback_query.message.chat.id, 
                merged_path, 
                callback_query.message,
                f"🎬 **Merged by {config.BOT_NAME}**\n\n"
                f"📁 **Original videos:** {len(videos)}\n"
                f"📊 **Size:** {format_file_size(file_size)}\n"
                f"👤 **User:** {user_name}"
            )
        elif upload_method == "gofile":
            uploader = GofileUploader()
            download_link = await uploader.upload_file(merged_path, callback_query.message)
            
            await callback_query.message.edit_text(
                f"✅ **Upload Complete!**\n\n"
                f"📁 **File:** `{os.path.basename(merged_path)}`\n"
                f"📊 **Size:** `{format_file_size(file_size)}`\n"
                f"🔗 **Download:** {download_link}"
            )

        # Log merged file
        await send_log_message(
            client,
            f"🎬 **Video Merged Successfully!**\n\n"
            f"👤 **User:** {user_name} (`{user_id}`)\n"
            f"📁 **Videos:** {len(videos)}\n"
            f"📊 **Size:** {format_file_size(file_size)}\n"
            f"📤 **Method:** {upload_method.title()}",
            log_type="merged_file"
        )

        # Clear user data
        clear_user_data(user_id)
        
    except Exception as e:
        logger.error(f"Merge and upload error: {e}")
        await callback_query.message.edit_text(f"❌ **Process failed!**\n\n🚨 **Error:** `{str(e)}`")

# ===================== STARTUP AND SHUTDOWN =====================

@app.on_message(filters.command("test") & filters.private)
async def test_handler(client: Client, message: Message):
    """Test command for debugging"""
    if message.from_user.id == config.OWNER_ID:
        await message.reply_text("✅ Bot is working correctly!")

async def startup():
    """Initialize bot on startup"""
    print("🤖 Starting Video Merger Bot...")
    
    # Create download directory
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    
    # Connect to database
    if config.MONGO_URI:
        await db.connect()
    else:
        print("⚠️ No MongoDB URI provided. Database features disabled.")
    
    print("✅ Bot started successfully!")

async def shutdown():
    """Cleanup on shutdown"""
    print("🛑 Shutting down bot...")
    
    # Cleanup all user data
    for user_id in list(user_data.keys()):
        clear_user_data(user_id)
    
    print("✅ Bot shutdown complete!")

if __name__ == "__main__":
    app.run(startup(), shutdown())
    async def main():
        await startup()
        try:
            await app.start()
            print("✅ Bot is now running! Press Ctrl+C to stop.")
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            print("🛑 Bot stopped by user")
        finally:
            await shutdown()
            await app.stop()
    
    asyncio.run(main())
