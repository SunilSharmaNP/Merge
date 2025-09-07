# bot.py - ENHANCED VERSION WITH FORCE SUBSCRIBE, USER LOGS & MERGE LOGS

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
    send_log_message,
    get_main_keyboard,
    get_help_text,
    get_about_text,
    get_video_queue_keyboard,
    get_upload_choice_keyboard,
    get_admin_keyboard,
    verify_user_complete,
    is_user_banned_check,
    format_file_size,
    get_invite_link
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

# --- FIXED: Proper filter definitions ---
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

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Complete user verification with all checks
    if not await verify_user_complete(client, message):
        return
    
    clear_user_data(user_id)
    
    usr_cmd = message.text.split("_")[-1] if "_" in message.text else "/start"
    
    if usr_cmd == "/start":
        try:
            text = config.START_TEXT.format(
                bot_name=config.BOT_NAME, 
                developer=config.DEVELOPER
            )
        except (KeyError, AttributeError):
            text = f"""
🎬 **Welcome to {config.BOT_NAME}!**

🚀 **Most Advanced Video Merger Bot**

✨ **Features:**
• Merge multiple videos instantly
• Support for direct links & file uploads  
• High-quality output with all streams preserved
• Professional UI with smart controls
• Custom thumbnails support

📝 **How to Use:**
1. Send videos or direct download links
2. Click "Merge Now" when ready (minimum 2 videos)
3. Choose upload destination (Telegram/GoFile)
4. Set custom thumbnail and filename
5. Get your merged file!

💫 **Developed by:** {config.DEVELOPER}

🔥 **Ready to merge some videos?** Send me your first video!
"""
        
        if hasattr(config, 'START_PIC') and config.START_PIC:
            await message.reply_photo(
                photo=config.START_PIC,
                caption=text,
                reply_markup=get_main_keyboard(),
                quote=True
            )
        else:
            await message.reply_text(text, reply_markup=get_main_keyboard(), quote=True)
    
    else:
        if "stream_" in message.text:
            try:
                await message.reply_text("File streaming feature - implement your logic here")
            except Exception as e:
                await message.reply_text("❌ File not found or expired.")
                logger.error(f"Stream error: {e}")
        
        elif "file_" in message.text:
            try:
                await message.reply_text("File download feature - implement your logic here")
            except Exception as e:
                await message.reply_text("❌ File not found or expired.")
                logger.error(f"File error: {e}")

@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    if not await verify_user_complete(client, message):
        return
    
    await message.reply_text(
        get_help_text(),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]),
        quote=True,
    )

@app.on_message(filters.command("about") & filters.private)
async def about_handler(client: Client, message: Message):
    if not await verify_user_complete(client, message):
        return
    
    await message.reply_text(
        get_about_text(),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]),
        quote=True,
    )

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in config.ADMINS and uid != config.OWNER_ID:
        return await message.reply_text("❌ Unauthorized.")
    
    stats = await db.get_bot_stats()
    text = f"""
📊 **Bot Statistics**
👥 **Total Users:** `{stats['total_users']}`
🎬 **Total Merges:** `{stats['total_merges']}`
📁 **Total Files:** `{stats.get('total_files', 0)}`
📈 **Today's Merges:** `{stats['today_merges']}`
📤 **Today's Files:** `{stats.get('today_files', 0)}`
🤖 **Bot Status:** Active ✅
💾 **Database Status:** Connected ✅
"""
    await message.reply_text(text, quote=True)

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client: Client, message: Message):
    uid = message.from_user.id
    clear_user_data(uid)
    await message.reply_text(
        "✅ Operation cancelled. Queue cleared.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]]),
        quote=True,
    )

# ===================== ADMIN HANDLERS =====================

@app.on_message(filters.command("admin") & filters.private)
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

