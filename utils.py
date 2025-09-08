# utils.py - FIXED VERSION with Proper Async Functions
import time
import math
import asyncio
import json
import os
import re
import shutil
import humanize

def get_human_readable_size(size_in_bytes: int) -> str:
    """Formats size in bytes to a human-readable string (KB, MB, GB)."""
    if size_in_bytes is None:
        return "0B"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size_in_bytes > power and n < len(power_labels) - 1:
        size_in_bytes /= power
        n += 1
    return f"{size_in_bytes:.2f} {power_labels[n]}B"

def get_progress_bar(progress: float, length: int = 20) -> str:
    """Creates a textual progress bar."""
    filled_len = int(length * progress)
    return '█' * filled_len + '░' * (length - filled_len)

def get_time_left(elapsed_time: float, progress: float) -> str:
    """Estimates the time remaining for the process."""
    if progress == 0:
        return "N/A"
    seconds = (elapsed_time / progress) - elapsed_time
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"

async def get_video_properties(video_path: str) -> dict:
    """Gets video properties (duration, width, height) using ffprobe asynchronously."""
    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        return None

    command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]

    try:
        # Run the command asynchronously
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            print(f"Error getting video properties for '{video_path}': {stderr.decode().strip()}")
            return None

        # Parse the JSON output
        data = json.loads(stdout)

        # Find the first video stream
        video_stream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)

        if not video_stream:
            print(f"No video stream found in '{video_path}'")
            return None

        # Extract properties
        duration_str = video_stream.get("duration", data.get("format", {}).get("duration", "0"))

        return {
            "duration": int(float(duration_str)),
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
        }
    except (json.JSONDecodeError, KeyError, StopIteration, ValueError) as e:
        print(f"Failed to parse ffprobe output for '{video_path}': {e}")
        return None

async def create_thumbnail(video_path: str, thumbnail_path: str) -> str:
    """Creates a thumbnail asynchronously from the middle of the video."""
    # First, get the video's duration reliably
    properties = await get_video_properties(video_path)
    if not properties or not properties["duration"]:
        print(f"Could not get duration for '{video_path}', cannot create thumbnail.")
        return None

    duration = properties["duration"]
    # Seek to the middle of the video for a safe thumbnail
    thumbnail_time = duration / 2

    command = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error',
        '-i', video_path,
        '-ss', str(thumbnail_time),
        '-vframes', '1',
        '-c:v', 'mjpeg', '-f', 'image2',
        '-y', thumbnail_path
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            print(f"Error creating thumbnail: {stderr.decode().strip()}")
            return None

        return thumbnail_path if os.path.exists(thumbnail_path) else None
    except Exception as e:
        print(f"Exception creating thumbnail: {e}")
        return None

def cleanup_files(*files_or_dirs):
    """Safely removes files and directories."""
    for item in files_or_dirs:
        try:
            if os.path.isdir(item):
                shutil.rmtree(item)
            elif os.path.isfile(item):
                os.remove(item)
        except OSError as e:
            print(f"Error cleaning up {item}: {e}")

def is_valid_url(url: str) -> bool:
    """A simple check to see if a string looks like a URL."""
    return re.match(r'^https?:\/\/.+$', url) is not None
