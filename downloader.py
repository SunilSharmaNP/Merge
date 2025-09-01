# downloader.py - Enhanced with Professional Progress Bars and Robust Error Handling
import aiohttp
import os
import time
import logging
from datetime import datetime
from config import config
from utils import get_human_readable_size, get_progress_bar

# Set up logging for better debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            logger.debug(f"Progress update failed: {e}")

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining."""
    if current <= 0 or total <= 0:
        return "Calculating..."
    
    elapsed = time.time() - start_time
    if elapsed <= 0:
        return "Calculating..."
    
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
    
    if not url.startswith(('http://', 'https://')):
        return False, "URL must start with http:// or https://"
    
    # Check for suspicious extensions
    dangerous_extensions = ['.exe', '.bat', '.cmd', '.scr', '.pif']
    if any(url.lower().endswith(ext) for ext in dangerous_extensions):
        return False, "Potentially dangerous file type"
    
    return True, "Valid"

def get_filename_from_url(url: str, fallback_name: str = None) -> str:
    """Extract filename from URL with fallback options."""
    try:
        # Get filename from URL path
        filename = url.split('/')[-1].split('?')[0]  # Remove query parameters
        
        # If no extension, add default
        if '.' not in filename:
            filename += '.mp4'
        
        # If filename is empty or too short, use fallback
        if not filename or len(filename) < 5:
            timestamp = int(time.time())
            filename = fallback_name or f"download_{timestamp}.mp4"
        
        # Clean filename (remove invalid characters)
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        return filename
    except:
        timestamp = int(time.time())
        return fallback_name or f"download_{timestamp}.mp4"

async def download_from_url(url: str, user_id: int, status_message) -> str | None:
    """Enhanced URL download with professional progress tracking."""
    
    # Validate URL first
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        await status_message.edit_text(f"❌ **Invalid URL!**\n\n🚨 **Error:** {error_msg}")
        return None
    
    # Setup paths
    file_name = get_filename_from_url(url)
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_download_dir, exist_ok=True)
    dest_path = os.path.join(user_download_dir, file_name)
    
    # Progress tracking variables
    start_time = time.time()
    last_progress_time = start_time
    
    try:
        # Initial status
        await smart_progress_editor(
            status_message, 
            f"🔍 **Connecting to server...**\n\n📁 **File:** `{file_name}`\n🌐 **URL:** `{url[:50]}...`"
        )
        
        # Setup session with proper headers and timeouts
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        timeout = aiohttp.ClientTimeout(
            total=None,  # No total timeout for large files
            connect=30,  # 30 seconds to connect
            sock_read=60  # 60 seconds between reads
        )
        
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url) as response:
                
                # Check response status
                if response.status != 200:
                    error_text = f"""
❌ **Download Failed!**

📁 **File:** `{file_name}`
🚨 **HTTP Error:** `{response.status} - {response.reason}`

💡 **Possible Solutions:**
• Check if the URL is correct and accessible
• Try the download link in a browser first
• Contact the file provider if link is expired
"""
                    await status_message.edit_text(error_text.strip())
                    return None
                
                # Get file information
                total_size = int(response.headers.get('content-length', 0))
                content_type = response.headers.get('content-type', 'unknown')
                
                # Update with file info
                await smart_progress_editor(
                    status_message,
                    f"📡 **Download Starting...**\n\n"
                    f"📁 **File:** `{file_name}`\n"
                    f"📊 **Size:** `{get_human_readable_size(total_size) if total_size > 0 else 'Unknown'}`\n"
                    f"📋 **Type:** `{content_type}`"
                )
                
                downloaded = 0
                chunk_size = 1024 * 1024  # 1MB chunks
                
                with open(dest_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Throttle progress updates
                        now = time.time()
                        if (now - last_progress_time) >= 2.0 or downloaded >= total_size:  # Update every 2 seconds
                            last_progress_time = now
                            
                            if total_size > 0:
                                progress = downloaded / total_size
                                speed = get_speed(start_time, downloaded)
                                eta = get_time_left(start_time, downloaded, total_size)
                                
                                progress_text = f"""
