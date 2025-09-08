# downloader.py - Enhanced with Professional Progress Bars and Robust Error Handling
import aiohttp
import asyncio
import os
import time
import logging
from datetime import datetime
from config import config
from utils import get_human_readable_size, get_progress_bar
from tenacity import retry, stop_after_attempt, wait_exponential, \
    retry_if_exception_type, RetryError
from urllib.parse import urlparse, unquote
import re
import requests
from hashlib import sha256
import json

# Set up logging for better debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 3.0

# Configuration for Downloader
DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks
DOWNLOAD_CONNECT_TIMEOUT = 60
DOWNLOAD_READ_TIMEOUT = 600
DOWNLOAD_RETRY_ATTEMPTS = 5
DOWNLOAD_RETRY_WAIT_MIN = 5
DOWNLOAD_RETRY_WAIT_MAX = 60
MAX_URL_LENGTH = 2048

# Gofile.io configuration
GOFILE_API_URL = "https://api.gofile.io"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
PASSWORD_ERROR_MESSAGE = "ERROR: Password is required for this link\n\nUse: /cmd {link} password"

class DirectDownloadLinkException(Exception):
    pass

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
            logger.debug(f"Progress update failed: {e}")

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining."""
    if current <= 0 or total <= 0:
        return "Calculating..."

    elapsed = time.time() - start_time
    if elapsed <= 0.1:
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
    """Calculate download speed."""
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

def validate_url(url: str) -> tuple[bool, str]:
    """Validate download URL."""
    if not url or not isinstance(url, str):
        return False, "Invalid URL format"

    if len(url) > MAX_URL_LENGTH:
        return False, f"URL length exceeds maximum allowed ({MAX_URL_LENGTH} characters)."

    parsed_url = urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        return False, "URL must have a scheme (http/https) and network location."

    if parsed_url.scheme not in ('http', 'https') and 'gofile.io' not in parsed_url.netloc:
        return False, "URL scheme must be http or https."

    return True, "Valid"

def get_filename_from_url(url: str, fallback_name: str = None) -> str:
    """Extract filename from URL robustly, with fallbacks and sanitization."""
    try:
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        filename = unquote(filename)

        if '?' in filename:
            filename = filename.split('?')[0]

        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip(' .').strip()
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)

        if not filename or len(filename) < 5 or filename.lower() in ('download', 'file', 'index'):
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = fallback_name or f"download_{timestamp_str}.bin"
            logger.info(f"Generated fallback filename: {filename} for URL: {url}")

        if '.' not in filename:
            filename += '.bin'

        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:(200 - len(ext))] + ext
            logger.warning(f"Truncated filename to: {filename}")

        return filename
    except Exception as e:
        logger.error(f"Error extracting filename from URL '{url}': {e}")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        return fallback_name or f"download_error_{timestamp_str}.bin"

async def download_from_url(url: str, user_id: int, status_message=None) -> str:
    """Download file from URL with progress tracking."""
    try:
        # Validate URL
        is_valid, error_msg = validate_url(url)
        if not is_valid:
            raise ValueError(error_msg)

        # Create user download directory
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_download_dir, exist_ok=True)

        # Get filename
        filename = get_filename_from_url(url)
        dest_path = os.path.join(user_download_dir, filename)

        if status_message:
            await smart_progress_editor(status_message, 
                f"📥 **Starting download...**\n"
                f"🔗 **URL:** `{url[:50]}...`\n"
                f"📁 **File:** `{filename}`"
            )

        # Create aiohttp session
        timeout = aiohttp.ClientTimeout(
            connect=DOWNLOAD_CONNECT_TIMEOUT,
            total=DOWNLOAD_READ_TIMEOUT
        )
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Get file size first
            async with session.head(url) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))

            # Download with progress
            await _perform_download_request(session, url, dest_path, status_message, total_size)

        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            return dest_path
        else:
            raise Exception("Download failed: File not created or empty")

    except Exception as e:
        logger.error(f"Download error: {e}")
        if status_message:
            await status_message.edit_text(f"❌ **Download failed!**\n\n🚨 **Error:** `{str(e)}`")
        raise

@retry(
    stop=stop_after_attempt(DOWNLOAD_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=DOWNLOAD_RETRY_WAIT_MIN, max=DOWNLOAD_RETRY_WAIT_MAX),
    retry=retry_if_exception_type(aiohttp.ClientError) | retry_if_exception_type(asyncio.TimeoutError),
    reraise=True
)
async def _perform_download_request(session: aiohttp.ClientSession, url: str, dest_path: str, status_message, total_size: int):
    """Internal function to perform the actual download request with retry logic."""
    start_time = time.time()
    last_progress_time = start_time
    downloaded = 0

    try:
        async with session.get(url) as response:
            response.raise_for_status()

            if total_size == 0 and 'content-length' in response.headers:
                total_size = int(response.headers['content-length'])
                logger.info(f"Content-Length discovered: {total_size} bytes for {os.path.basename(dest_path)}")

            with open(dest_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if (now - last_progress_time) >= EDIT_THROTTLE_SECONDS or downloaded >= total_size:
                        last_progress_time = now

                        if total_size > 0:
                            progress_percent = downloaded / total_size
                            speed = get_speed(start_time, downloaded)
                            eta = get_time_left(start_time, downloaded, total_size)

                            progress_text = f"""
📥 **Downloading from URL...**
📁 **File:** `{os.path.basename(dest_path)}`
📊 **Total Size:** `{get_human_readable_size(total_size)}`
{get_progress_bar(progress_percent)} `{progress_percent:.1%}`
📈 **Downloaded:** `{get_human_readable_size(downloaded)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
📡 **Status:** {'Complete!' if downloaded >= total_size else 'Downloading...'}
"""
                            await smart_progress_editor(status_message, progress_text.strip())

    except Exception as e:
        logger.error(f"Download request failed: {e}")
        raise

async def download_from_tg(client, message, user_id: int, status_message=None) -> str:
    """Download file from Telegram message."""
    try:
        # Create user download directory
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_download_dir, exist_ok=True)

        # Get file info
        if message.video:
            file_obj = message.video
            file_name = f"video_{int(time.time())}.mp4"
        elif message.document:
            file_obj = message.document
            file_name = file_obj.file_name or f"document_{int(time.time())}"
        else:
            raise ValueError("Message doesn't contain a downloadable file")

        dest_path = os.path.join(user_download_dir, file_name)

        if status_message:
            await smart_progress_editor(status_message,
                f"📥 **Downloading from Telegram...**\n"
                f"📁 **File:** `{file_name}`\n"
                f"📊 **Size:** `{get_human_readable_size(file_obj.file_size)}`"
            )

        # Download with progress callback
        def progress_callback(current, total):
            if status_message:
                progress_percent = current / total
                progress_text = f"""
📥 **Downloading from Telegram...**
📁 **File:** `{file_name}`
📊 **Total Size:** `{get_human_readable_size(total)}`
{get_progress_bar(progress_percent)} `{progress_percent:.1%}`
📈 **Downloaded:** `{get_human_readable_size(current)}`
📡 **Status:** {'Complete!' if current >= total else 'Downloading...'}
"""
                asyncio.create_task(smart_progress_editor(status_message, progress_text.strip()))

        await client.download_media(message, file_name=dest_path, progress=progress_callback)

        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            return dest_path
        else:
            raise Exception("Download failed: File not created or empty")

    except Exception as e:
        logger.error(f"Telegram download error: {e}")
        if status_message:
            await status_message.edit_text(f"❌ **Download failed!**\n\n🚨 **Error:** `{str(e)}`")
        raise