@app.on_message(filters.command("ban") & filters.private)
async def ban_user_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid != config.OWNER_ID and uid not in config.ADMINS:
        return await message.reply_text("❌ Unauthorized.")
    
    try:
        target_id = int(message.text.split(" ", 1)[1])
    except (IndexError, ValueError):
        return await message.reply_text("❌ Usage: `/ban <user_id>`")
    
    if await db.is_user_banned(target_id):
        return await message.reply_text(f"User `{target_id}` is already banned.")
    
    success = await db.ban_user(target_id, True)
    if success:
        try:
            await client.send_message(target_id, "🚫 You have been banned from using this bot.")
        except:
            pass
        await message.reply_text(f"✅ User `{target_id}` has been banned.")
        
        # Log ban action
        await send_log_message(
            client, "admin_action",
            f"🚫 **User Banned**\n**Admin:** {message.from_user.first_name} (`{uid}`)\n**Banned User:** `{target_id}`"
        )
    else:
        await message.reply_text("❌ Failed to ban user.")

@app.on_message(filters.command("unban") & filters.private)
async def unban_user_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid != config.OWNER_ID and uid not in config.ADMINS:
        return await message.reply_text("❌ Unauthorized.")
    
    try:
        target_id = int(message.text.split(" ", 1)[1])
    except (IndexError, ValueError):
        return await message.reply_text("❌ Usage: `/unban <user_id>`")
    
    if not await db.is_user_banned(target_id):
        return await message.reply_text(f"User `{target_id}` is not banned.")
    
    success = await db.ban_user(target_id, False)
    if success:
        try:
            await client.send_message(target_id, "✅ You have been unbanned. You can now use the bot.")
        except:
            pass
        await message.reply_text(f"✅ User `{target_id}` has been unbanned.")
        
        # Log unban action
        await send_log_message(
            client, "admin_action",
            f"✅ **User Unbanned**\n**Admin:** {message.from_user.first_name} (`{uid}`)\n**Unbanned User:** `{target_id}`"
        )
    else:
        await message.reply_text("❌ Failed to unban user.")

@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client: Client, message: Message):
    uid = message.from_user.id
    if uid != config.OWNER_ID:
        return await message.reply_text("❌ Only owner can broadcast.")
    
    user_data[uid] = {"state": "broadcast"}
    await message.reply_text("📢 Send the message you want to broadcast to all users.", quote=True)

@app.on_message(filters.text & filters.private & is_waiting_for_broadcast)
async def handle_broadcast(client: Client, message: Message):
    uid = message.from_user.id
    if uid != config.OWNER_ID:
        return
    
    user_data[uid]["state"] = None
    broadcast_message = message.text
    
    while True:
        broadcast_id = ''.join([random.choice(string.ascii_letters) for i in range(3)])
        if broadcast_id not in broadcast_ids:
            break
    
    status = await message.reply_text("📡 Starting broadcast...")
    users = await db.get_all_users()
    
    start_time = time.time()
    total_users = len(users)
    success = fail = 0
    
    broadcast_ids[broadcast_id] = {
        "total": total_users,
        "success": 0,
        "failed": 0
    }
    
    async with aiofiles.open('broadcast.txt', 'w') as log_file:
        for i, target_id in enumerate(users, 1):
            try:
                await client.send_message(target_id, broadcast_message)
                success += 1
                await log_file.write(f"✅ {target_id}\n")
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await client.send_message(target_id, broadcast_message)
                    success += 1
                    await log_file.write(f"✅ {target_id} (after FloodWait)\n")
                except Exception as e:
                    fail += 1
                    await log_file.write(f"❌ {target_id}: {str(e)}\n")
            except Exception as e:
                fail += 1
                await log_file.write(f"❌ {target_id}: {str(e)}\n")
            
            if i % 50 == 0:
                try:
                    await status.edit_text(f"📡 Broadcasting...\n✅ Success: {success}\n❌ Failed: {fail}\n📊 Progress: {i}/{total_users}")
                except:
                    pass
    
    broadcast_ids.pop(broadcast_id, None)
    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    
    result_text = f"""
✅ **Broadcast Completed!**

📊 **Results:**
• Total Users: {total_users}
• Successful: {success}
• Failed: {fail}
• Time Taken: {completed_in}
"""
    
    if fail > 0:
        await message.reply_document(
            document='broadcast.txt',
            caption=result_text,
            quote=True
        )
        os.remove('broadcast.txt')
    else:
        await status.edit_text(result_text)
    
    await db.log_broadcast(str(message.message_id), success, fail, total_users)

