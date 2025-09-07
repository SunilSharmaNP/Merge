# uploader.py - ENHANCED with merged file logging
import os
import time
import asyncio
from aiohttp import ClientSession, FormData, ClientTimeout
from random import choice
from config import config
from utils import get_human_readable_size, get_progress_bar, get_video_properties
import logging
from helpers import send_merge_log
from database import db

logger = logging.getLogger(__name__)

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 2.0

# Configuration
GOFILE_CHUNK_SIZE = 5 * 1024 * 1024  # 5MB chunks
GOFILE_UPLOAD_TIMEOUT = 1800  # 30 minutes
MAX_RETRIES = 3

async def smart_progress_editor(status_message, text: str):
    """Smart progress editor with throttling"""
    if not status_message or not hasattr(status_message, 'chat'):
        return
    
    message_key = f"{status_message.chat.id}_{status_message.id}"
    now = time.time()
    last_time = last_edit_time.get(message_key, 0)
    
    if (now - last_time) > EDIT_THROTTLE_SECONDS:
        try:
            await status_message.edit_text(text)
            last_edit_time[message_key] = now
        except Exception:
            pass

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining"""
    if current <= 0 or (time.time() - start_time) <= 0:
        return "Calculating..."
    
    elapsed = time.time() - start_time
    if elapsed < 0.1: 
        return "Calculating..."
        
    rate = current / elapsed
    if rate == 0:
        return "Calculating..."
    
    remaining_bytes = total - current
    if remaining_bytes <= 0:
        return "Complete"
        
    remaining = remaining_bytes / rate
    
    if remaining < 60:
        return f"{int(remaining)}s"
    elif remaining < 3600:
        return f"{int(remaining // 60)}m {int(remaining % 60)}s"
    else:
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return f"{hours}h {minutes}m"

def get_speed(start_time: float, current: int) -> str:
    """Calculate upload speed"""
    elapsed = time.time() - start_time
    if elapsed <= 0:
        return "0 B/s"
    
    speed = current / elapsed
    if speed < 1024:
        return f"{speed:.1f} B/s"
    elif speed < 1024 * 1024:
        return f"{speed / 1024:.1f} KB/s"
    else:
        return f"{speed / (1024 * 1024):.1f} MB/s"

async def create_default_thumbnail(video_path: str) -> str:
    """Create a default thumbnail from video"""
    thumbnail_path = f"{os.path.splitext(video_path)[0]}.jpg"
    
    try:
        metadata = await get_video_properties(video_path)
        if not metadata or not metadata.get("duration"):
            return None
        
        # Generate thumbnail from middle of video
        thumbnail_time = metadata["duration"] / 2
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-i', video_path,
            '-ss', str(thumbnail_time),
            '-vframes', '1',
            '-c:v', 'mjpeg', '-f', 'image2',
            '-y', thumbnail_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command, 
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if process.returncode == 0 and os.path.exists(thumbnail_path):
            return thumbnail_path
        
    except Exception as e:
        logger.error(f"Error creating thumbnail: {e}")
    
    return None

async def upload_to_telegram(client, video_path: str, status_message, thumbnail_path: str = None, user_name: str = "User"):
    """Upload video to Telegram with progress and logging"""
    try:
        if not os.path.exists(video_path):
            await status_message.edit_text("❌ **Video file not found!**")
            return None
        
        file_size = os.path.getsize(video_path)
        filename = os.path.basename(video_path)
        
        # Check Telegram file size limit (2GB)
        if file_size > 2000000000:  # 2GB
            await status_message.edit_text(
                f"❌ **File too large for Telegram!**\n\n"
                f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                f"📏 **Limit:** `2GB`\n\n"
                f"💡 **Use GoFile for large files**"
            )
            return None
        
        # Create thumbnail if not provided
        if not thumbnail_path:
            thumbnail_path = await create_default_thumbnail(video_path)
        
        # Get video metadata
        metadata = await get_video_properties(video_path)
        duration = int(metadata.get("duration", 0)) if metadata else 0
        
        # Start upload
        await smart_progress_editor(
            status_message,
            f"📤 **Starting Telegram upload...**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"📊 **Size:** `{get_human_readable_size(file_size)}`"
        )
        
        start_time = time.time()
        
        # Progress callback
        async def progress_callback(current, total):
            progress = current / total
            speed = get_speed(start_time, current)
            eta = get_time_left(start_time, current, total)
            
            progress_text = f"""📤 **Uploading to Telegram...**

