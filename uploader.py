# uploader.py - Enhanced with Professional Progress Bars
import os
import time
import asyncio
from aiohttp import ClientSession, FormData, ClientTimeout
from random import choice
from config import config  # Assuming config.py exists with GOFILE_TOKEN
from utils import get_human_readable_size, get_progress_bar, get_video_properties
from tenacity import retry, stop_after_attempt, wait_exponential, \
    retry_if_exception_type, RetryError

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 3.0

# --- Configuration for Uploader (You can move these to config.py if preferred) ---
GOFILE_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB chunks for GoFile upload
GOFILE_UPLOAD_TIMEOUT = 3600  # 1 hour timeout for large file uploads
GOFILE_RETRY_ATTEMPTS = 5
GOFILE_RETRY_WAIT_MIN = 1  # seconds
GOFILE_RETRY_WAIT_MAX = 60 # seconds
# --- End Configuration ---

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
            # Silently handle rate limits and other common Telegram API errors
            # print(f"Error editing message: {e}") # Uncomment for debugging
            pass

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining."""
    if current <= 0 or (time.time() - start_time) <= 0:
        return "Calculating..."
    
    elapsed = time.time() - start_time
    # Avoid division by zero if elapsed is too small
    if elapsed < 0.1: 
        return "Calculating..."
        
    rate = current / elapsed
    if rate == 0: # Avoid division by zero if no data is transferred yet
        return "Calculating..."
    
    remaining_bytes = total - current
    if remaining_bytes <= 0:
        return "0s" # Already done or no bytes remaining
        
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
            print(f"Error creating default thumbnail (ffmpeg exit code {process.returncode}): {stderr.decode().strip()}")
            return None
        
        return thumbnail_path if os.path.exists(thumbnail_path) else None
        
    except Exception as e:
        print(f"Exception creating thumbnail for '{video_path}': {e}")
        return None

class GofileUploader:
    """Enhanced GoFile uploader with real-time progress tracking and retries."""
    
    def __init__(self, token=None):
        self.api_url = "https://api.gofile.io/"
        self.token = token or getattr(config, 'GOFILE_TOKEN', None)
        if not self.token:
            print("Warning: GOFILE_TOKEN not found in config. GoFile uploads might be anonymous.")
        self.chunk_size = GOFILE_CHUNK_SIZE
        self.session = None # Managed asynchronously

    async def _get_session(self):
        """Get or create an aiohttp ClientSession."""
        if self.session is None or self.session.closed:
            self.session = ClientSession(
                timeout=ClientTimeout(total=GOFILE_UPLOAD_TIMEOUT)
            )
        return self.session
    
    async def close(self):
        """Close the aiohttp ClientSession."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    @retry(
        stop=stop_after_attempt(GOFILE_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=GOFILE_RETRY_WAIT_MIN, max=GOFILE_RETRY_WAIT_MAX),
        retry=retry_if_exception_type(Exception), # Retries on any exception, fine for network issues
        reraise=True
    )
    async def __get_server(self):
        """Get the best GoFile server for uploading with retries."""
        print("Attempting to get GoFile server...")
        session = await self._get_session()
        async with session.get(f"{self.api_url}servers") as resp:
            resp.raise_for_status()
            result = await resp.json()
            
            if result.get("status") == "ok":
                servers = result["data"]["servers"]
                # GoFile recommends choosing a random server if no specific criteria.
                # For robustness, we can try to pick based on country or load in future.
                selected_server = choice(servers)["name"]
                print(f"Selected GoFile server: {selected_server}")
                return selected_server
            else:
                raise Exception(f"GoFile API error getting server: {result.get('message', 'Unknown error')}")
    
    async def upload_file(self, file_path: str, status_message=None):
        """Upload file to GoFile with real-time progress tracking and retries."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        if file_size > (10 * 1024 * 1024 * 1024): # GoFile often has a 10GB soft limit for free users
            raise ValueError(f"File size {get_human_readable_size(file_size)} exceeds GoFile recommended limit (10GB).")

        # Get upload server with retry logic
        try:
            if status_message:
                await smart_progress_editor(status_message, "🔗 **Connecting to GoFile servers...**")
            server = await self.__get_server()
            upload_url = f"https://{server}.gofile.io/uploadFile"
        except RetryError as e:
            error_msg = f"Failed to get GoFile server after multiple retries: {e.last_attempt.exception()}"
            print(error_msg)
            if status_message:
                await status_message.edit_text(
                    f"❌ **GoFile Upload Failed!**\n\n"
                    f"🚨 **Error:** `{error_msg}`\n\n"
                    f"💡 **Tip:** GoFile servers might be busy. Try again later."
                )
            raise Exception(error_msg) from e
        except Exception as e:
            error_msg = f"Error getting GoFile server: {e}"
            print(error_msg)
            if status_message:
                await status_message.edit_text(
                    f"❌ **GoFile Upload Failed!**\n\n"
                    f"🚨 **Error:** `{error_msg}`\n\n"
                    f"💡 **Tip:** Check internet connection or GoFile status."
                )
            raise e
        
        if status_message:
            await smart_progress_editor(
                status_message, 
                f"🚀 **Starting GoFile Upload...**\n\n📁 **File:** `{filename}`\n📊 **Size:** `{get_human_readable_size(file_size)}`"
            )
        
        start_time = time.time()
        uploaded_bytes = 0
        
        try:
            session = await self._get_session()
            form = FormData()
            if self.token:
                form.add_field("token", self.token)
            
            # --- Real-time progress tracking for GoFile upload ---
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break # End of file
                    
                    # For GoFile, we add the file field only once with the first chunk
                    # and then subsequent chunks are part of the stream.
                    # However, aiohttp's FormData manages multipart encoding.
                    # The most straightforward way to stream with progress is to
                    # wrap the file object or use a custom data producer.
                    
                    # A more robust approach for actual progress involves
                    # sending chunks manually, but aiohttp's FormData
                    # can stream an open file handle, and we can hook into
                    # the file's read method for progress.
                    
                    # Let's use a custom file-like object for accurate progress
                    # as `FormData` does not expose `on_progress` for fields.
                    
                    async def file_sender():
                        nonlocal uploaded_bytes
                        with open(file_path, 'rb') as f_stream:
                            while True:
                                chunk_data = f_stream.read(self.chunk_size)
                                if not chunk_data:
                                    break
                                uploaded_bytes += len(chunk_data)
                                
                                # Update progress message
                                if status_message:
                                    progress_percent = uploaded_bytes / file_size
                                    speed = get_speed(start_time, uploaded_bytes)
                                    eta = get_time_left(start_time, uploaded_bytes, file_size)
                                    
                                    progress_text = f"""