# ===================== FILE HANDLERS =====================

@app.on_message(filters.photo & filters.private & is_waiting_for_thumbnail)
async def thumbnail_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in user_data or "status_message" not in user_data[uid]:
        return await message.reply_text("❌ Session expired. Please start over.")
    
    status = user_data[uid]["status_message"]
    await status.edit_text("🖼️ Processing thumbnail...")
    
    user_dir = os.path.join(config.DOWNLOAD_DIR, str(uid))
    os.makedirs(user_dir, exist_ok=True)
    
    path = await message.download(file_name=os.path.join(user_dir, "custom_thumb.jpg"))
    user_data[uid].update({"custom_thumbnail": path, "state": "waiting_for_filename"})
    await status.edit_text(
        "✅ **Thumbnail saved!**\n\n"
        "Now, send me the **filename** (without extension) you want for the merged video."
    )

@app.on_message(filters.text & filters.private & is_waiting_for_filename)
async def filename_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in user_data or "status_message" not in user_data[uid]:
        return await message.reply_text("❌ Session expired. Please start over.")
    
    filename = message.text.strip()
    if not filename:
        return await message.reply_text("❌ Please send a valid filename.")
    
    # Remove invalid characters
    filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).rstrip()
    if not filename:
        return await message.reply_text("❌ Please send a valid filename with alphanumeric characters.")
    
    user_data[uid]["custom_filename"] = filename
    user_data[uid]["state"] = None
    
    await user_data[uid]["status_message"].edit_text(
        f"✅ **Setup Complete!**\n\n"
        f"📁 **Filename:** `{filename}.mp4`\n"
        f"🖼️ **Thumbnail:** {'✅ Custom' if user_data[uid].get('custom_thumbnail') else '❌ Auto-generated'}\n\n"
        f"🎬 **Starting merge process...**"
    )
    
    await start_merge_process(client, message, uid)

# Enhanced URL and video file handler
@app.on_message((filters.text | filters.video | filters.document) & filters.private)
async def media_handler(client: Client, message: Message):
    if not await verify_user_complete(client, message):
        return
    
    uid = message.from_user.id
    
    # Skip if user is in a special state
    if uid in user_data and user_data[uid].get("state") in ["broadcast", "waiting_for_thumbnail", "waiting_for_filename"]:
        return
    
    # Initialize user data if not exists
    if uid not in user_data:
        user_data[uid] = {"videos": [], "queue_message": None}
    
    success = False
    
    if message.text and is_valid_url(message.text.strip()):
        # Handle URL
        url = message.text.strip()
        status = await message.reply_text("📥 **Downloading from URL...**", quote=True)
        
        try:
            user_dir = os.path.join(config.DOWNLOAD_DIR, str(uid))
            os.makedirs(user_dir, exist_ok=True)
            
            video_path = await download_from_url(url, user_dir, status)
            if video_path and os.path.exists(video_path):
                user_data[uid]["videos"].append(video_path)
                success = True
                await status.edit_text(f"✅ **Downloaded!** Added to queue.\n📁 **File:** `{os.path.basename(video_path)}`")
            else:
                await status.edit_text("❌ **Download failed!** Please check the URL.")
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            await status.edit_text("❌ **Download failed!** Please try again.")
    
    elif message.video or (message.document and message.document.mime_type and "video" in message.document.mime_type):
        # Handle video file
        status = await message.reply_text("📥 **Downloading video...**", quote=True)
        
        try:
            user_dir = os.path.join(config.DOWNLOAD_DIR, str(uid))
            os.makedirs(user_dir, exist_ok=True)
            
            video_path = await download_from_tg(message, user_dir, status)
            if video_path and os.path.exists(video_path):
                user_data[uid]["videos"].append(video_path)
                success = True
                
                # Get file size for display
                file_size = os.path.getsize(video_path)
                await status.edit_text(
                    f"✅ **Downloaded!** Added to queue.\n"
                    f"📁 **File:** `{os.path.basename(video_path)}`\n"
                    f"📊 **Size:** `{format_file_size(file_size)}`"
                )
            else:
                await status.edit_text("❌ **Download failed!** Please try again.")
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            await status.edit_text("❌ **Download failed!** Please try again.")
    
    # Update queue display if successful
    if success:
        await update_queue_display(client, message, uid)

