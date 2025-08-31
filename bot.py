# bot_enhanced.py - Professional Video Merger Bot with MongoDB Integration

import os
import shutil
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserNotParticipant

# Import your existing modules (unchanged)
from config import Config
from database import db
from helpers import *
from downloader import download_from_url, download_from_tg
from merger import merge_videos  # Your existing merger.py (unchanged)
from uploader import GofileUploader, upload_to_telegram
from utils import cleanup_files, is_valid_url

# Initialize bot
app = Client(
    "video_merger_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# User data storage (in-memory for queue management)
user_data = {}

def clear_user_data(user_id: int):
    """Clear user session data"""
    if user_id in user_data:
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        cleanup_files(user_download_dir)
        
        custom_thumb = user_data[user_id].get("custom_thumbnail")
        if custom_thumb and os.path.exists(custom_thumb):
            os.remove(custom_thumb)
        
        user_data.pop(user_id, None)

# Filters for different states
async def is_waiting_for_thumbnail(_, __, message: Message):
    if not message.from_user:
        return False
    return user_data.get(message.from_user.id, {}).get("state") == "waiting_for_thumbnail"

async def is_waiting_for_filename(_, __, message: Message):
    if not message.from_user:
        return False
    return user_data.get(message.from_user.id, {}).get("state") == "waiting_for_filename"

async def is_waiting_for_broadcast(_, __, message: Message):
    if not message.from_user:
        return False
    return user_data.get(message.from_user.id, {}).get("state") == "waiting_for_broadcast"

# Start command with professional welcome
@app.on_message(filters.command(["start"]) & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Force subscribe check
    if not await force_subscribe_check(client, message):
        return
    
    # Clear any existing session
    clear_user_data(user_id)
    
    # Add user to database
    await db.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    # Send log to channel
    await send_log_message(
        client, "new_user", 
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_id
    )
    
    # Create welcome message with thumbnail
    welcome_text = config.START_TEXT.format(
        bot_name=config.BOT_NAME,
        developer=config.DEVELOPER
    )
    
    # Create professional keyboard
    keyboard = get_main_keyboard()
    
    # Send welcome message with thumbnail (you can add a welcome image)
    await message.reply_text(
        welcome_text,
        reply_markup=keyboard,
        quote=True
    )

# Help command
@app.on_message(filters.command(["help"]) & filters.private)
async def help_handler(client: Client, message: Message):
    if not await force_subscribe_check(client, message):
        return
        
    await message.reply_text(
        get_help_text(),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Home", callback_data="back_to_start")]
        ]),
        quote=True
    )

# Stats command (Admin only)
@app.on_message(filters.command(["stats"]) & filters.private)
async def stats_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in config.ADMINS and user_id != config.OWNER_ID:
        await message.reply_text("❌ You don't have permission to use this command!")
        return
    
    stats = await db.get_bot_stats()
    if stats:
        stats_text = f"""
📊 **Bot Statistics**

👥 **Total Users:** `{stats['total_users']}`
🎬 **Total Merges:** `{stats['total_merges']}`
📈 **Today's Merges:** `{stats['today_merges']}`
🤖 **Bot Status:** Active ✅

💾 **Database Status:** Connected
"""
        await message.reply_text(stats_text, quote=True)
    else:
        await message.reply_text("❌ Error fetching statistics!")

# Cancel command
@app.on_message(filters.command(["cancel"]))
async def cancel_handler(client: Client, message: Message):
    user_id = message.from_user.id
    clear_user_data(user_id)
    
    await message.reply_text(
        "✅ **Operation Cancelled**\n\nYour queue has been cleared. Use /start to begin again.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Go Home", callback_data="back_to_start")]
        ]),
        quote=True
    )