📁 **File:** `{filename}`
📊 **Total Size:** `{get_human_readable_size(total)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Uploaded:** `{get_human_readable_size(current)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`"""
            
            await smart_progress_editor(status_message, progress_text)
        
        # Upload video
        message = await client.send_video(
            chat_id=status_message.chat.id,
            video=video_path,
            thumb=thumbnail_path,
            duration=duration,
            caption=f"✅ **Merged Video Ready!**\n\n"
                   f"📁 **File:** `{filename}`\n"
                   f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                   f"⏱ **Duration:** `{metadata.get('duration_str', 'Unknown') if metadata else 'Unknown'}`\n"
                   f"🎯 **Resolution:** `{metadata.get('resolution', 'Unknown') if metadata else 'Unknown'}`\n\n"
                   f"🎬 **Merged successfully by {config.BOT_NAME}**",
            progress=progress_callback
        )
        
        # Final success message
        elapsed_time = time.time() - start_time
        await smart_progress_editor(
            status_message,
            f"✅ **Upload Complete!**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
            f"⏱ **Upload Time:** `{int(elapsed_time)}s`\n"
            f"🚀 **Avg Speed:** `{get_speed(start_time, file_size)}`\n\n"
            f"🎬 **Video uploaded successfully!**"
        )
        
        # Log merged file to MERGED_FILE_LOG_CHANNEL
        await send_log_message(
            client,
            f"🎬 **New Merged Video!**\n\n"
            f"👤 **User:** {user_name}\n"
            f"📁 **File:** `{filename}`\n"
            f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
            f"⏱ **Duration:** `{metadata.get('duration_str', 'Unknown') if metadata else 'Unknown'}`\n"
            f"🎯 **Resolution:** `{metadata.get('resolution', 'Unknown') if metadata else 'Unknown'}`\n"
            f"🕐 **Time:** `{time.strftime('%Y-%m-%d %H:%M:%S')}`",
            log_type="merged_file"
        )
        
        # Send copy to merged file log channel if different from current chat
        if config.MERGED_FILE_LOG_CHANNEL and str(config.MERGED_FILE_LOG_CHANNEL) != str(status_message.chat.id):
            try:
                await client.send_video(
                    chat_id=config.MERGED_FILE_LOG_CHANNEL,
                    video=video_path,
                    thumb=thumbnail_path,
                    duration=duration,
                    caption=f"🎬 **Merged Video Log**\n\n"
                           f"👤 **User:** {user_name}\n"
                           f"📁 **File:** `{filename}`\n"
                           f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                           f"⏱ **Duration:** `{metadata.get('duration_str', 'Unknown') if metadata else 'Unknown'}`\n"
                           f"🎯 **Resolution:** `{metadata.get('resolution', 'Unknown') if metadata else 'Unknown'}`\n"
                           f"🕐 **Time:** `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
                )
            except Exception as e:
                logger.error(f"Failed to send to merged file log channel: {e}")
        
        return message
        
    except Exception as e:
        logger.error(f"Telegram upload error: {e}")
        await smart_progress_editor(
            status_message,
            f"❌ **Telegram Upload Failed!**\n\n"
            f"🚨 **Error:** `{str(e)}`\n\n"
            f"💡 **Try GoFile upload instead**"
        )
        return None