async def update_queue_display(client: Client, message: Message, uid: int):
    """Update the queue display with current videos."""
    if uid not in user_data:
        return
    
    videos = user_data[uid]["videos"]
    count = len(videos)
    
    if count == 0:
        return
    
    # Create queue text
    queue_text = f"📊 **Video Queue ({count} videos)**\n\n"
    
    total_size = 0
    for i, video_path in enumerate(videos, 1):
        try:
            size = os.path.getsize(video_path)
            total_size += size
            filename = os.path.basename(video_path)
            queue_text += f"`{i}.` **{filename}** ({format_file_size(size)})\n"
        except:
            queue_text += f"`{i}.` **{os.path.basename(video_path)}** (Unknown size)\n"
    
    queue_text += f"\n💾 **Total Size:** `{format_file_size(total_size)}`"
    
    # Get appropriate keyboard
    keyboard = get_video_queue_keyboard(count)
    
    # Update or send queue message
    if user_data[uid].get("queue_message"):
        try:
            await user_data[uid]["queue_message"].edit_text(queue_text, reply_markup=keyboard)
        except:
            # If edit fails, send new message
            user_data[uid]["queue_message"] = await message.reply_text(queue_text, reply_markup=keyboard, quote=True)
    else:
        user_data[uid]["queue_message"] = await message.reply_text(queue_text, reply_markup=keyboard, quote=True)