📥 **Downloading from URL...**

📁 **File:** `{file_name}`
📊 **Total Size:** `{get_human_readable_size(total_size)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Downloaded:** `{get_human_readable_size(downloaded)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
📡 **Status:** {'Complete!' if downloaded >= total_size else 'Downloading...'}
"""
                                await smart_progress_editor(status_message, progress_text.strip())
                            else:
                                # Unknown size progress
                                speed = get_speed(start_time, downloaded)
                                elapsed = time.time() - start_time
                                
                                progress_text = f"""
📥 **Downloading from URL...**

📁 **File:** `{file_name}`
📊 **Size:** `Unknown`

⏳ **Downloaded:** `{get_human_readable_size(downloaded)}`
🚀 **Speed:** `{speed}`
⏱ **Time:** `{int(elapsed)}s`
📡 **Status:** Downloading...
"""
                                await smart_progress_editor(status_message, progress_text.strip())
                
                # Verify download
                actual_size = os.path.getsize(dest_path)
                if total_size > 0 and actual_size != total_size:
                    logger.error(f"File size mismatch: expected {total_size}, got {actual_size}")
                    os.remove(dest_path)
                    
                    error_text = f"""
❌ **Download Failed!**

📁 **File:** `{file_name}`
🚨 **Error:** File size mismatch
📊 **Expected:** `{get_human_readable_size(total_size)}`
📊 **Received:** `{get_human_readable_size(actual_size)}`

💡 **Tip:** Try downloading again or check your internet connection.
"""
                    await status_message.edit_text(error_text.strip())
                    return None
                
                # Success
                elapsed_time = time.time() - start_time
                success_text = f"""
✅ **Download Complete!**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(actual_size)}`
⏱ **Time:** `{elapsed_time:.1f}s`
🚀 **Avg Speed:** `{get_speed(start_time, actual_size)}`

🔄 **Next:** Preparing for merge...
"""
                await status_message.edit_text(success_text.strip())
                return dest_path
                
    except aiohttp.ClientError as e:
        error_text = f"""
❌ **Connection Error!**

📁 **File:** `{file_name}`
🚨 **Network Error:** `{str(e)}`

💡 **Possible Solutions:**
• Check your internet connection
• Verify the URL is accessible
• Try again after a few minutes
• Contact support if problem persists
"""
        await status_message.edit_text(error_text.strip())
        logger.error(f"Aiohttp client error: {e}")
        return None
        
    except Exception as e:
        error_text = f"""
❌ **Download Failed!**

📁 **File:** `{file_name}`
🚨 **Error:** `{str(e)}`

💡 **Tip:** Please try again or contact support if the problem continues.
"""
        await status_message.edit_text(error_text.strip())
        logger.error(f"General download error: {e}")
        return None

async def download_from_tg(message, user_id: int, status_message) -> str | None:
    """Enhanced Telegram download with professional progress tracking."""
    
    try:
        # Setup paths
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_download_dir, exist_ok=True)
        
        # Get file information
        if message.video:
            file_obj = message.video
            file_name = file_obj.file_name or f"video_{message.id}.mp4"
            file_size = file_obj.file_size
            duration = file_obj.duration or 0
            
            # Get video resolution
            width = getattr(file_obj, 'width', 0)
            height = getattr(file_obj, 'height', 0)
            resolution = f"{width}x{height}" if width and height else "Unknown"
            
        elif message.document:
            file_obj = message.document
            file_name = file_obj.file_name or f"document_{message.id}"
            file_size = file_obj.file_size
            duration = 0
            resolution = "N/A"
        else:
            await status_message.edit_text("❌ **Error:** No downloadable file found in message.")
            return None
        
        # Validate file size (Telegram has a 2GB limit)
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
            error_text = f"""
❌ **File Too Large!**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(file_size)}`
🚨 **Limit:** `2GB (Telegram API Limit)`

