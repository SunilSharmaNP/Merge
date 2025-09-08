# merger.py - Enhanced with subtitle/audio merging and custom filename support
import asyncio
import os
import time
import json
import logging
import re
import shutil
from typing import List, Optional, Dict, Any
from collections import Counter
from config import config
from utils import get_video_properties, get_progress_bar, get_time_left

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 2.0

async def smart_progress_editor(status_message, text: str):
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

async def get_detailed_video_info(file_path: str) -> Optional[Dict[str, Any]]:
    """Get comprehensive video information using ffprobe with normalized parameters"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', file_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"ffprobe failed for {file_path}: {stderr.decode()}")
            return None

        data = json.loads(stdout.decode())

        video_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        audio_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
        subtitle_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'subtitle']

        if not video_streams:
            logger.error(f"No video stream found in {file_path}")
            return None

        video_stream = video_streams[0]
        audio_stream = audio_streams[0] if audio_streams else None

        # Parse frame rate properly
        fps_str = video_stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = round(float(num) / float(den), 2) if int(den) != 0 else 30.0
        else:
            fps = round(float(fps_str), 2)

        # Get normalized codec names
        video_codec = video_stream.get('codec_name', '').lower()
        audio_codec = audio_stream.get('codec_name', '').lower() if audio_stream else None

        # Get pixel format
        pixel_format = video_stream.get('pix_fmt', 'yuv420p')

        # Get sample rate
        audio_sample_rate = int(audio_stream.get('sample_rate', 48000)) if audio_stream else 48000

        # Get container format
        container = data['format'].get('format_name', '').lower()

        return {
            'has_video': True,
            'has_audio': audio_stream is not None,
            'has_subtitles': len(subtitle_streams) > 0,
            'width': int(video_stream['width']),
            'height': int(video_stream['height']),
            'fps': fps,
            'video_codec': video_codec,
            'audio_codec': audio_codec,
            'pixel_format': pixel_format,
            'duration': float(data['format'].get('duration', 0)),
            'bitrate': video_stream.get('bit_rate'),
            'audio_sample_rate': audio_sample_rate,
            'container': container,
            'file_path': file_path,
            'audio_streams_count': len(audio_streams),
            'subtitle_streams_count': len(subtitle_streams)
        }

    except Exception as e:
        logger.error(f"Failed to get video info for {file_path}: {e}")
        return None

def videos_are_identical_for_merge(video_infos: List[Dict[str, Any]]) -> bool:
    """Check if all videos have identical parameters for fast merge"""
    if not video_infos or len(video_infos) < 2:
        return False

    reference = video_infos[0]

    # Critical parameters that must match for lossless concat
    critical_params = [
        'width', 'height', 'fps', 'video_codec',
        'audio_codec', 'pixel_format', 'audio_sample_rate'
    ]

    for video_info in video_infos[1:]:
        for param in critical_params:
            ref_val = reference.get(param)
            vid_val = video_info.get(param)

            # Handle None values (missing audio)
            if ref_val is None and vid_val is None:
                continue
            if ref_val is None or vid_val is None:
                logger.info(f"Parameter mismatch: {param} - {ref_val} vs {vid_val}")
                return False

            # Special handling for fps comparison
            if param == 'fps':
                if abs(ref_val - vid_val) > 0.1:
                    logger.info(f"FPS mismatch: {ref_val} vs {vid_val}")
                    return False
            else:
                if ref_val != vid_val:
                    logger.info(f"Parameter mismatch: {param} - {ref_val} vs {vid_val}")
                    return False

    return True

async def get_total_duration(video_files: List[str]) -> float:
    """Calculate total duration of all video files for progress calculation"""
    total_duration = 0.0
    for file_path in video_files:
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                   '-of', 'csv=p=0', file_path]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                duration = float(stdout.decode().strip())
                total_duration += duration
        except:
            pass
    return total_duration

async def track_merge_progress(process, total_duration: float, status_message, merge_type: str):
    """Track ffmpeg merge progress and update status"""
    start_time = time.time()
    last_update = 0

    while True:
        try:
            line = await asyncio.wait_for(process.stderr.readline(), timeout=1.0)
            if not line:
                break

            line = line.decode().strip()

            # Parse time progress from ffmpeg stderr
            time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
            if time_match and total_duration > 0:
                hours, minutes, seconds = time_match.groups()
                current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

                progress = min(current_time / total_duration, 1.0)
                elapsed = time.time() - start_time

                if time.time() - last_update > 2.0:
                    eta = (elapsed / progress - elapsed) if progress > 0.01 else 0

                    progress_text = (
                        f"🎶 **{merge_type} in Progress...**\n"
                        f"➤ {get_progress_bar(progress)} `{progress:.1%}`\n"
                        f"➤ **Time Processed:** `{int(current_time)}s` / `{int(total_duration)}s`\n"
                        f"➤ **Elapsed:** `{int(elapsed)}s`\n"
                        f"➤ **ETA:** `{int(eta)}s remaining`"
                    )

                    await smart_progress_editor(status_message, progress_text)
                    last_update = time.time()

        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.debug(f"Progress tracking error: {e}")
            break

async def fast_merge_identical_videos(video_files: List[str], user_id: int, status_message, video_infos: List[Dict[str, Any]], output_filename: str = None) -> Optional[str]:
    """Fast merge with container compatibility fixes - outputs MKV"""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))

    # Generate output filename
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        output_path = os.path.join(user_download_dir, f"{base_name}.mkv")
    else:
        output_path = os.path.join(user_download_dir, f"Merged_By_SSBots_{int(time.time())}.mkv")

    inputs_file = os.path.join(user_download_dir, f"inputs_{int(time.time())}.txt")

    try:
        await status_message.edit_text("🚀 **Starting ultra-fast merge...**")

        # Get total duration for progress calculation
        total_duration = await get_total_duration(video_files)

        # Create inputs file with proper escaping
        with open(inputs_file, 'w', encoding='utf-8') as f:
            for file_path in video_files:
                abs_path = os.path.abspath(file_path)
                formatted_path = abs_path.replace("'", "'\''")
                f.write(f"file '{formatted_path}'\n")

        # Enhanced concat command
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'info', '-y',
            '-f', 'concat', '-safe', '0', '-i', inputs_file,
            '-map', '0',
            '-c', 'copy',   # Stream copy (no re-encoding)
            '-f', 'matroska',  # Force MKV output
            '-progress', 'pipe:2',
            output_path
        ]

        logger.info(f"Fast merge command: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # Start progress tracking
        progress_task = asyncio.create_task(
            track_merge_progress(process, total_duration, status_message, "Fast Merge")
        )

        stdout, stderr = await process.communicate()
        progress_task.cancel()

        # Cleanup
        try:
            os.remove(inputs_file)
        except:
            pass

        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path)

            await status_message.edit_text(
                f"✅ **Fast Merge Completed Successfully!**\n"
                f"➤ **Output:** `{os.path.basename(output_path)}`\n"
                f"➤ **Size:** `{file_size / (1024*1024):.1f} MB`\n"
                f"➤ **Mode:** Ultra-fast merge"
            )
            return output_path
        else:
            raise Exception("Fast merge failed")

    except Exception as e:
        logger.error(f"Fast merge failed: {e}")
        # Cleanup
        try:
            os.remove(inputs_file)
            if os.path.exists(output_path):
                os.remove(output_path)
        except:
            pass
        raise

async def re_encode_merge_videos(video_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Re-encode and merge videos with different parameters"""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))

    # Generate output filename
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        output_path = os.path.join(user_download_dir, f"{base_name}.mp4")
    else:
        output_path = os.path.join(user_download_dir, f"Merged_ReEncoded_{int(time.time())}.mp4")

    try:
        await status_message.edit_text("🔧 **Starting re-encode merge (this may take longer)...**")

        # Build ffmpeg command for re-encoding merge
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-y']

        # Add input files
        for video_file in video_files:
            cmd.extend(['-i', video_file])

        # Filter complex to concatenate
        filter_inputs = ''.join([f'[{i}:v:0][{i}:a:0]' for i in range(len(video_files))])
        filter_concat = f'{filter_inputs}concat=n={len(video_files)}:v=1:a=1[outv][outa]'

        cmd.extend([
            '-filter_complex', filter_concat,
            '-map', '[outv]',
            '-map', '[outa]',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-progress', 'pipe:2',
            output_path
        ])

        logger.info(f"Re-encode merge command: {' '.join(cmd)}")

        # Get total duration for progress
        total_duration = await get_total_duration(video_files)

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # Start progress tracking
        progress_task = asyncio.create_task(
            track_merge_progress(process, total_duration, status_message, "Re-encode Merge")
        )

        stdout, stderr = await process.communicate()
        progress_task.cancel()

        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path)

            await status_message.edit_text(
                f"✅ **Re-encode Merge Completed Successfully!**\n"
                f"➤ **Output:** `{os.path.basename(output_path)}`\n"
                f"➤ **Size:** `{file_size / (1024*1024):.1f} MB`\n"
                f"➤ **Mode:** Re-encoded merge"
            )
            return output_path
        else:
            raise Exception("Re-encode merge failed")

    except Exception as e:
        logger.error(f"Re-encode merge failed: {e}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise

async def merge_videos(video_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Main merge function that chooses the best strategy"""
    try:
        # Get video information for all files
        video_infos = []
        for video_file in video_files:
            info = await get_detailed_video_info(video_file)
            if info:
                video_infos.append(info)

        if len(video_infos) != len(video_files):
            raise Exception("Could not analyze all video files")

        # Check if videos are identical for fast merge
        if videos_are_identical_for_merge(video_infos):
            logger.info("Videos are identical - using fast merge")
            return await fast_merge_identical_videos(video_files, user_id, status_message, video_infos, output_filename)
        else:
            logger.info("Videos have different parameters - using re-encode merge")
            return await re_encode_merge_videos(video_files, user_id, status_message, output_filename)

    except Exception as e:
        logger.error(f"Merge operation failed: {e}")
        if status_message:
            await status_message.edit_text(f"❌ **Merge failed!**\n\n🚨 **Error:** `{str(e)}`")
        raise
