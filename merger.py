# bulletproof_merger_fixed.py - Fixed MKV->MP4 container compatibility issues
import asyncio
import os
import time
import json
import logging
import re
from typing import List, Optional, Dict, Any
from collections import Counter
from config import config
from utils import get_video_properties, get_progress_bar, get_time_left

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Progress throttling (unchanged) ---
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
        
        if not video_streams:
            logger.error(f"No video stream found in {file_path}")
            return None
            
        video_stream = video_streams[0]
        audio_stream = audio_streams[0] if audio_streams else None
        
        # Parse frame rate properly with rounding for comparison
        fps_str = video_stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = round(float(num) / float(den), 2) if int(den) != 0 else 30.0
        else:
            fps = round(float(fps_str), 2)
            
        # Get normalized codec names for comparison
        video_codec = video_stream.get('codec_name', '').lower()
        audio_codec = audio_stream.get('codec_name', '').lower() if audio_stream else None
        
        # Get pixel format with fallback
        pixel_format = video_stream.get('pix_fmt', 'yuv420p')
        
        # Get sample rate with fallback
        audio_sample_rate = int(audio_stream.get('sample_rate', 48000)) if audio_stream else 48000
        
        # Get container format (critical for compatibility check)
        container = data['format'].get('format_name', '').lower()
        
        return {
            'has_video': True,
            'has_audio': audio_stream is not None,
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
            'file_path': file_path  # Store original path for debugging
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
            
            # Special handling for fps comparison (allow small differences)
            if param == 'fps':
                if abs(ref_val - vid_val) > 0.1:
                    logger.info(f"FPS mismatch: {ref_val} vs {vid_val}")
                    return False
            else:
                if ref_val != vid_val:
                    logger.info(f"Parameter mismatch: {param} - {ref_val} vs {vid_val}")
                    return False
    
    return True

def requires_container_remux(video_infos: List[Dict[str, Any]], target_container: str = 'mp4') -> bool:
    """Check if container remux is needed (MKV->MP4 compatibility)"""
    for info in video_infos:
        container = info.get('container', '')
        # Check for container incompatibility issues
        if 'matroska' in container and target_container == 'mp4':
            logger.info(f"Container remux needed: {container} -> {target_container}")
            return True
    return False

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
                        f"ðŸŽ¬ **{merge_type} in Progress...**\n"
                        f"âž¢ {get_progress_bar(progress)} `{progress:.1%}`\n"
                        f"âž¢ **Time Processed:** `{int(current_time)}s` / `{int(total_duration)}s`\n"
                        f"âž¢ **Elapsed:** `{int(elapsed)}s`\n"
                        f"âž¢ **ETA:** `{int(eta)}s remaining`"
                    )
                    
                    await smart_progress_editor(status_message, progress_text)
                    last_update = time.time()
                    
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.debug(f"Progress tracking error: {e}")
            break

