# downloader.py (Modified to prevent FloodWait errors and fix large file download issues)
import aiohttp
import os
import time
import logging
from config import config
from utils import get_human_readable_size, get_progress_bar

# Set up logging for better debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Throttling Logic ---
# Global dictionary to store the last time a message was updated.
last_edit_time = {}

# We will only allow message edits once every 4 seconds.
EDIT_THROTTLE_SECONDS = 4.0

async def smart_progress_editor(status_message, text: str):
    """
    A custom editor that checks if enough time has passed before editing a message.
    This is the core of the FloodWait prevention.
    """
    # Check for valid message object
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
            logger.debug(f"Progress update failed (could be FloodWait or no change): {e}")

async def download_from_url(url: str, user_id: int, status_message) -> str or None:
    """Downloads a file from a direct URL with smart progress reporting."""
    file_name = url.split('/')[-1] or f"video_{int(time.time())}.mp4"
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_download_dir, exist_ok=True)
    dest_path = os.path.join(user_download_dir, file_name)

    try:
        # Increased timeout to None for large files. It will now wait indefinitely.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    total_size = int(resp.headers.get('content-length', 0))
                    downloaded = 0
                    start_time = time.time()
                    
                    # Update message to indicate download is starting
                    await smart_progress_editor(status_message, f"📥 **Starting download...**\n`{file_name}`")
                    
                    with open(dest_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if total_size > 0:
                                progress = downloaded / total_size
                                
                                # Estimate ETA
                                elapsed_time = time.time() - start_time
                                eta = (elapsed_time / progress) - elapsed_time if progress > 0 else 0
                                
                                # Build the progress message text
                                progress_text = (
                                    f"📥 **Downloading from URL...**\n"
                                    f"➢ `{file_name}`\n"
                                    f"➢ {get_progress_bar(progress)} `{progress:.1%}`\n"
                                    f"➢ **Size:** `{get_human_readable_size(downloaded)}` / `{get_human_readable_size(total_size)}`\n"
                                    f"➢ **ETA:** `{int(eta)}s`"
                                )
                                # Call our new smart editor instead of editing directly
                                await smart_progress_editor(status_message, progress_text)
                    
                    # Verify file size and send a final update to show the download is done
                    if os.path.exists(dest_path) and os.path.getsize(dest_path) == total_size:
                        await status_message.edit_text(f"✅ **Downloaded:** `{file_name}`\n\nPreparing to merge...")
                        return dest_path
                    else:
                        logger.error(f"Downloaded file size mismatch for {file_name}")
                        await status_message.edit_text(f"❌ **Download Failed!**\nFile size mismatch for: `{file_name}`")
                        return None
                else:
                    await status_message.edit_text(f"❌ **Download Failed!**\nStatus: {resp.status} for URL: `{url}`")
                    return None
    except aiohttp.ClientError as e:
        logger.error(f"Aiohttp client error during download: {e}")
        try:
            await status_message.edit_text(f"❌ **Download Failed!**\nConnection Error: `{str(e)}`")
        except Exception:
            pass
        return None
    except Exception as e:
        logger.error(f"General error during URL download: {e}")
        try:
            await status_message.edit_text(f"❌ **Download Failed!**\nError: `{str(e)}`")
        except Exception:
            pass
        return None

async def download_from_tg(message, user_id: int, status_message) -> str or None:
    """Downloads a file from Telegram with smart progress reporting."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_download_dir, exist_ok=True)
    
    # We define the progress callback here, which will be called by Pyrogram
    async def progress_func(current, total):
        progress = current / total
        file_name = message.video.file_name if message.video and message.video.file_name else "telegram_video.mp4"
        
        # Build the progress message text
        progress_text = (
            f"📥 **Downloading from Telegram...**\n"
            f"➢ `{file_name}`\n"
            f"➢ {get_progress_bar(progress)} `{progress:.1%}`\n"
            f"➢ **Size:** `{get_human_readable_size(current)}` / `{get_human_readable_size(total)}`"
        )
        # Call our new smart editor
        await smart_progress_editor(status_message, progress_text)

    try:
        # Use a proper file name to avoid Pyrogram's default behavior
        file_path = await message.download(
            file_name=os.path.join(user_download_dir, message.video.file_name if message.video else "telegram_file"),
            progress=progress_func
        )
        file_name = os.path.basename(file_path)
        await status_message.edit_text(f"✅ **Downloaded:** `{file_name}`\n\nPreparing to merge...")
        return file_path
    except Exception as e:
        logger.error(f"General error during Telegram download: {e}")
        try:
            await status_message.edit_text(f"❌ **Download Failed!**\nError: `{str(e)}`")
        except Exception:
            pass
        return None
