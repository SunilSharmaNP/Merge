# downloader.py - CLEANED AND OPTIMIZED VERSION
import aiohttp
import asyncio
import os
import time
import logging
from datetime import datetime
from config import config
from utils import get_human_readable_size, get_progress_bar
from urllib.parse import urlparse, unquote
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 2.0

# Configuration
DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB chunks
DOWNLOAD_TIMEOUT = 300  # 5 minutes
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
        except Exception as e:
            logger.debug(f"Progress update failed: {e}")

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining"""
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
    """Calculate download speed"""
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

def get_filename_from_url(url: str, fallback_name: str = None) -> str:
    """Extract filename from URL"""
    try:
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        filename = unquote(filename)
        
        if '?' in filename:
            filename = filename.split('?')[0]

        # Sanitize filename
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip(' .').strip()
        
        if not filename or len(filename) < 3:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = fallback_name or f"download_{timestamp_str}.mp4"
        
        if not filename.endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm')):
            filename += '.mp4'
        
        return filename
        
    except Exception as e:
        logger.error(f"Error extracting filename: {e}")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        return fallback_name or f"download_{timestamp_str}.mp4"

async def download_from_url(url: str, dest_dir: str, status_message, filename: str = None) -> str:
    """Download video from URL with progress tracking"""
    try:
        # Ensure destination directory exists
        os.makedirs(dest_dir, exist_ok=True)
        
        # Determine filename
        if not filename:
            filename = get_filename_from_url(url)
        
        dest_path = os.path.join(dest_dir, filename)
        
        # Update status
        await smart_progress_editor(
            status_message,
            f"🔗 **Starting download...**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"🌐 **URL:** `{url[:50]}...`"
        )
        
        start_time = time.time()
        downloaded = 0
        
        timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                
                # Update with file size info
                await smart_progress_editor(
                    status_message,
                    f"⬇️ **Downloading...**\n\n"
                    f"📁 **File:** `{filename}`\n"
                    f"📊 **Size:** `{get_human_readable_size(total_size) if total_size > 0 else 'Unknown'}`\n"
                    f"🚀 **Starting download...**"
                )
                
                with open(dest_path, 'wb') as file:
                    async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                        file.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = downloaded / total_size
                            speed = get_speed(start_time, downloaded)
                            eta = get_time_left(start_time, downloaded, total_size)
                            
                            progress_text = f"""⬇️ **Downloading Video...**

📁 **File:** `{filename}`
📊 **Total Size:** `{get_human_readable_size(total_size)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Downloaded:** `{get_human_readable_size(downloaded)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`"""
                            
                            await smart_progress_editor(status_message, progress_text)
        
        # Verify download
        if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
            raise Exception("Download failed - file is empty or doesn't exist")
        
        # Final success message
        elapsed_time = time.time() - start_time
        final_size = os.path.getsize(dest_path)
        
        await smart_progress_editor(
            status_message,
            f"✅ **Download Complete!**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"📊 **Size:** `{get_human_readable_size(final_size)}`\n"
            f"⏱ **Time:** `{int(elapsed_time)}s`\n"
            f"🚀 **Avg Speed:** `{get_speed(start_time, final_size)}`"
        )
        
        return dest_path
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await smart_progress_editor(
            status_message,
            f"❌ **Download Failed!**\n\n"
            f"🚨 **Error:** `{str(e)}`\n\n"
            f"💡 **Try again or check the URL**"
        )
        return None

async def download_from_tg(client, file_id: str, dest_dir: str, status_message, filename: str = None) -> str:
    """Download video from Telegram with progress tracking"""
    try:
        # Ensure destination directory exists
        os.makedirs(dest_dir, exist_ok=True)
        
        # Get file info
        file_info = await client.get_file(file_id)
        
        if not filename:
            filename = f"telegram_video_{int(time.time())}.mp4"
        
        dest_path = os.path.join(dest_dir, filename)
        
        # Update status
        await smart_progress_editor(
            status_message,
            f"📱 **Starting Telegram download...**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"📊 **Size:** `{get_human_readable_size(file_info.file_size)}`"
        )
        
        start_time = time.time()
        
        # Download with progress callback
        async def progress_callback(current, total):
            progress = current / total
            speed = get_speed(start_time, current)
            eta = get_time_left(start_time, current, total)
            
            progress_text = f"""📱 **Downloading from Telegram...**

📁 **File:** `{filename}`
📊 **Total Size:** `{get_human_readable_size(total)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Downloaded:** `{get_human_readable_size(current)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`"""
            
            await smart_progress_editor(status_message, progress_text)
        
        # Download file
        await client.download_media(file_id, dest_path, progress=progress_callback)
        
        # Verify download
        if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
            raise Exception("Download failed - file is empty or doesn't exist")
        
        # Final success message
        elapsed_time = time.time() - start_time
        final_size = os.path.getsize(dest_path)
        
        await smart_progress_editor(
            status_message,
            f"✅ **Telegram Download Complete!**\n\n"
            f"📁 **File:** `{filename}`\n"
            f"📊 **Size:** `{get_human_readable_size(final_size)}`\n"
            f"⏱ **Time:** `{int(elapsed_time)}s`\n"
            f"🚀 **Avg Speed:** `{get_speed(start_time, final_size)}`"
        )
        
        return dest_path
        
    except Exception as e:
        logger.error(f"Telegram download error: {e}")
        await smart_progress_editor(
            status_message,
            f"❌ **Telegram Download Failed!**\n\n"
            f"🚨 **Error:** `{str(e)}`\n\n"
            f"💡 **Try uploading the file again**"
        )
        return None
