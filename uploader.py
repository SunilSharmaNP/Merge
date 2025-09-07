# uploader.py - ENHANCED with complete merged file logging for both TG and GoFile
import os
import time
import asyncio
from aiohttp import ClientSession, FormData, ClientTimeout
from random import choice
from config import config
from utils import get_human_readable_size, get_progress_bar, get_video_properties
import logging
from helpers import send_log_message
from database import db
from datetime import datetime

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

async def upload_to_telegram(client, chat_id: int, video_path: str, custom_filename: str = None, thumbnail_path: str = None, status_message = None):
    """Enhanced Telegram upload with comprehensive merged file logging"""
    try:
        if not os.path.exists(video_path):
            if status_message:
                await status_message.edit_text("❌ **Video file not found!**")
            return False
        
        file_size = os.path.getsize(video_path)
        filename = custom_filename or os.path.splitext(os.path.basename(video_path))[0]
        final_filename = f"{filename}.mp4"
        
        # Check Telegram file size limit (2GB)
        if file_size > 2000000000:  # 2GB
            if status_message:
                await status_message.edit_text(
                    f"❌ **File too large for Telegram!**\n\n"
                    f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                    f"📏 **Limit:** `2GB`\n\n"
                    f"💡 **Use GoFile for large files**"
                )
            return False
        
        # Create thumbnail if not provided
        if not thumbnail_path:
            thumbnail_path = await create_default_thumbnail(video_path)
        
        # Get video metadata
        metadata = await get_video_properties(video_path)
        duration = int(metadata.get("duration", 0)) if metadata else 0
        resolution = f"{metadata.get('width', 0)}x{metadata.get('height', 0)}" if metadata else "Unknown"
        
        # Start upload
        if status_message:
            await smart_progress_editor(
                status_message,
                f"📤 **Starting Telegram upload...**\n\n"
                f"📁 **File:** `{final_filename}`\n"
                f"📊 **Size:** `{get_human_readable_size(file_size)}`"
            )
        
        start_time = time.time()
        
        # Progress callback
        async def progress_callback(current, total):
            if not status_message:
                return
                
            progress = current / total
            speed = get_speed(start_time, current)
            eta = get_time_left(start_time, current, total)
            
            progress_text = f"""📤 **Uploading to Telegram...**

📁 **File:** `{final_filename}`
📊 **Total Size:** `{get_human_readable_size(total)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Uploaded:** `{get_human_readable_size(current)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`"""
            
            await smart_progress_editor(status_message, progress_text)
        
        # Upload video
        message = await client.send_video(
            chat_id=chat_id,
            video=video_path,
            thumb=thumbnail_path,
            duration=duration,
            caption=f"✅ **Merged Video Ready!**\n\n"
                   f"📁 **File:** `{final_filename}`\n"
                   f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                   f"⏱ **Duration:** `{duration}s`\n"
                   f"🎯 **Resolution:** `{resolution}`\n\n"
                   f"🎬 **Merged successfully by {config.BOT_NAME}**",
            progress=progress_callback
        )
        
        # Calculate upload time
        elapsed_time = time.time() - start_time
        
        # Final success message
        if status_message:
            await smart_progress_editor(
                status_message,
                f"✅ **Telegram Upload Complete!**\n\n"
                f"📁 **File:** `{final_filename}`\n"
                f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                f"⏱ **Upload Time:** `{int(elapsed_time)}s`\n"
                f"🚀 **Avg Speed:** `{get_speed(start_time, file_size)}`\n\n"
                f"🎬 **Video uploaded successfully!**"
            )
        
        # Get user info for logging
        try:
            user_info = await client.get_chat(chat_id)
            if hasattr(user_info, 'first_name'):
                user_name = user_info.first_name or "Unknown User"
                user_id = user_info.id
            else:
                user_name = "Unknown User"
                user_id = chat_id
        except:
            user_name = "Unknown User"
            user_id = chat_id
        
        # Log to database
        await db.log_file_activity(
            user_id=user_id,
            file_name=final_filename,
            file_size=file_size,
            upload_type="telegram_upload",
            file_url=None
        )
        
        # Send merged file log to FLOG channel
        await send_log_message(
            client, "merge_activity",
            f"📤 **Merged File Uploaded to Telegram**\n\n"
            f"👤 **User:** {user_name} (`{user_id}`)\n"
            f"📁 **Filename:** `{final_filename}`\n"
            f"📊 **File Size:** `{get_human_readable_size(file_size)}`\n"
            f"⏱ **Duration:** `{duration}s`\n"
            f"🎯 **Resolution:** `{resolution}`\n"
            f"🚀 **Upload Speed:** `{get_speed(start_time, file_size)}`\n"
            f"⏰ **Upload Time:** `{int(elapsed_time)}s`\n"
            f"📅 **Date:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"📊 **Platform:** Telegram"
        )
        
        # Send copy to FLOG channel if configured and different from current chat
        if hasattr(config, 'FLOG_CHANNEL') and config.FLOG_CHANNEL and str(config.FLOG_CHANNEL) != str(chat_id):
            try:
                await client.send_video(
                    chat_id=config.FLOG_CHANNEL,
                    video=video_path,
                    thumb=thumbnail_path,
                    duration=duration,
                    caption=f"🎬 **Merged Video Log - Telegram**\n\n"
                           f"👤 **User:** {user_name} (`{user_id}`)\n"
                           f"📁 **File:** `{final_filename}`\n"
                           f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                           f"⏱ **Duration:** `{duration}s`\n"
                           f"🎯 **Resolution:** `{resolution}`\n"
                           f"📅 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                           f"📊 **Platform:** Telegram"
                )
                logger.info(f"Merged file logged to FLOG channel: {final_filename}")
            except Exception as e:
                logger.error(f"Failed to send to FLOG channel: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Telegram upload error: {e}")
        if status_message:
            await smart_progress_editor(
                status_message,
                f"❌ **Telegram Upload Failed!**\n\n"
                f"🚨 **Error:** `{str(e)}`\n\n"
                f"💡 **Try GoFile upload instead**"
            )
        return False