# Admin panel command
@app.on_message(filters.command(["admin"]) & filters.private)
async def admin_panel(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id != config.OWNER_ID and user_id not in config.ADMINS:
        await message.reply_text("❌ You don't have admin access!")
        return
    
    admin_text = f"""
🔧 **Admin Panel**

Welcome to the admin dashboard, {message.from_user.first_name}!

Use the buttons below to manage the bot:
"""
    
    await message.reply_text(
        admin_text,
        reply_markup=get_admin_keyboard(),
        quote=True
    )

# Broadcast command (Owner only)
@app.on_message(filters.command(["broadcast"]) & filters.private)
async def broadcast_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id != config.OWNER_ID:
        await message.reply_text("❌ Only the owner can use this command!")
        return
    
    user_data[user_id] = {"state": "waiting_for_broadcast"}
    
    await message.reply_text(
        "📢 **Broadcast Mode**\n\nSend me the message you want to broadcast to all users.\n\nUse /cancel to abort.",
        quote=True
    )

# Handle broadcast message
@app.on_message(filters.text & filters.private & filters.create(is_waiting_for_broadcast))
async def handle_broadcast(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id != config.OWNER_ID:
        return
    
    user_data[user_id]["state"] = None
    broadcast_message = message.text
    
    status_msg = await message.reply_text("📡 **Starting broadcast...**")
    
    users = await db.get_all_users()
    success = 0
    failed = 0
    
    for target_user_id in users:
        try:
            await client.send_message(target_user_id, broadcast_message)
            success += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await client.send_message(target_user_id, broadcast_message)
                success += 1
            except:
                failed += 1
        except:
            failed += 1
        
        # Update status every 50 users
        if (success + failed) % 50 == 0:
            await status_msg.edit_text(
                f"📡 **Broadcasting...**\n\n"
                f"✅ Successful: {success}\n"
                f"❌ Failed: {failed}\n"
                f"📊 Progress: {success + failed}/{len(users)}"
            )
    
    await status_msg.edit_text(
        f"✅ **Broadcast Completed!**\n\n"
        f"📊 **Results:**\n"
        f"✅ Successful: {success}\n"
        f"❌ Failed: {failed}\n"
        f"👥 Total Users: {len(users)}"
    )

# Thumbnail handler
@app.on_message(filters.photo & filters.private & filters.create(is_waiting_for_thumbnail))
async def thumbnail_handler(client: Client, message: Message):
    user_id = message.from_user.id
    status_msg = user_data[user_id]["status_message"]
    
    await status_msg.edit_text("🖼️ **Processing thumbnail...**")
    
    thumb_path = await message.download(
        file_name=os.path.join(config.DOWNLOAD_DIR, str(user_id), "custom_thumb.jpg")
    )
    
    user_data[user_id]["custom_thumbnail"] = thumb_path
    user_data[user_id]["state"] = "waiting_for_filename"
    
    await status_msg.edit_text(
        "✅ **Thumbnail Saved!**\n\n"
        "Now send me the **filename** (without extension) for your merged video."
    )

# No thumbnail handler
@app.on_message(filters.command("notg_thumbnail") & filters.private & filters.create(is_waiting_for_thumbnail))
async def no_thumbnail_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_data[user_id]["custom_thumbnail"] = None
    user_data[user_id]["state"] = "waiting_for_filename"
    
    await user_data[user_id]["status_message"].edit_text(
        "👍 **Using Default Thumbnail**\n\n"
        "Now send me the **filename** (without extension) for your merged video."
    )

# Filename handler
@app.on_message(filters.text & filters.private & filters.create(is_waiting_for_filename))
async def filename_handler(client: Client, message: Message):
    user_id = message.from_user.id
    status_msg = user_data[user_id]["status_message"]
    filename = os.path.basename(message.text.strip())
    
    user_data[user_id]["custom_filename"] = filename
    user_data[user_id]["state"] = None
    
    await status_msg.edit_text(
        f"✅ **Filename Set:** `{filename}.mkv`\n\n🚀 **Starting upload to Telegram...**"
    )
    
    # Start upload process
    file_path = user_data[user_id]["merged_file"]
    thumb_path = user_data[user_id].get("custom_thumbnail")
    
    await upload_to_telegram(
        client=client,
        chat_id=message.chat.id,
        file_path=file_path,
        status_message=status_msg,
        custom_thumbnail=thumb_path,
        custom_filename=filename
    )
    
    # Log merge activity
    await send_log_message(
        client, "merge_activity",
        f"📁 **File Merged & Uploaded**\n\n"
        f"👤 **User:** {message.from_user.first_name} (`{user_id}`)\n"
        f"📎 **File:** `{filename}.mkv`\n"
        f"📅 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    clear_user_data(user_id)

# File handler - Videos and URLs
@app.on_message((filters.video | (filters.text & ~filters.command(["start", "help", "cancel", "merge", "notg_thumbnail", "stats", "admin", "broadcast"]))) & (filters.private | filters.group))
async def file_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Authorization check
    if not await is_authorized_user(user_id, chat_id):
        if chat_id != user_id:  # Group message
            await message.reply_text(
                "❌ **Unauthorized Chat**\n\nThis bot is only available in authorized chats. Contact the owner to get access.",
                quote=True
            )
        return
    
    # Force subscribe check for private chats
    if chat_id == user_id:
        if not await force_subscribe_check(client, message):
            return
    
    # Check if user is in a special state
    if user_data.get(user_id, {}).get("state"):
        await message.reply_text(
            "⏳ **Please complete the current process first**\n\nOr use /cancel to start over.",
            quote=True
        )
        return
    
    # Update user activity
    await db.update_user_activity(user_id)
    
    # Initialize user data if needed
    if user_id not in user_data:
        user_data[user_id] = {"queue": []}
    
    # Process the item
    item = message if message.video else message.text
    item_type = "Video" if message.video else "Link"
    
    # Validate URL
    if item_type == "Link" and not is_valid_url(item):
        await message.reply_text(
            "⚠️ **Invalid Link**\n\nPlease send a valid direct download link (HTTP/HTTPS).",
            quote=True
        )
        return
    
    # Add to queue
    user_data[user_id].setdefault("queue", []).append(item)
    queue_count = len(user_data[user_id]["queue"])
    
    # Create response message
    response_text = f"✅ **{item_type} Added to Queue!**\n\n📊 **Queue Status:** {queue_count} item(s)"
    
    # Get appropriate keyboard
    keyboard = get_video_queue_keyboard(queue_count)
    
    await message.reply_text(
        response_text,
        reply_markup=keyboard,
        quote=True
    )

# Merge command (for compatibility)
@app.on_message(filters.command(["merge"]) & (filters.private | filters.group))
async def merge_command(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Authorization check
    if not await is_authorized_user(user_id, chat_id):
        await message.reply_text("❌ **Access Denied**\n\nYou don't have permission to use this bot here.")
        return
    
    # Check queue
    if user_id not in user_data or not user_data[user_id].get("queue"):
        await message.reply_text(
            "📭 **Empty Queue**\n\nPlease add videos to your queue first!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📚 How to Use", callback_data="help_menu")]
            ]),
            quote=True
        )
        return
    
    if len(user_data[user_id]["queue"]) < 2:
        await message.reply_text(
            "⚠️ **Need More Videos**\n\nYou need at least 2 videos to merge.",
            quote=True
        )
        return
    
    # Start merge process directly
    await start_merge_process(client, message, user_id)

