# uploader.py - Enhanced with Professional Progress Bars
import os
import time
import asyncio
from aiohttp import ClientSession, FormData
from random import choice
from config import config
from utils import get_human_readable_size, get_progress_bar, get_video_properties

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 3.0

async def smart_progress_editor(status_message, text: str):
    """Smart progress editor with throttling to avoid flood limits."""
    if not status_message or not hasattr(status_message, 'chat'):
        return
    
    message_key = f"{status_message.chat.id}_{status_message.id}"
    now = time.time()
    last_time = last_edit_time.get(message_key, 0)
    
    if (now - last_time) > EDIT_THROTTLE_SECONDS:
        try:
            await status_message.edit_text(text)
            last_edit_time[message_key] = now
        except Exception as e:
            # Silently handle rate limits and other errors
            pass

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining."""
    if current <= 0:
        return "Calculating..."
    
    elapsed = time.time() - start_time
    rate = current / elapsed
    remaining = (total - current) / rate
    
    if remaining < 60:
        return f"{int(remaining)}s"
    elif remaining < 3600:
        return f"{int(remaining // 60)}m {int(remaining % 60)}s"
    else:
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return f"{hours}h {minutes}m"

def get_speed(start_time: float, current: int) -> str:
    """Calculate upload/download speed."""
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

async def create_default_thumbnail(video_path: str) -> str | None:
    """Create a default thumbnail from video."""
    thumbnail_path = f"{os.path.splitext(video_path)[0]}.jpg"
    
    try:
        metadata = await get_video_properties(video_path)
        if not metadata or not metadata.get("duration"):
            print(f"Could not get duration for '{video_path}'. Skipping default thumbnail.")
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
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            print(f"Error creating default thumbnail: {stderr.decode().strip()}")
            return None
        
        return thumbnail_path if os.path.exists(thumbnail_path) else None
        
    except Exception as e:
        print(f"Exception creating thumbnail: {e}")
        return None

class GofileUploader:
    """Enhanced GoFile uploader with progress tracking."""
    
    def __init__(self, token=None):
        self.api_url = "https://api.gofile.io/"
        self.token = token or config.GOFILE_TOKEN
        self.chunk_size = 8192  # 8KB chunks for progress tracking
    
    async def __get_server(self):
        """Get the best GoFile server for uploading."""
        try:
            async with ClientSession() as session:
                async with session.get(f"{self.api_url}servers") as resp:
                    resp.raise_for_status()
                    result = await resp.json()
                    
                    if result.get("status") == "ok":
                        servers = result["data"]["servers"]
                        # Choose server with best performance (random for now)
                        return choice(servers)["name"]
                    else:
                        raise Exception(f"GoFile API error: {result}")
        except Exception as e:
            print(f"Error getting GoFile server: {e}")
            # Fallback to store1
            return "store1"
    
    async def upload_file(self, file_path: str, status_message=None):
        """Upload file to GoFile with progress tracking."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        # Get upload server
        if status_message:
            await smart_progress_editor(status_message, "🔗 **Connecting to GoFile servers...**")
        
        server = await self.__get_server()
        upload_url = f"https://{server}.gofile.io/uploadFile"
        
        if status_message:
            await smart_progress_editor(
                status_message, 
                f"🚀 **Starting GoFile Upload...**\n\n📁 **File:** `{filename}`\n📊 **Size:** `{get_human_readable_size(file_size)}`"
            )
        
        start_time = time.time()
        
        try:
            # Prepare form data
            data = FormData()
            if self.token:
                data.add_field("token", self.token)
            
            # Custom file field with progress tracking
            with open(file_path, "rb") as f:
                # Read file content
                file_content = f.read()
                data.add_field("file", file_content, filename=filename)
            
            # Upload with progress simulation (since aiohttp doesn't support upload progress directly)
            async with ClientSession() as session:
                if status_message:
                    # Simulate upload progress
                    asyncio.create_task(self._simulate_upload_progress(
                        status_message, filename, file_size, start_time
                    ))
                
                async with session.post(upload_url, data=data) as resp:
                    resp.raise_for_status()
                    resp_json = await resp.json()
                    
                    if resp_json.get("status") == "ok":
                        download_page = resp_json["data"]["downloadPage"]
                        
                        if status_message:
                            elapsed_time = time.time() - start_time
                            await status_message.edit_text(
                                f"✅ **GoFile Upload Complete!**\n\n"
                                f"📁 **File:** `{filename}`\n"
                                f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
                                f"⏱ **Time:** `{elapsed_time:.1f}s`\n"
                                f"🔗 **Link:** {download_page}\n\n"
                                f"💡 **Note:** Links expire after 10 days of inactivity."
                            )
                        
                        return download_page
                    else:
                        error_msg = resp_json.get("message", "Unknown error")
                        raise Exception(f"GoFile upload failed: {error_msg}")
        
        except Exception as e:
            if status_message:
                await status_message.edit_text(
                    f"❌ **GoFile Upload Failed!**\n\n"
                    f"📁 **File:** `{filename}`\n"
                    f"🚨 **Error:** `{str(e)}`\n\n"
                    f"💡 **Tip:** Try again or contact support if the problem persists."
                )
            raise e
    
    async def _simulate_upload_progress(self, status_message, filename: str, file_size: int, start_time: float):
        """Simulate upload progress for better UX."""
        try:
            # Simulate progress over time
            total_duration = max(10, file_size / (1024 * 1024))  # At least 10 seconds, 1MB/s rate
            steps = 20
            
            for i in range(steps + 1):
                if i == steps:
                    break  # Don't show 100% until actual completion
                
                progress = i / steps
                current_bytes = int(file_size * progress)
                
                elapsed = time.time() - start_time
                speed = get_speed(start_time, current_bytes) if current_bytes > 0 else "0 B/s"
                eta = get_time_left(start_time, current_bytes, file_size) if current_bytes > 0 else "Calculating..."
                
                progress_text = f"""
🔗 **Uploading to GoFile.io...**

📁 **File:** `{filename}`
📊 **Size:** `{get_human_readable_size(file_size)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Uploaded:** `{get_human_readable_size(current_bytes)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
"""
                await smart_progress_editor(status_message, progress_text.strip())
                
                # Wait based on expected duration
                await asyncio.sleep(total_duration / steps)
        
        except Exception:
            # If simulation fails, just continue silently
            pass