💡 **Tip:** Try splitting the file or use a different sharing method.
"""
            await status_message.edit_text(error_text.strip())
            return None
        
        # Initial status with file details
        initial_text = f"""
📡 **Starting Telegram Download...**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(file_size)}`
⏱ **Duration:** `{duration // 60}:{duration % 60:02d}` (if video)
📐 **Resolution:** `{resolution}`
"""
        await smart_progress_editor(status_message, initial_text.strip())
        
        # Progress tracking variables
        start_time = time.time()
        last_progress_time = start_time
        
        async def progress_callback(current, total):
            """Enhanced progress callback with detailed information."""
            nonlocal last_progress_time
            
            # Throttle progress updates
            now = time.time()
            if (now - last_progress_time) < 2.0 and current < total:
                return
            last_progress_time = now
            
            progress = current / total
            speed = get_speed(start_time, current)
            eta = get_time_left(start_time, current, total)
            
            progress_text = f"""
📥 **Downloading from Telegram...**

📁 **File:** `{file_name}`
📊 **Total Size:** `{get_human_readable_size(total)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Downloaded:** `{get_human_readable_size(current)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
📡 **Status:** {'Complete!' if current >= total else 'Downloading...'}
"""
            await smart_progress_editor(status_message, progress_text.strip())
        
        # Download the file
        dest_path = os.path.join(user_download_dir, file_name)
        file_path = await message.download(
            file_name=dest_path,
            progress=progress_callback
        )
        
        # Verify download
        if not os.path.exists(file_path):
            await status_message.edit_text("❌ **Download Failed:** File not found after download.")
            return None
        
        actual_size = os.path.getsize(file_path)
        if actual_size != file_size:
            logger.warning(f"File size mismatch: expected {file_size}, got {actual_size}")
        
        # Success message
        elapsed_time = time.time() - start_time
        success_text = f"""
✅ **Telegram Download Complete!**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(actual_size)}`
⏱ **Time:** `{elapsed_time:.1f}s`
🚀 **Avg Speed:** `{get_speed(start_time, actual_size)}`

🔄 **Next:** Preparing for merge...
"""
        await status_message.edit_text(success_text.strip())
        return file_path
        
    except Exception as e:
        file_name = "Unknown"
        try:
            if hasattr(message, 'video') and message.video:
                file_name = message.video.file_name or "video file"
            elif hasattr(message, 'document') and message.document:
                file_name = message.document.file_name or "document file"
        except:
            pass
        
        error_text = f"""
❌ **Telegram Download Failed!**

📁 **File:** `{file_name}`
🚨 **Error:** `{str(e)}`

💡 **Possible Solutions:**
• Check if the file is still available
• Ensure stable internet connection
• Try forwarding the file and downloading again
• Contact support if problem persists
"""
        await status_message.edit_text(error_text.strip())
        logger.error(f"Telegram download error: {e}")
        return None

# Additional utility functions
def cleanup_failed_downloads(user_id: int):
    """Clean up failed or incomplete downloads."""
    try:
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        if os.path.exists(user_download_dir):
            for filename in os.listdir(user_download_dir):
                file_path = os.path.join(user_download_dir, filename)
                if os.path.isfile(file_path):
                    # Remove files that are too small (likely incomplete)
                    if os.path.getsize(file_path) < 1024:  # Less than 1KB
                        os.remove(file_path)
                        logger.info(f"Cleaned up incomplete download: {filename}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

def get_download_info(file_path: str) -> dict:
    """Get information about a downloaded file."""
    try:
        if not os.path.exists(file_path):
            return {"exists": False}
        
        stat_info = os.stat(file_path)
        return {
            "exists": True,
            "size": stat_info.st_size,
            "size_human": get_human_readable_size(stat_info.st_size),
            "created": datetime.fromtimestamp(stat_info.st_ctime),
            "modified": datetime.fromtimestamp(stat_info.st_mtime),
            "filename": os.path.basename(file_path)
        }
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        return {"exists": False, "error": str(e)}

# Progress bar styles (matching uploader.py)
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