# Callback query handler
@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data
    
    try:
        # Force subscribe callbacks
        if data == "check_subscription":
            if await is_user_member(client, user_id, config.FORCE_SUB_CHANNEL):
                await query.message.delete()
                # Re-send start message
                await start_handler(client, query.message)
            else:
                await query.answer("❌ You haven't joined the channel yet!", show_alert=True)
            return
        
        # Main menu callbacks
        if data == "back_to_start":
            await query.message.edit_text(
                config.START_TEXT.format(
                    bot_name=config.BOT_NAME,
                    developer=config.DEVELOPER
                ),
                reply_markup=get_main_keyboard()
            )
        
        elif data == "help_menu":
            await query.message.edit_text(
                get_help_text(),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
                ])
            )
        
        elif data == "about_menu":
            await query.message.edit_text(
                get_about_text(),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
                ])
            )
        
        elif data == "home_menu":
            await query.answer("🏠 You're already at home!", show_alert=False)
        
        # Queue management callbacks
        elif data == "add_more":
            await query.answer("📹 Send me more videos or links!", show_alert=False)
        
        elif data == "clear_queue":
            clear_user_data(user_id)
            await query.message.edit_text(
                "🗑️ **Queue Cleared**\n\nAll videos have been removed from your queue.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Home", callback_data="back_to_start")]
                ])
            )
        
        elif data == "start_merge":
            await query.message.edit_reply_markup(None)
            await start_merge_process(client, query.message, user_id)
        
        # Upload choice callbacks
        elif data == "upload_tg":
            if user_id not in user_data or not user_data[user_id].get("merged_file"):
                await query.answer("❌ Session expired! Please start over.", show_alert=True)
                return
            
            user_data[user_id]["state"] = "waiting_for_thumbnail"
            await query.message.edit_text(
                "🖼️ **Thumbnail Selection**\n\n"
                "Send me a **photo** to use as thumbnail for your video.\n\n"
                "Or send /notg_thumbnail to use a default thumbnail."
            )
        
        elif data == "upload_gofile":
            if user_id not in user_data or not user_data[user_id].get("merged_file"):
                await query.answer("❌ Session expired! Please start over.", show_alert=True)
                return
            
            status_msg = await query.message.edit_text("🔗 **Uploading to GoFile.io...**")
            
            try:
                uploader = GofileUploader()
                link = await uploader.upload_file(user_data[user_id]["merged_file"])
                
                await status_msg.edit_text(
                    f"✅ **GoFile Upload Complete!**\n\n"
                    f"🔗 **Download Link:** {link}\n\n"
                    f"💡 **Note:** Links expire after 10 days of inactivity."
                )
            except Exception as e:
                await status_msg.edit_text(f"❌ **GoFile Upload Failed!**\n\nError: `{str(e)}`")
            
            clear_user_data(user_id)
        
        # Admin callbacks
        elif data.startswith("admin_"):
            if user_id not in config.ADMINS and user_id != config.OWNER_ID:
                await query.answer("❌ Access denied!", show_alert=True)
                return
            
            await handle_admin_callbacks(client, query, data)
        
        await query.answer()
        
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