async def upload_to_telegram(client, chat_id: int, file_path: str, status_message, custom_thumbnail: str | None, custom_filename: str):
    """Enhanced Telegram upload with professional progress bar."""
    is_default_thumb_created = False
    thumb_to_upload = custom_thumbnail
    
    try:
        # Handle thumbnail
        if not thumb_to_upload:
            await smart_progress_editor(status_message, "🖼 **Analyzing video for thumbnail...**")
            thumb_to_upload = await create_default_thumbnail(file_path)
            if thumb_to_upload:
                is_default_thumb_created = True
                await smart_progress_editor(status_message, "✅ **Thumbnail created successfully!**")
        
        # Get video metadata
        await smart_progress_editor(status_message, "🔍 **Extracting video metadata...**")
        metadata = await get_video_properties(file_path)
        
        duration = metadata.get('duration', 0) if metadata else 0
        width = metadata.get('width', 0) if metadata else 0
        height = metadata.get('height', 0) if metadata else 0
        file_size = os.path.getsize(file_path)
        
        # Prepare upload
        final_filename = f"{custom_filename}.mkv"
        caption = f"""
🎬 **Video Upload Complete!**

📁 **File:** `{final_filename}`
📊 **Size:** `{get_human_readable_size(file_size)}`
⏱ **Duration:** `{duration // 60}:{duration % 60:02d}`
📐 **Resolution:** `{width}x{height}`
🎯 **Quality:** `High Definition`
"""
        
        # Progress tracking variables
        start_time = time.time()
        last_progress_time = start_time
        
        async def progress(current, total):
            """Enhanced progress callback with detailed information."""
            nonlocal last_progress_time
            
            # Throttle progress updates
            now = time.time()
            if (now - last_progress_time) < 2.0 and current < total:
                return
            last_progress_time = now
            
            progress_percent = current / total
            speed = get_speed(start_time, current)
            eta = get_time_left(start_time, current, total)
            
            progress_text = f"""
📤 **Uploading to Telegram...**

📁 **File:** `{final_filename}`
📊 **Total Size:** `{get_human_readable_size(total)}`

{get_progress_bar(progress_percent)} `{progress_percent:.1%}`

📈 **Uploaded:** `{get_human_readable_size(current)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
📡 **Status:** {'Complete!' if current >= total else 'Uploading...'}
"""
            await smart_progress_editor(status_message, progress_text.strip())
        
        # Upload the video
        await smart_progress_editor(status_message, f"🚀 **Starting upload to Telegram...**\n\n📁 **File:** `{final_filename}`")
        
        await client.send_video(
            chat_id=chat_id,
            video=file_path,
            caption=caption.strip(),
            file_name=final_filename,
            duration=duration,
            width=width,
            height=height,
            thumb=thumb_to_upload,
            progress=progress
        )
        
        # Success - delete status message
        try:
            await status_message.delete()
        except:
            pass
        
        return True
    
    except Exception as e:
        error_text = f"""
❌ **Telegram Upload Failed!**

📁 **File:** `{custom_filename}.mkv`
🚨 **Error:** `{str(e)}`

💡 **Possible Solutions:**
• Check file size (max 2GB for bots)
• Ensure stable internet connection
• Try again after a few minutes
• Contact support if problem persists
"""
        await status_message.edit_text(error_text.strip())
        return False
    
    finally:
        # Cleanup default thumbnail if created
        if is_default_thumb_created and thumb_to_upload and os.path.exists(thumb_to_upload):
            try:
                os.remove(thumb_to_upload)
            except:
                pass

# Additional utility function for file validation
def validate_video_file(file_path: str) -> tuple[bool, str]:
    """Validate video file before upload."""
    if not os.path.exists(file_path):
        return False, "File not found"
    
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        return False, "File is empty"
    
    if file_size > 2 * 1024 * 1024 * 1024:  # 2GB limit for Telegram bots
        return False, f"File too large: {get_human_readable_size(file_size)} (max 2GB)"
    
    # Check file extension
    valid_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v']
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext not in valid_extensions:
        return False, f"Unsupported format: {file_ext}"
    
    return True, "Valid"

# Progress bar styles
PROGRESS_STYLES = {
    "default": {"filled": "█", "empty": "░"},
    "modern": {"filled": "▰", "empty": "▱"},
    "dots": {"filled": "●", "empty": "○"},
    "blocks": {"filled": "■", "empty": "□"},
}

def get_styled_progress_bar(progress: float, length: int = 20, style: str = "default") -> str:
    """Get a styled progress bar."""
    style_chars = PROGRESS_STYLES.get(style, PROGRESS_STYLES["default"])
    filled_len = int(length * progress)
    return (
        style_chars["filled"] * filled_len + 
        style_chars["empty"] * (length - filled_len)
    )
