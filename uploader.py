# uploader.py - Enhanced with Professional Progress Bars
import os
import time
import asyncio
from aiohttp import ClientSession, FormData, ClientTimeout
from random import choice
from config import config
from utils import get_human_readable_size, get_progress_bar, get_video_properties
from tenacity import retry, stop_after_attempt, wait_exponential, \
    retry_if_exception_type, RetryError

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 3.0

# Configuration for Uploader
GOFILE_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB chunks
GOFILE_UPLOAD_TIMEOUT = 3600  # 1 hour timeout
GOFILE_RETRY_ATTEMPTS = 5
GOFILE_RETRY_WAIT_MIN = 1
GOFILE_RETRY_WAIT_MAX = 60

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
            pass

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining."""
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
        return "0s"

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

async def create_default_thumbnail(video_path: str):
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
        self.session = None

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
        retry=retry_if_exception_type(Exception),
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

        if file_size > (10 * 1024 * 1024 * 1024):  # 10GB limit
            raise ValueError(f"File size {get_human_readable_size(file_size)} exceeds GoFile limit (10GB).")

        # Get upload server
        try:
            if status_message:
                await smart_progress_editor(status_message, "🔗 **Connecting to GoFile servers...**")
            server = await self.__get_server()
            upload_url = f"https://{server}.gofile.io/uploadFile"
        except RetryError as e:
            error_msg = f"Failed to get GoFile server: {e.last_attempt.exception()}"
            if status_message:
                await status_message.edit_text(f"❌ **GoFile Upload Failed!**\n\n🚨 **Error:** `{error_msg}`")
            raise Exception(error_msg) from e

        if status_message:
            await smart_progress_editor(
                status_message,
                f"🚀 **Starting GoFile Upload...**\n\n📁 **File:** `{filename}`\n📊 **Size:** `{get_human_readable_size(file_size)}`"
            )

        start_time = time.time()
        uploaded_bytes = 0

        try:
            session = await self._get_session()
            
            # Create form data
            form = FormData()
            if self.token:
                form.add_field("token", self.token)

            # Add file field
            with open(file_path, 'rb') as f:
                form.add_field("file", f, filename=filename, content_type="application/octet-stream")

            # Upload with progress tracking
            async with session.post(upload_url, data=form) as resp:
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
                    f"🚨 **Error:** `{str(e)}`"
                )
            raise e
        finally:
            await self.close()

async def upload_to_telegram(client, chat_id: int, file_path: str, status_message, caption: str = None, custom_thumbnail: str = None):
    """Upload video file to Telegram with progress tracking."""
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        # Create thumbnail if not provided
        thumbnail_path = custom_thumbnail
        if not thumbnail_path:
            thumbnail_path = await create_default_thumbnail(file_path)

        if status_message:
            await smart_progress_editor(
                status_message,
                f"📤 **Uploading to Telegram...**\n\n"
                f"📁 **File:** `{filename}`\n"
                f"📊 **Size:** `{get_human_readable_size(file_size)}`"
            )

        # Progress callback for upload
        def progress_callback(current, total):
            if status_message:
                progress_percent = current / total
                progress_text = f"""
📤 **Uploading to Telegram...**
📁 **File:** `{filename}`
📊 **Total Size:** `{get_human_readable_size(total)}`
{get_progress_bar(progress_percent)} `{progress_percent:.1%}`
📈 **Uploaded:** `{get_human_readable_size(current)}`
📡 **Status:** {'Complete!' if current >= total else 'Uploading...'}
"""
                asyncio.create_task(smart_progress_editor(status_message, progress_text.strip()))

        # Upload as video
        if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')):
            # Get video properties for metadata
            video_props = await get_video_properties(file_path)
            duration = video_props.get('duration', 0) if video_props else 0
            width = video_props.get('width', 0) if video_props else 0
            height = video_props.get('height', 0) if video_props else 0

            message = await client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                duration=duration,
                width=width,
                height=height,
                thumb=thumbnail_path,
                progress=progress_callback
            )
        else:
            # Upload as document
            message = await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                thumb=thumbnail_path,
                progress=progress_callback
            )

        # Cleanup thumbnail if we created it
        if thumbnail_path and thumbnail_path != custom_thumbnail:
            try:
                os.remove(thumbnail_path)
            except:
                pass

        return message

    except Exception as e:
        if status_message:
            await status_message.edit_text(f"❌ **Telegram Upload Failed!**\n\n🚨 **Error:** `{str(e)}`")
        raise