🔗 **Uploading to GoFile.io...**

📁 **File:** `{filename}`
📊 **Total Size:** `{get_human_readable_size(file_size)}`

{get_progress_bar(progress_percent)} `{progress_percent:.1%}`

📈 **Uploaded:** `{get_human_readable_size(uploaded_bytes)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
"""
                                    await smart_progress_editor(status_message, progress_text.strip())
                                
                                yield chunk_data
                                # Give control back to event loop
                                await asyncio.sleep(0.001) 
                    
                    form.add_field("file", file_sender(), filename=filename, content_type="application/octet-stream")
                    break # Only add the field once
            
            # Use tenacity for retries on the actual POST request
            @retry(
                stop=stop_after_attempt(GOFILE_RETRY_ATTEMPTS),
                wait=wait_exponential(multiplier=1, min=GOFILE_RETRY_WAIT_MIN, max=GOFILE_RETRY_WAIT_MAX),
                retry=retry_if_exception_type(Exception), # Retries on any exception from the POST
                reraise=True
            )
            async def _perform_upload():
                async with session.post(upload_url, data=form) as resp:
                    resp.raise_for_status() # Raise an exception for bad status codes (4xx, 5xx)
                    return await resp.json()
            
            resp_json = await _perform_upload()
            
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
        
        except RetryError as e:
            error_msg = f"GoFile upload failed after multiple retries for '{filename}': {e.last_attempt.exception()}"
            print(error_msg)
            if status_message:
                await status_message.edit_text(
                    f"❌ **GoFile Upload Failed!**\n\n"
                    f"📁 **File:** `{filename}`\n"
                    f"🚨 **Error:** `{error_msg}`\n\n"
                    f"💡 **Tip:** Check GoFile status or try again."
                )
            raise Exception(error_msg) from e
        except Exception as e:
            print(f"GoFile upload encountered an error for '{filename}': {e}")
            if status_message:
                await status_message.edit_text(
                    f"❌ **GoFile Upload Failed!**\n\n"
                    f"📁 **File:** `{filename}`\n"
                    f"🚨 **Error:** `{str(e)}`\n\n"
                    f"💡 **Tip:** Try again or contact support if the problem persists."
                )
            raise e
        finally:
            await self.close() # Ensure session is closed after upload attempt

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
        final_filename = f"{custom_filename}.mkv" # Assuming MKV is the desired output format for Telegram
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
            if (now - last_progress_time) < EDIT_THROTTLE_SECONDS and current < total: # Use global throttle for consistency
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
        except Exception as e:
            print(f"Failed to delete status message after Telegram upload: {e}")
        
        return True
    
    except Exception as e:
        error_text = f"""
❌ **Telegram Upload Failed!**

📁 **File:** `{custom_filename}.mkv`
🚨 **Error:** `{type(e).__name__}: {str(e)}`

💡 **Possible Solutions:**
• Check file size (max 2GB for bots)
• Ensure stable internet connection
• Try again after a few minutes
• Contact support if problem persists
"""
        print(f"Telegram upload failed for '{custom_filename}.mkv': {e}")
        await status_message.edit_text(error_text.strip())
        return False
    
    finally:
        # Cleanup default thumbnail if created
        if is_default_thumb_created and thumb_to_upload and os.path.exists(thumb_to_upload):
            try:
                os.remove(thumb_to_upload)
                print(f"Cleaned up default thumbnail: {thumb_to_upload}")
            except Exception as e:
                print(f"Error cleaning up thumbnail '{thumb_to_upload}': {e}")

# Additional utility function for file validation
def validate_video_file(file_path: str) -> tuple[bool, str]:
    """Validate video file before upload."""
    if not os.path.exists(file_path):
        return False, "File not found"
    
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        return False, "File is empty"
    
    # Telegram bot file size limit is 2GB
    if file_size > 2 * 1024 * 1024 * 1024:
        return False, f"File too large: {get_human_readable_size(file_size)} (Telegram max 2GB)"
    
    # Check file extension
    valid_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v']
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext not in valid_extensions:
        return False, f"Unsupported format: {file_ext}. Valid: {', '.join(valid_extensions)}"
    
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

# Assume get_progress_bar in utils.py uses get_styled_progress_bar with a default style
# Example implementation in utils.py (if not already there):
# def get_progress_bar(progress: float, length: int = 20) -> str:
#     return get_styled_progress_bar(progress, length, "default")
