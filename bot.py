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

# --- Define state-based filters ---
# This is the corrected function.
async def is_waiting_for_state(state: str, _, update) -> bool:
    """
    Helper filter to check the user's current state.
    It handles both Message and CallbackQuery updates.
    """
    if isinstance(update, Message):
        user = update.from_user
    elif isinstance(update, CallbackQuery):
        user = update.from_user
    else:
        return False
    
    if not user:
        return False
    
    return user_data.get(user.id, {}).get("state") == state

is_waiting_for_broadcast = filters.create(is_waiting_for_state, state="broadcast")
is_waiting_for_thumbnail = filters.create(is_waiting_for_state, state="waiting_for_thumbnail")
is_waiting_for_filename = filters.create(is_waiting_for_state, state="waiting_for_filename")

# ===================== MAIN HANDLERS =====================

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Complete user verification
    if not await verify_user_complete(client, message):
        return
    
    clear_user_data(user_id)
    
    usr_cmd = message.text.split("_")[-1] if "_" in message.text else "/start"
    
    if usr_cmd == "/start":
        text = config.START_TEXT.format(bot_name=config.BOT_NAME, developer=config.DEVELOPER)
        
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
📈 **Today's Merges:** `{stats['today_merges']}`
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
    await status.edit_text("🖼 Processing thumbnail...")
    
    user_dir = os.path.join(config.DOWNLOAD_DIR, str(uid))
    os.makedirs(user_dir, exist_ok=True)
    
    path = await message.download(os.path.join(user_dir, "thumb.jpg"))
    user_data[uid].update({"custom_thumbnail": path, "state": "waiting_for_filename"})
    await status.edit_text("✅ Thumbnail saved! Now send the filename (without extension).")

@app.on_message(filters.command("no_thumbnail") & filters.private & is_waiting_for_thumbnail)
async def no_thumbnail(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in user_data or "status_message" not in user_data[uid]:
        return await message.reply_text("❌ Session expired. Please start over.")
    
    user_data[uid].update({"custom_thumbnail": None, "state": "waiting_for_filename"})
    await user_data[uid]["status_message"].edit_text("👍 Using default thumbnail. Send filename:")

@app.on_message(filters.text & filters.private & is_waiting_for_filename)
async def filename_handler(client: Client, message: Message):
    uid = message.from_user.id
    if uid not in user_data or "status_message" not in user_data[uid]:
        return await message.reply_text("❌ Session expired. Please start over.")
    
    status = user_data[uid]["status_message"]
    name = os.path.basename(message.text.strip())
    user_data[uid].update({"custom_filename": name, "state": None})
    
    await status.edit_text(f"📁 Filename: `{name}.mkv`\n🚀 Starting upload...")
    
    await upload_to_telegram(
        client,
        message.chat.id,
        user_data[uid]["merged_file"],
        status,
        user_data[uid].get("custom_thumbnail"),
        name,
    )
    
    await send_log_message(
        client, "merge_activity",
        f"📁 **File Merged & Uploaded**\n👤 User: {message.from_user.first_name} (`{uid}`)\n📎 File: `{name}.mkv`\n📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        uid
    )
    
    clear_user_data(uid)

@app.on_message(
    filters.video | (filters.text & ~filters.command([
        "start", "help", "about", "cancel", "merge", "notg_thumbnail", "no_thumbnail",
        "stats", "admin", "broadcast", "ban", "unban"
    ]))
)
async def file_handler(client: Client, message: Message):
    uid = message.from_user.id
    cid = message.chat.id
    
    if not await is_authorized_user(uid, cid):
        if cid != uid:
            return await message.reply_text("❌ This bot is not authorized in this chat.")
        if not await verify_user_complete(client, message):
            return
    
    if user_data.get(uid, {}).get("state"):
        return await message.reply_text("⏳ Please complete the current process or use /cancel.")
    
    await db.update_user_activity(uid)
    user_data.setdefault(uid, {"queue": []})
    
    item = message if message.video else message.text
    if not message.video and not is_valid_url(item):
        return await message.reply_text("⚠️ Please send a valid HTTP/HTTPS link.")
    
    user_data[uid]["queue"].append(item)
    count = len(user_data[uid]["queue"])
    
    item_type = "Video" if message.video else "Link"
    response_text = f"✅ **{item_type} Added to Queue!**\n📊 Queue: {count} item(s)"
    
    keyboard = get_video_queue_keyboard(count)
    await message.reply_text(response_text, reply_markup=keyboard, quote=True)

@app.on_message(filters.command("merge") & (filters.private | filters.group))
async def merge_command(client: Client, message: Message):
    uid = message.from_user.id
    cid = message.chat.id
    
    if not await is_authorized_user(uid, cid):
        return await message.reply_text("❌ Unauthorized.")
    
    queue = user_data.get(uid, {}).get("queue", [])
    if len(queue) < 2:
        return await message.reply_text("⚠️ You need at least 2 videos to merge.")
    
    await start_merge_process(client, message, uid)

# ===================== CALLBACK HANDLERS =====================

@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    data = query.data

    try:
        if data == "check_subscription":
            if await is_user_member(client, uid, config.FORCE_SUB_CHANNEL):
                await query.message.delete()
                fake_msg = type("obj", (), {
                    "from_user": query.from_user,
                    "chat": query.message.chat,
                    "text": "/start",
                    "reply_text": query.message.reply_text,
                    "reply_photo": getattr(query.message, "reply_photo", None)
                })()
                await start_handler(client, fake_msg)
            else:
                try:
                    await query.answer("❌ Please join the channel first!", show_alert=True)
                except Exception:
                    pass
            return

        if data == "back_to_start":
            text = config.START_TEXT.format(bot_name=config.BOT_NAME, developer=config.DEVELOPER)
            await query.message.edit_text(text, reply_markup=get_main_keyboard())

        elif data == "help_menu":
            await query.message.edit_text(
                get_help_text(),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]])
            )

        elif data == "about_menu":
            await query.message.edit_text(
                get_about_text(),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]])
            )

        elif data == "add_more":
            try:
                await query.answer("📹 Send more videos or links!")
            except Exception:
                pass

        elif data == "clear_queue":
            clear_user_data(uid)
            await query.message.edit_text(
                "🗑 Queue cleared!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]])
            )

        elif data == "start_merge":
            await query.message.edit_reply_markup(None)
            await start_merge_process(client, query.message, uid)

        elif data == "upload_tg":
            if uid not in user_data or "merged_file" not in user_data[uid]:
                try:
                    await query.answer("❌ Session expired!", show_alert=True)
                except Exception:
                    pass
                return

            user_data[uid]["state"] = "waiting_for_thumbnail"
            await query.message.edit_text(
                "🖼 **Thumbnail Selection**\n\nSend a photo for thumbnail or use /no_thumbnail for default."
            )

        elif data == "upload_gofile":
            if uid not in user_data or "merged_file" not in user_data[uid]:
                try:
                    await query.answer("❌ Session expired!", show_alert=True)
                except Exception:
                    pass
                return

            status = await query.message.edit_text("🔗 Uploading to GoFile...")
            try:
                uploader = GofileUploader()
                link = await uploader.upload_file(user_data[uid]["merged_file"])
                await status.edit_text(f"✅ **GoFile Upload Complete!**\n\n🔗 **Link:** {link}")
            except Exception as e:
                await status.edit_text(f"❌ GoFile upload failed: {e}")

            clear_user_data(uid)

        elif data.startswith("admin_"):
            if uid not in config.ADMINS and uid != config.OWNER_ID:
                try:
                    await query.answer("❌ Access denied!", show_alert=True)
                except Exception:
                    pass
                return
            await handle_admin_callbacks(client, query, data)

        try:
            await query.answer()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Callback error: {e}")
        try:
            await query.answer("❌ An error occurred!", show_alert=True)
        except Exception:
            pass