async def start_merge_process(client: Client, message: Message, user_id: int):
    """Start the merge process"""
    try:
        status_msg = await message.reply_text("🚀 **Starting merge process...**")
        user_data[user_id]["status_message"] = status_msg
        
        # Download files
        video_paths = []
        queue = user_data[user_id]["queue"]
        
        for i, item in enumerate(queue):
            await status_msg.edit_text(f"📥 **Downloading item {i+1} of {len(queue)}...**")
            
            if isinstance(item, str):
                file_path = await download_from_url(item, user_id, status_msg)
            else:
                file_path = await download_from_tg(item, user_id, status_msg)
            
            if not file_path:
                await status_msg.edit_text("❌ **Download failed!** Cancelling operation.")
                clear_user_data(user_id)
                return
            
            video_paths.append(file_path)
        
        # Merge videos
        start_time = datetime.now()
        merged_path = await merge_videos(video_paths, user_id, status_msg)
        merge_time = (datetime.now() - start_time).total_seconds()
        
        if not merged_path:
            clear_user_data(user_id)
            return
        
        user_data[user_id]["merged_file"] = merged_path
        
        # Log merge activity
        file_size = os.path.getsize(merged_path) if os.path.exists(merged_path) else 0
        await db.log_merge(user_id, len(video_paths), file_size, merge_time)
        await db.increment_merge_count(user_id)
        
        # Show upload options
        await status_msg.edit_text(
            "✅ **Merge Completed Successfully!**\n\n"
            "Choose your upload destination:",
            reply_markup=get_upload_choice_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error in merge process: {e}")
        await status_msg.edit_text(f"❌ **Merge failed!** Error: {str(e)}")
        clear_user_data(user_id)

async def handle_admin_callbacks(client: Client, query: CallbackQuery, data: str):
    """Handle admin panel callbacks"""
    if data == "admin_stats":
        stats = await db.get_bot_stats()
        if stats:
            stats_text = f"""
📊 **Detailed Bot Statistics**

👥 **Users:**
├ Total Users: `{stats['total_users']}`
├ Active Today: `{stats.get('active_today', 'N/A')}`
└ Banned Users: `{stats.get('banned_users', 'N/A')}`

🎬 **Merges:**
├ Total Merges: `{stats['total_merges']}`
├ Today's Merges: `{stats['today_merges']}`
└ Average per Day: `{stats.get('avg_daily', 'N/A')}`

💾 **System:**
├ Database: Connected ✅
├ Storage: Available ✅
└ Bot Status: Online 🟢
"""
            await query.message.edit_text(
                stats_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
                ])
            )
        else:
            await query.answer("❌ Error fetching stats!", show_alert=True)
    
    elif data == "admin_back":
        await query.message.edit_text(
            "🔧 **Admin Panel**\n\nChoose an option:",
            reply_markup=get_admin_keyboard()
        )

if __name__ == "__main__":
    print(f"🚀 {config.BOT_NAME} is starting...")
    print(f"👤 Owner: {config.DEVELOPER}")
    print(f"📊 MongoDB: {'Enabled' if config.MONGO_URI else 'Disabled'}")
    print(f"🔔 Force Subscribe: {'Enabled' if config.FORCE_SUB_CHANNEL else 'Disabled'}")
    
    app.run()