class GofileUploader:
    """Enhanced GoFile uploader with comprehensive merged file logging"""
    
    def __init__(self, token=None):
        self.api_url = "https://api.gofile.io/"
        self.token = token or getattr(config, 'GOFILE_TOKEN', None)
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

    async def upload_file(self, client, user_id: int, file_path: str, custom_filename: str = None, status_message=None):
        """Enhanced GoFile upload with comprehensive merged file logging"""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        filename = custom_filename or os.path.splitext(os.path.basename(file_path))[0]
        final_filename = f"{filename}.mp4"
        
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
                f"📁 **File:** `{final_filename}`\n"
                f"📊 **Size:** `{get_human_readable_size(file_size)}`"
            )
        
        start_time = time.time()
        
        try:
            session = await self._get_session()
            
            # Create form data
            form = FormData()
            if self.token:
                form.add_field("token", self.token)
            
            # Track upload progress
            uploaded = 0
            
            # Custom file reader with progress
            async def track_upload_progress():
                nonlocal uploaded
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(self.chunk_size)
                        if not chunk:
                            break
                        uploaded += len(chunk)
                        
                        if status_message:
                            progress = uploaded / file_size
                            speed = get_speed(start_time, uploaded)
                            eta = get_time_left(start_time, uploaded, file_size)
                            
                            progress_text = f"""🔗 **Uploading to GoFile...**

📁 **File:** `{final_filename}`
📊 **Total Size:** `{get_human_readable_size(file_size)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Uploaded:** `{get_human_readable_size(uploaded)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`"""
                            
                            await smart_progress_editor(status_message, progress_text)
                        
                        yield chunk
            
            # Add file to form
            form.add_field("file", track_upload_progress(), filename=final_filename)
            
            # Upload file
            async with session.post(upload_url, data=form) as resp:
                resp.raise_for_status()
                result = await resp.json()
            
            if result.get("status") != "ok":
                raise Exception(f"GoFile upload failed: {result.get('message', 'Unknown error')}")
            
            file_data = result["data"]
            download_url = file_data["downloadPage"]
            file_id = file_data["fileId"]
            
            # Calculate upload time
            elapsed_time = time.time() - start_time
            
            # Get user info for logging
            try:
                user_info = await client.get_chat(user_id)
                if hasattr(user_info, 'first_name'):
                    user_name = user_info.first_name or "Unknown User"
                else:
                    user_name = "Unknown User"
            except:
                user_name = "Unknown User"
            
            # Get video metadata for logging
            metadata = await get_video_properties(file_path)
            duration = int(metadata.get("duration", 0)) if metadata else 0
            resolution = f"{metadata.get('width', 0)}x{metadata.get('height', 0)}" if metadata else "Unknown"
            
            # Log to database
            await db.log_file_activity(
                user_id=user_id,
                file_name=final_filename,
                file_size=file_size,
                upload_type="gofile_upload",
                file_url=download_url
            )
            
            # Send merged file log to FLOG channel
            await send_log_message(
                client, "merge_activity",
                f"🔗 **Merged File Uploaded to GoFile**\n\n"
                f"👤 **User:** {user_name} (`{user_id}`)\n"
                f"📁 **Filename:** `{final_filename}`\n"
                f"📊 **File Size:** `{get_human_readable_size(file_size)}`\n"
                f"⏱ **Duration:** `{duration}s`\n"
                f"🎯 **Resolution:** `{resolution}`\n"
                f"🚀 **Upload Speed:** `{get_speed(start_time, file_size)}`\n"
                f"⏰ **Upload Time:** `{int(elapsed_time)}s`\n"
                f"🔗 **Download URL:** {download_url}\n"
                f"📅 **Date:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"📊 **Platform:** GoFile\n"
                f"🆔 **File ID:** `{file_id}`"
            )
            
            # Send text log to FLOG channel if configured
            if hasattr(config, 'FLOG_CHANNEL') and config.FLOG_CHANNEL:
                try:
                    await client.send_message(
                        chat_id=config.FLOG_CHANNEL,
                        text=f"🔗 **Merged Video Log - GoFile**\n\n"
                             f"👤 **User:** {user_name} (`{user_id}`)\n"
                             f"📁 **File:** `{final_filename}`\n"
                             f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                             f"⏱ **Duration:** `{duration}s`\n"
                             f"🎯 **Resolution:** `{resolution}`\n"
                             f"🔗 **URL:** {download_url}\n"
                             f"📅 **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                             f"📊 **Platform:** GoFile\n"
                             f"🆔 **File ID:** `{file_id}`"
                    )
                    logger.info(f"Merged file logged to FLOG channel: {final_filename}")
                except Exception as e:
                    logger.error(f"Failed to send to FLOG channel: {e}")
            
            # Final success message
            if status_message:
                await smart_progress_editor(
                    status_message,
                    f"✅ **GoFile Upload Complete!**\n\n"
                    f"📁 **File:** `{final_filename}`\n"
                    f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                    f"⏱ **Upload Time:** `{int(elapsed_time)}s`\n"
                    f"🚀 **Avg Speed:** `{get_speed(start_time, file_size)}`\n"
                    f"🔗 **Download:** [Click Here]({download_url})\n\n"
                    f"🎬 **File uploaded successfully!**"
                )
            
            return {
                "success": True,
                "download_url": download_url,
                "file_id": file_id,
                "upload_time": elapsed_time,
                "file_size": file_size
            }
            
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
        
        finally:
            await self.close()

# Global uploader instance
gofile_uploader = GofileUploader()

# Convenience functions
async def upload_to_gofile(client, user_id: int, file_path: str, custom_filename: str = None, status_message=None):
    """Convenience function for GoFile upload"""
    return await gofile_uploader.upload_file(client, user_id, file_path, custom_filename, status_message)

# Enhanced helper function
def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    return get_human_readable_size(size_bytes)