async def start_merge_process(client: Client, message: Message, uid: int):
    """Start the video merging process."""
    if uid not in user_data or not user_data[uid].get("videos"):
        return await message.reply_text("❌ No videos in queue.")
    
    videos = user_data[uid]["videos"]
    if len(videos) < 2:
        return await message.reply_text("❌ Need at least 2 videos to merge.")
    
    status_msg = user_data[uid].get("status_message")
    if not status_msg:
        status_msg = await message.reply_text("🎬 **Starting merge process...**", quote=True)
    
    try:
        # Start merge
        start_time = time.time()
        await status_msg.edit_text("⚙️ **Merging videos...** This may take a while.")
        
        user_dir = os.path.join(config.DOWNLOAD_DIR, str(uid))
        custom_filename = user_data[uid].get("custom_filename", f"merged_{int(time.time())}")
        output_path = os.path.join(user_dir, f"{custom_filename}.mp4")
        
        # Merge videos
        success = await merge_videos(videos, output_path, status_msg)
        
        if success and os.path.exists(output_path):
            merge_time = time.time() - start_time
            file_size = os.path.getsize(output_path)
            
            # Log merge activity to database
            await db.log_merge(uid, len(videos), file_size, merge_time, custom_filename)
            
            # Send merge log to FLOG channel
            await send_log_message(
                client, "merge_activity",
                f"🎬 **Video Merged Successfully**\n\n"
                f"👤 **User:** {message.from_user.first_name} (`{uid}`)\n"
                f"📁 **Filename:** `{custom_filename}.mp4`\n"
                f"🔢 **Videos Count:** `{len(videos)}`\n"
                f"📊 **File Size:** `{format_file_size(file_size)}`\n"
                f"⏱️ **Merge Time:** `{merge_time:.2f}s`\n"
                f"📅 **Date:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            
            await status_msg.edit_text(
                f"✅ **Merge completed!**\n\n"
                f"📁 **File:** `{custom_filename}.mp4`\n"
                f"📊 **Size:** `{format_file_size(file_size)}`\n"
                f"⏱️ **Time:** `{merge_time:.2f}s`\n\n"
                f"📤 **Choose upload destination:**",
                reply_markup=get_upload_choice_keyboard()
            )
            
            # Store output path for upload
            user_data[uid]["output_path"] = output_path
            
        else:
            await db.log_merge_error(uid, "Merge process failed", len(videos))
            await status_msg.edit_text("❌ **Merge failed!** Please try again with different videos.")
            clear_user_data(uid)
            
    except Exception as e:
        logger.error(f"Merge error: {e}")
        await db.log_merge_error(uid, str(e), len(videos))
        await status_msg.edit_text("❌ **Merge failed!** An error occurred during processing.")
        clear_user_data(uid)

# ===================== CALLBACK HANDLERS =====================

@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    uid = callback_query.from_user.id
    message = callback_query.message
    
    try:
        # Force subscribe check callback
        if data == "check_subscription":
            if await force_subscribe_check(client, uid):
                await callback_query.answer("✅ Welcome! You can now use the bot.", show_alert=True)
                
                # Add user and send log
                user_name = callback_query.from_user.first_name or str(uid)
                await db.add_user(uid, user_name, callback_query.from_user.username)
                await send_log_message(
                    client, "new_user",
                    f"👤 **New User Joined**\n**Name:** {user_name}\n**Username:** @{callback_query.from_user.username or 'None'}\n**ID:** `{uid}`\n**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                # Show start message
                try:
                    text = config.START_TEXT.format(bot_name=config.BOT_NAME, developer=config.DEVELOPER)
                except:
                    text = f"🎬 **Welcome to {config.BOT_NAME}!**\n\nI can help you merge multiple videos into one.\n\n**Developer:** {config.DEVELOPER}"
                
                await message.edit_text(text, reply_markup=get_main_keyboard())
            else:
                await callback_query.answer("❌ Please join the channel first!", show_alert=True)
            return
        
        # Main menu callbacks
        elif data == "back_to_start":
            try:
                text = config.START_TEXT.format(bot_name=config.BOT_NAME, developer=config.DEVELOPER)
            except:
                text = f"🎬 **Welcome to {config.BOT_NAME}!**\n\nI can help you merge multiple videos into one.\n\n**Developer:** {config.DEVELOPER}"
            await message.edit_text(text, reply_markup=get_main_keyboard())
        
        elif data == "help_menu":
            await message.edit_text(get_help_text(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]))
        
        elif data == "about_menu":
            await message.edit_text(get_about_text(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]))
        
        # Queue management callbacks
        elif data == "clear_queue":
            clear_user_data(uid)
            await message.edit_text("✅ **Queue cleared!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]))
        
        elif data == "add_more":
            await callback_query.answer("Send more videos or URLs to add to queue!", show_alert=False)
        
        elif data == "start_merge":
            if uid not in user_data or len(user_data[uid].get("videos", [])) < 2:
                await callback_query.answer("❌ Need at least 2 videos to merge!", show_alert=True)
                return
            
            await message.edit_text(
                "🎬 **Ready to merge!**\n\n"
                "📎 Send a **thumbnail image** (optional)\n"
                "or type **filename** to skip thumbnail and proceed with merge."
            )
            user_data[uid]["state"] = "waiting_for_thumbnail"
            user_data[uid]["status_message"] = message
        
        # Upload choice callbacks
        elif data == "upload_tg":
            if uid not in user_data or "output_path" not in user_data[uid]:
                await callback_query.answer("❌ No file to upload!", show_alert=True)
                return
            
            await message.edit_text("📤 **Uploading to Telegram...** Please wait.")
            
            try:
                output_path = user_data[uid]["output_path"]
                custom_filename = user_data[uid].get("custom_filename", "merged_video")
                thumbnail = user_data[uid].get("custom_thumbnail")
                
                # Upload to Telegram
                success = await upload_to_telegram(
                    client, message.chat.id, output_path, 
                    custom_filename, thumbnail, message
                )
                
                if success:
                    file_size = os.path.getsize(output_path)
                    
                    # Log file activity to FLOG
                    await db.log_file_activity(
                        uid, f"{custom_filename}.mp4", file_size, "telegram_upload"
                    )
                    
                    await send_log_message(
                        client, "file_activity",
                        f"📤 **File Uploaded to Telegram**\n\n"
                        f"👤 **User:** {callback_query.from_user.first_name} (`{uid}`)\n"
                        f"📁 **Filename:** `{custom_filename}.mp4`\n"
                        f"📊 **Size:** `{format_file_size(file_size)}`\n"
                        f"📅 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                    )
                    
                    await message.edit_text("✅ **Upload completed!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]))
                else:
                    await message.edit_text("❌ **Upload failed!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]))
                    
            except Exception as e:
                logger.error(f"Upload error: {e}")
                await message.edit_text("❌ **Upload failed!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]))
            
            finally:
                clear_user_data(uid)
        
        elif data == "upload_gofile":
            if uid not in user_data or "output_path" not in user_data[uid]:
                await callback_query.answer("❌ No file to upload!", show_alert=True)
                return
            
            await message.edit_text("🔗 **Uploading to GoFile...** Please wait.")
            
            try:
                output_path = user_data[uid]["output_path"]
                custom_filename = user_data[uid].get("custom_filename", "merged_video")
                
                # Upload to GoFile
                uploader = GofileUploader()
                download_url = await uploader.upload_file(output_path, message)
                
                if download_url:
                    file_size = os.path.getsize(output_path)
                    
                    # Log file activity to FLOG
                    await db.log_file_activity(
                        uid, f"{custom_filename}.mp4", file_size, "gofile_upload", download_url
                    )
                    
                    await send_log_message(
                        client, "file_activity",
                        f"🔗 **File Uploaded to GoFile**\n\n"
                        f"👤 **User:** {callback_query.from_user.first_name} (`{uid}`)\n"
                        f"📁 **Filename:** `{custom_filename}.mp4`\n"
                        f"📊 **Size:** `{format_file_size(file_size)}`\n"
                        f"🔗 **URL:** {download_url}\n"
                        f"📅 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                    )
                    
                    await message.edit_text(
                        f"✅ **Upload completed!**\n\n🔗 **Download Link:**\n{download_url}",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]])
                    )
                else:
                    await message.edit_text("❌ **Upload failed!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]))
                    
            except Exception as e:
                logger.error(f"GoFile upload error: {e}")
                await message.edit_text("❌ **Upload failed!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]))
            
            finally:
                clear_user_data(uid)
        
        # Close callback
        elif data == "close":
            await message.delete()
        
        else:
            await callback_query.answer("⚠️ Invalid option!", show_alert=False)
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

# ===================== STARTUP =====================

async def main():
    """Start the bot."""
    logger.info(f"🚀 Starting {config.BOT_NAME}...")
    
    # Print configuration info
    logger.info(f"📋 Configuration loaded successfully")
    logger.info(f"🔔 Force Subscribe: {'✅ Enabled' if config.FORCE_SUB_CHANNEL else '❌ Disabled'}")
    logger.info(f"📊 User Logging: {'✅ Enabled' if getattr(config, 'ULOG_CHANNEL', None) else '❌ Disabled'}")
    logger.info(f"📁 Merge Logging: {'✅ Enabled' if getattr(config, 'FLOG_CHANNEL', None) else '❌ Disabled'}")
    
    await app.start()
    logger.info(f"✅ {config.BOT_NAME} started successfully!")
    
    # Send startup message to log channel
    if getattr(config, 'LOG_CHANNEL', None):
        try:
            await app.send_message(
                config.LOG_CHANNEL,
                f"🚀 **{config.BOT_NAME} Started!**\n\n"
                f"📅 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"🤖 **Status:** Online ✅\n"
                f"💾 **Database:** Connected ✅"
            )
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.main()