async def remux_to_compatible_format(input_path: str, output_path: str, status_message, file_index: int, total_files: int) -> bool:
    """Remux MKV to MP4 maintaining all streams (FIXED container compatibility)"""
    try:
        await smart_progress_editor(status_message, 
            f"ðŸ”„ **Remuxing video {file_index}/{total_files} for compatibility...**\n"
            f"âž¢ `{os.path.basename(input_path)}`\n"
            f"âž¢ **Converting:** MKV â†’ MP4 (no re-encoding)"
        )
        
        # FIXED: Use explicit stream mapping to preserve all streams
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'info', '-y',
            '-i', input_path,
            
            # CRITICAL FIX: Explicitly map all streams
            '-map', '0:v:0',  # Map first video stream
            '-map', '0:a:0',  # Map first audio stream
            
            # Stream copy (no re-encoding)
            '-c:v', 'copy',   # Copy video codec
            '-c:a', 'copy',   # Copy audio codec
            
            # MP4 container optimization
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts',
            
            # Progress reporting
            '-progress', 'pipe:2',
            
            output_path
        ]
        
        logger.info(f"Remux command: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"Successfully remuxed: {input_path}")
            return True
        else:
            error_output = stderr.decode().strip()
            logger.error(f"Remux failed for {input_path}: {error_output}")
            return False
            
    except Exception as e:
        logger.error(f"Remux error for {input_path}: {e}")
        return False

async def fast_merge_identical_videos(video_files: List[str], user_id: int, status_message, video_infos: List[Dict[str, Any]]) -> Optional[str]:
    """Fast merge with container compatibility fixes"""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    # Check if container remux is needed
    needs_remux = requires_container_remux(video_infos)
    
    if needs_remux:
        await status_message.edit_text("ðŸ”„ **Container compatibility issue detected! Remuxing files...**")
        
        # Remux files to compatible format
        remuxed_files = []
        for i, (file_path, info) in enumerate(zip(video_files, video_infos)):
            remuxed_path = os.path.join(user_download_dir, f"remux_{i}_{int(time.time())}.mp4")
            
            success = await remux_to_compatible_format(file_path, remuxed_path, status_message, i+1, len(video_files))
            if not success:
                await status_message.edit_text(f"âŒ **Failed to remux video {i+1}!**")
                return None
            remuxed_files.append(remuxed_path)
        
        # Use remuxed files for concat
        video_files = remuxed_files
    
    output_path = os.path.join(user_download_dir, f"merged_fast_{int(time.time())}.mp4")
    inputs_file = os.path.join(user_download_dir, f"inputs_{int(time.time())}.txt")
    
    try:
        await status_message.edit_text("ðŸš€ **Starting ultra-fast merge...**")
        
        # Get total duration for progress calculation
        total_duration = await get_total_duration(video_files)
        
        # Create inputs file with proper escaping
        with open(inputs_file, 'w', encoding='utf-8') as f:
            for file_path in video_files:
                abs_path = os.path.abspath(file_path)
                formatted_path = abs_path.replace("'", "'\''")
                f.write(f"file '{formatted_path}'\n")
        
        # FIXED: Enhanced concat command with explicit stream mapping
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'info', '-y',
            '-f', 'concat', '-safe', '0', '-i', inputs_file,
            
            # CRITICAL FIX: Explicitly specify stream mapping
            '-map', '0:v',  # Map all video streams
            '-map', '0:a',  # Map all audio streams
            
            '-c', 'copy',   # Stream copy (no re-encoding)
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            '-progress', 'pipe:2',
            output_path
        ]
        
        logger.info(f"Enhanced fast merge command: {' '.join(cmd)}")
        
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
            if needs_remux:
                for remuxed_file in video_files:
                    os.remove(remuxed_file)
        except:
            pass
        
        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path)
            
            # Verify output has both video and audio
            output_info = await get_detailed_video_info(output_path)
            if output_info and output_info['has_video'] and output_info['has_audio']:
                await status_message.edit_text(
                    f"âœ… **Fast Merge Completed Successfully!**\n"
                    f"âž¢ **Output:** `{os.path.basename(output_path)}`\n"
                    f"âž¢ **Size:** `{file_size / (1024*1024):.1f} MB`\n"
                    f"âž¢ **Streams:** Video âœ… + Audio âœ…\n"
                    f"âž¢ **Mode:** {'Container-fixed' if needs_remux else 'Ultra-fast'} merge"
                )
                return output_path
            else:
                logger.error("Output verification failed: missing video or audio stream")
                await status_message.edit_text("âš ï¸ **Fast merge produced incomplete output, falling back to standardization...**")
                return None
        else:
            error_output = stderr.decode().strip()
            logger.error(f"Fast merge failed: {error_output}")
            await status_message.edit_text("âš ï¸ **Fast merge failed, falling back to standardization...**")
            return None
            
    except Exception as e:
        logger.error(f"Fast merge error: {e}")
        try:
            os.remove(inputs_file)
        except:
            pass
        await status_message.edit_text("âš ï¸ **Fast merge failed, falling back to standardization...**")
        return None

async def standardize_video_file_with_progress(input_path: str, output_path: str, target_params: Dict[str, Any], status_message, file_index: int, total_files: int) -> bool:
    """Force standardize a video file to exact target parameters with progress tracking"""
    try:
        duration = 0.0
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', 
                   '-of', 'csv=p=0', input_path]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                duration = float(stdout.decode().strip())
        except:
            duration = 60.0
        
        # FIXED: Enhanced standardization with explicit stream mapping
        cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'info',
            '-i', input_path,
            
            # Video processing
            '-vf', f'scale={target_params["width"]}:{target_params["height"]}:force_original_aspect_ratio=decrease,pad={target_params["width"]}:{target_params["height"]}:(ow-iw)/2:(oh-ih)/2,fps={target_params["fps"]},format={target_params["pixel_format"]}',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            
            # Audio processing (explicit mapping)
            '-c:a', 'aac', '-ar', str(target_params['audio_sample_rate']), '-ac', '2', '-b:a', '128k',
            
            # Stream mapping to ensure both video and audio
            '-map', '0:v:0',  # Map first video stream
            '-map', '0:a:0',  # Map first audio stream
            
            # Container optimization
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts',
            '-progress', 'pipe:2',
            
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        # Progress tracking
        start_time = time.time()
        last_update = 0
        
        async def track_standardization_progress():
            while True:
                try:
                    line = await asyncio.wait_for(process.stderr.readline(), timeout=1.0)
                    if not line:
                        break
                    
                    line = line.decode().strip()
                    time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                    
                    if time_match and duration > 0:
                        hours, minutes, seconds = time_match.groups()
                        current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                        progress = min(current_time / duration, 1.0)
                        elapsed = time.time() - start_time
                        
                        nonlocal last_update
                        if time.time() - last_update > 3.0:
                            eta = (elapsed / progress - elapsed) if progress > 0.01 else 0
                            
                            progress_text = (
                                f"âš™ï¸ **Standardizing Video {file_index}/{total_files}...**\n"
                                f"âž¢ `{os.path.basename(input_path)}`\n"
                                f"âž¢ {get_progress_bar(progress)} `{progress:.1%}`\n"
                                f"âž¢ **Processing:** `{int(current_time)}s` / `{int(duration)}s`\n"
                                f"âž¢ **ETA:** `{int(eta)}s remaining`"
                            )
                            
                            await smart_progress_editor(status_message, progress_text)
                            last_update = time.time()
                            
                except asyncio.TimeoutError:
                    continue
                except:
                    break
        
        progress_task = asyncio.create_task(track_standardization_progress())
        stdout, stderr = await process.communicate()
        progress_task.cancel()
        
        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"Successfully standardized: {input_path}")
            return True
        else:
            logger.error(f"Standardization