class GofileUploader:
    """Enhanced GoFile uploader with progress tracking"""
    
    def __init__(self, token=None):
        self.api_url = "https://api.gofile.io/"
        self.token = token or config.GOFILE_TOKEN
        self.chunk_size = GOFILE_CHUNK_SIZE
        self.session = None

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = ClientSession(
                timeout=ClientTimeout(total=GOFILE_UPLOAD_TIMEOUT)
            )
        return self.session
    
    async def close(self):
        """Close session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def __get_server(self):
        """Get best GoFile server"""
        session = await self._get_session()
        async with session.get(f"{self.api_url}servers") as resp:
            resp.raise_for_status()
            result = await resp.json()
            
            if result.get("status") == "ok":
                servers = result["data"]["servers"]
                selected_server = choice(servers)["name"]
                logger.info(f"Selected GoFile server: {selected_server}")
                return selected_server
            else:
                raise Exception(f"GoFile API error: {result.get('message', 'Unknown error')}")

    async def upload_file(self, file_path: str, status_message=None, user_name: str = "User"):
        """Upload file to GoFile with progress and logging"""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        if file_size > (10 * 1024 * 1024 * 1024):  # 10GB limit
            raise ValueError(f"File size {get_human_readable_size(file_size)} exceeds GoFile limit (10GB)")

        # Get upload server
        if status_message:
            await smart_progress_editor(status_message, "🔗 **Connecting to GoFile servers...**")
        
        try:
            server = await self.__get_server()
            upload_url = f"https://{server}.gofile.io/uploadFile"
        except Exception as e:
            error_msg = f"Failed to get GoFile server: {e}"
            logger.error(error_msg)
            if status_message:
                await status_message.edit_text(f"❌ **GoFile Upload Failed!**\n\n🚨 **Error:** `{error_msg}`")
            raise Exception(error_msg)
        
        if status_message:
            await smart_progress_editor(
                status_message, 
                f"🚀 **Starting GoFile Upload...**\n\n"
                f"📁 **File:** `{filename}`\n"
                f"📊 **Size:** `{get_human_readable_size(file_size)}`"
            )
        
        start_time = time.time()
        
        try:
            session = await self._get_session()
            
            # Create form data
            form = FormData()
            if self.token:
                form.add_field("token", self.token)
            
            # Add file with progress tracking
            with open(file_path, "rb") as f:
                form.add_field("file", f, filename=filename)
                
                async with session.post(upload_url, data=form) as resp:
                    resp.raise_for_status()
                    resp_json = await resp.json()
            
            if resp_json.get("status") == "ok":
                download_page = resp_json["data"]["downloadPage"]
                
                if status_message:
                    elapsed_time = time.time() - start_time
                    await smart_progress_editor(
                        status_message,
                        f"✅ **GoFile Upload Complete!**\n\n"
                        f"📁 **File:** `{filename}`\n"
                        f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                        f"⏱ **Upload Time:** `{int(elapsed_time)}s`\n"
                        f"🚀 **Avg Speed:** `{get_speed(start_time, file_size)}`\n\n"
                        f"🔗 **Download Link:** `{download_page}`"
                    )
                
                # Log merged file upload
                await send_log_message(
                    status_message.from_user.first_name if hasattr(status_message, 'from_user') else None,
                    f"☁️ **GoFile Upload Complete!**\n\n"
                    f"👤 **User:** {user_name}\n"
                    f"📁 **File:** `{filename}`\n"
                    f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                    f"🔗 **Link:** `{download_page}`\n"
                    f"🕐 **Time:** `{time.strftime('%Y-%m-%d %H:%M:%S')}`",
                    log_type="merged_file"
                )
                
                return download_page
            else:
                raise Exception(f"GoFile upload failed: {resp_json.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"GoFile upload error: {e}")
            if status_message:
                await smart_progress_editor(
                    status_message,
                    f"❌ **GoFile Upload Failed!**\n\n"
                    f"🚨 **Error:** `{str(e)}`\n\n"
                    f"💡 **Try Telegram upload instead**"
                )
            raise e