# ===================== HELPER FUNCTIONS =====================

async def start_merge_process(client: Client, message: Message, uid: int):
    """Start the video merge process"""
    status = await message.reply_text("🚀 Starting merge process...")
    user_data[uid]["status_message"] = status
    
    try:
        paths = []
        queue = user_data[uid]["queue"]
        
        for i, item in enumerate(queue, 1):
            await status.edit_text(f"📥 Downloading {i}/{len(queue)}...")
            
            if isinstance(item, str):
                path = await download_from_url(item, uid, status)
            else:
                path = await download_from_tg(item, uid, status)
            
            if not path:
                await status.edit_text("❌ Download failed!")
                return clear_user_data(uid)
            
            paths.append(path)
        
        await status.edit_text("🔄 Merging videos...")
        start_time = datetime.utcnow()
        merged = await merge_videos(paths, uid, status)
        
        if not merged:
            return clear_user_data(uid)
        
        merge_time = (datetime.utcnow() - start_time).total_seconds()
        file_size = os.path.getsize(merged) if os.path.exists(merged) else 0
        
        await db.log_merge(uid, len(paths), file_size, merge_time)
        await db.increment_merge_count(uid)
        
        user_data[uid]["merged_file"] = merged
        
        await status.edit_text(
            "✅ **Merge Complete!**\n\nChoose upload destination:",
            reply_markup=get_upload_choice_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Merge error: {e}")
        await status.edit_text(f"❌ Merge failed: {str(e)}")
        clear_user_data(uid)

async def handle_admin_callbacks(client: Client, query: CallbackQuery, data: str):
    """Handle admin panel callbacks"""
    if data == "admin_stats":
        stats = await db.get_bot_stats()
        text = f"""
📊 **Detailed Bot Statistics**

👥 **Users:** {stats['total_users']}
🎬 **Total Merges:** {stats['total_merges']}
📈 **Today's Merges:** {stats['today_merges']}
💾 **Database:** Connected ✅
🤖 **Status:** Online 🟢
"""
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
            ])
        )
    
    elif data == "admin_back":
        await query.message.edit_text(
            "🔧 **Admin Panel**\n\nChoose an option:",
            reply_markup=get_admin_keyboard()
        )

# ===================== STARTUP =====================

if __name__ == "__main__":
    print(f"🚀 {config.BOT_NAME} is starting...")
    print(f"👤 Owner: {config.DEVELOPER}")
    print(f"📊 MongoDB: {'Enabled' if hasattr(config, 'MONGO_URI') and config.MONGO_URI else 'Disabled'}")
    print(f"🔔 Force Subscribe: {'Enabled' if hasattr(config, 'FORCE_SUB_CHANNEL') and config.FORCE_SUB_CHANNEL else 'Disabled'}")
    
    app.run()
