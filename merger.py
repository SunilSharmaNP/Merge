# advanced_merger.py (Enhanced for merging all kinds of videos)
import asyncio
import os
import time
import json
import logging
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import subprocess
from config import config
from utils import get_video_properties, get_progress_bar, get_time_left

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Enhanced Video Metadata Classes ---
@dataclass
class VideoMetadata:
    """Enhanced video metadata container"""
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    bitrate: Optional[int] = None
    pixel_format: str = "yuv420p"
    color_space: Optional[str] = None
    hdr_metadata: Optional[Dict] = None
    audio_tracks: List[Dict] = None
    subtitle_tracks: List[Dict] = None
    has_chapters: bool = False
    container_format: str = "unknown"

class MergeStrategy(Enum):
    """Available merge strategies"""
    FAST_CONCAT = "fast_concat"          # concat protocol/demuxer
    FILTER_COMPLEX = "filter_complex"    # concat filter with re-encoding
    SMART_SCALE = "smart_scale"          # scale videos to common resolution
    ADAPTIVE = "adaptive"                # automatically choose best method
    GPU_ACCELERATED = "gpu_accelerated"  # use GPU acceleration when available

class QualityProfile(Enum):
    """Quality presets for encoding"""
    ULTRA_FAST = "ultrafast"
    FAST = "fast" 
    MEDIUM = "medium"
    SLOW = "slow"
    PRESERVE_QUALITY = "preserve"

# --- Advanced Hardware Detection ---
class HardwareCapabilities:
    """Detect and manage hardware acceleration capabilities"""
    
    @staticmethod
    async def detect_gpu_support() -> Dict[str, bool]:
        """Detect available GPU acceleration"""
        capabilities = {
            'nvidia': False,
            'intel': False,
            'amd': False,
            'apple': False
        }
        
        try:
            # Check for NVIDIA NVENC
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-hide_banner', '-encoders',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await process.communicate()
            output = stdout.decode()
            
            if 'h264_nvenc' in output or 'hevc_nvenc' in output:
                capabilities['nvidia'] = True
            if 'h264_qsv' in output or 'hevc_qsv' in output:
                capabilities['intel'] = True
            if 'h264_amf' in output or 'hevc_amf' in output:
                capabilities['amd'] = True
            if 'h264_videotoolbox' in output:
                capabilities['apple'] = True
                
        except Exception as e:
            logger.warning(f"Could not detect GPU capabilities: {e}")
            
        return capabilities

# --- Enhanced Metadata Extraction ---
class AdvancedMetadataExtractor:
    """Enhanced metadata extraction with format-specific handling"""
    
    @staticmethod
    async def extract_comprehensive_metadata(file_path: str) -> Optional[VideoMetadata]:
        """Extract comprehensive video metadata using ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', '-show_chapters',
                file_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"ffprobe failed for {file_path}: {stderr.decode()}")
                return None
                
            data = json.loads(stdout.decode())
            
            # Find video stream
            video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
            if not video_stream:
                logger.error(f"No video stream found in {file_path}")
                return None
            
            # Extract audio tracks
            audio_tracks = [
                {
                    'index': s['index'],
                    'codec': s['codec_name'],
                    'channels': s.get('channels', 2),
                    'sample_rate': int(s.get('sample_rate', 48000)),
                    'bitrate': s.get('bit_rate'),
                    'language': s.get('tags', {}).get('language', 'und')
                }
                for s in data['streams'] if s['codec_type'] == 'audio'
            ]
            
            # Extract subtitle tracks
            subtitle_tracks = [
                {
                    'index': s['index'],
                    'codec': s['codec_name'],
                    'language': s.get('tags', {}).get('language', 'und')
                }
                for s in data['streams'] if s['codec_type'] == 'subtitle'
            ]
            
            # Parse frame rate
            fps_str = video_stream.get('r_frame_rate', '30/1')
            fps = eval(fps_str) if '/' in fps_str else float(fps_str)
            
            # Parse duration
            duration = float(video_stream.get('duration') or data['format'].get('duration', 0))
            
            return VideoMetadata(
                duration=duration,
                width=int(video_stream['width']),
                height=int(video_stream['height']),
                fps=fps,
                codec=video_stream['codec_name'],
                bitrate=video_stream.get('bit_rate'),
                pixel_format=video_stream.get('pix_fmt', 'yuv420p'),
                color_space=video_stream.get('color_space'),
                hdr_metadata=video_stream.get('side_data_list'),
                audio_tracks=audio_tracks,
                subtitle_tracks=subtitle_tracks,
                has_chapters='chapters' in data and len(data['chapters']) > 0,
                container_format=data['format']['format_name']
            )
            
        except Exception as e:
            logger.error(f"Failed to extract metadata from {file_path}: {e}")
            return None

# --- Compatibility Analysis ---
class CompatibilityAnalyzer:
    """Analyze video compatibility for optimal merge strategy"""
    
    @staticmethod
    def analyze_compatibility(metadata_list: List[VideoMetadata]) -> Dict[str, Any]:
        """Analyze video files for compatibility"""
        if not metadata_list:
            return {'compatible': False, 'reason': 'No metadata provided'}
        
        analysis = {
            'compatible': True,
            'strategy': MergeStrategy.FAST_CONCAT,
            'reasons': [],
            'resolution_analysis': {},
            'audio_analysis': {},
            'encoding_required': False
        }
        
        # Check resolution compatibility
        resolutions = [(m.width, m.height) for m in metadata_list]
        unique_resolutions = set(resolutions)
        
        if len(unique_resolutions) > 1:
            analysis['compatible'] = False
            analysis['reasons'].append('Different resolutions detected')
            analysis['resolution_analysis'] = {
                'resolutions': list(unique_resolutions),
                'max_resolution': max(unique_resolutions, key=lambda x: x[0] * x[1]),
                'min_resolution': min(unique_resolutions, key=lambda x: x[0] * x[1])
            }
            analysis['strategy'] = MergeStrategy.SMART_SCALE
        
        # Check codec compatibility
        codecs = [m.codec for m in metadata_list]
        if len(set(codecs)) > 1:
            analysis['compatible'] = False
            analysis['reasons'].append(f'Different codecs: {set(codecs)}')
            analysis['strategy'] = MergeStrategy.FILTER_COMPLEX
        
        # Check frame rate compatibility
        frame_rates = [round(m.fps, 2) for m in metadata_list]
        if len(set(frame_rates)) > 1:
            analysis['compatible'] = False
            analysis['reasons'].append(f'Different frame rates: {set(frame_rates)}')
            analysis['encoding_required'] = True
        
        # Check pixel format compatibility
        pixel_formats = [m.pixel_format for m in metadata_list]
        if len(set(pixel_formats)) > 1:
            analysis['compatible'] = False
            analysis['reasons'].append(f'Different pixel formats: {set(pixel_formats)}')
        
        # Analyze audio tracks
        max_audio_tracks = max(len(m.audio_tracks or []) for m in metadata_list)
        if max_audio_tracks > 1:
            analysis['audio_analysis']['has_multi_audio'] = True
            analysis['audio_analysis']['max_tracks'] = max_audio_tracks
        
        return analysis

# --- Throttling Logic for Progress Bar (Enhanced) ---
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 2.0  # Reduced for more responsive updates

async def smart_progress_editor(status_message, text: str):
    """Enhanced throttled editor with better error handling"""
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

# --- Advanced Merge Strategies ---
class AdvancedVideoMerger:
    """Advanced video merger with multiple strategies"""
    
    def __init__(self, user_id: int, quality_profile: QualityProfile = QualityProfile.FAST):
        self.user_id = user_id
        self.quality_profile = quality_profile
        self.user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        self.hardware_caps = None
        
    async def initialize_hardware(self):
        """Initialize hardware capabilities"""
        self.hardware_caps = await HardwareCapabilities.detect_gpu_support()
        logger.info(f"Hardware capabilities: {self.hardware_caps}")
        
    async def merge_videos_advanced(
        self, 
        video_files: List[str], 
        status_message,
        strategy: MergeStrategy = MergeStrategy.ADAPTIVE,
        preserve_metadata: bool = True
    ) -> Optional[str]:
        """Advanced video merging with multiple strategies"""
        
        if not self.hardware_caps:
            await self.initialize_hardware()
            
        # Extract metadata for all files
        await status_message.edit_text("🔍 **Analyzing video files...**")
        metadata_tasks = [
            AdvancedMetadataExtractor.extract_comprehensive_metadata(f) 
            for f in video_files
        ]
        metadata_list = await asyncio.gather(*metadata_tasks)
        
        # Filter out failed metadata extractions
        valid_metadata = [m for m in metadata_list if m is not None]
        if len(valid_metadata) != len(video_files):
            await status_message.edit_text("❌ **Failed to analyze some video files!**")
            return None
            
        # Analyze compatibility
        compatibility = CompatibilityAnalyzer.analyze_compatibility(valid_metadata)
        
        # Choose strategy if adaptive
        if strategy == MergeStrategy.ADAPTIVE:
            strategy = compatibility['strategy']
            if not compatibility['compatible']:
                await status_message.edit_text(
                    f"⚠️ **Video compatibility issues detected:**\n"
                    f"• {', '.join(compatibility['reasons'])}\n"
                    f"🔄 **Using {strategy.value} strategy...**"
                )
        
        # Execute merge based on strategy
        try:
            if strategy == MergeStrategy.FAST_CONCAT and compatibility['compatible']:
                return await self._fast_concat_merge(video_files, valid_metadata, status_message)
            elif strategy == MergeStrategy.SMART_SCALE:
                return await self._smart_scale_merge(video_files, valid_metadata, compatibility, status_message)
            elif strategy == MergeStrategy.GPU_ACCELERATED and any(self.hardware_caps.values()):
                return await self._gpu_accelerated_merge(video_files, valid_metadata, compatibility, status_message)
            else:
                return await self._filter_complex_merge(video_files, valid_metadata, compatibility, status_message)
                
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            await status_message.edit_text(f"❌ **Merge failed:** {str(e)}")
            return None
    
    async def _fast_concat_merge(
        self, 
        video_files: List[str], 
        metadata_list: List[VideoMetadata], 
        status_message
    ) -> Optional[str]:
        """Fast concatenation without re-encoding"""
        output_path = os.path.join(self.user_download_dir, f"merged_fast_{int(time.time())}.mkv")
        inputs_file = os.path.join(self.user_download_dir, "inputs.txt")
        
        # Create inputs file with absolute paths
        with open(inputs_file, 'w', encoding='utf-8') as f:
            for file in video_files:
                abs_path = os.path.abspath(file)
                formatted_path = abs_path.replace("'", "'\''")
                f.write(f"file '{formatted_path}'\n")
        
        await status_message.edit_text("🚀 **Fast Merge in Progress...**")
        
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-f', 'concat', '-safe', '0', '-i', inputs_file,
            '-c', 'copy', '-movflags', '+faststart', '-y', output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        os.remove(inputs_file)
        
        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            await status_message.edit_text("✅ **Fast Merge Complete!**")
            return output_path
        else:
            logger.error(f"Fast merge failed: {stderr.decode()}")
            return None
    
    async def _smart_scale_merge(
        self, 
        video_files: List[str], 
        metadata_list: List[VideoMetadata], 
        compatibility: Dict[str, Any], 
        status_message
    ) -> Optional[str]:
        """Smart scaling merge for different resolutions"""
        output_path = os.path.join(self.user_download_dir, f"merged_scaled_{int(time.time())}.mkv")
        
        # Determine target resolution (use most common or highest quality)
        resolutions = [(m.width, m.height) for m in metadata_list]
        target_resolution = max(set(resolutions), key=resolutions.count)
        target_width, target_height = target_resolution
        
        await status_message.edit_text(
            f"📐 **Smart Scaling Merge**\n"
            f"Target Resolution: {target_width}x{target_height}"
        )
        
        # Build filter complex for scaling and concatenation
        filter_parts = []
        input_args = []
        
        for i, (file, metadata) in enumerate(zip(video_files, metadata_list)):
            input_args.extend(['-i', file])
            
            # Scale if necessary
            if (metadata.width, metadata.height) != target_resolution:
                filter_parts.append(
                    f"[{i}:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                    f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2[v{i}]"
                )
                video_ref = f"v{i}"
            else:
                video_ref = f"{i}:v"
            
            filter_parts.append(f"[{video_ref}][{i}:a]")
        
        filter_complex = "".join(filter_parts) + f"concat=n={len(video_files)}:v=1:a=1[outv][outa]"
        
        # Choose encoder based on quality profile and hardware
        video_encoder, encoder_opts = self._get_optimal_encoder()
        
        command = [
            'ffmpeg', '-hide_banner', *input_args,
            '-filter_complex', filter_complex,
            '-map', '[outv]', '-map', '[outa]',
            '-c:v', video_encoder, *encoder_opts,
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            '-progress', 'pipe:1', '-y', output_path
        ]
        
        return await self._execute_with_progress(command, metadata_list, status_message, output_path, "Smart Scaling")
    
    async def _gpu_accelerated_merge(
        self, 
        video_files: List[str], 
        metadata_list: List[VideoMetadata], 
        compatibility: Dict[str, Any], 
        status_message
    ) -> Optional[str]:
        """GPU-accelerated merge for high performance"""
        output_path = os.path.join(self.user_download_dir, f"merged_gpu_{int(time.time())}.mkv")
        
        # Choose GPU encoder
        gpu_encoder = self._get_gpu_encoder()
        if not gpu_encoder:
            logger.warning("No GPU encoder available, falling back to CPU")
            return await self._filter_complex_merge(video_files, metadata_list, compatibility, status_message)
        
        await status_message.edit_text("🚀 **GPU-Accelerated Merge**")
        
        # Build GPU-accelerated command
        input_args = []
        filter_parts = []
        
        for i, file in enumerate(video_files):
            input_args.extend(['-hwaccel', 'auto', '-i', file])
            filter_parts.append(f"[{i}:v][{i}:a]")
        
        filter_complex = "".join(filter_parts) + f"concat=n={len(video_files)}:v=1:a=1[outv][outa]"
        
        command = [
            'ffmpeg', '-hide_banner', *input_args,
            '-filter_complex', filter_complex,
            '-map', '[outv]', '-map', '[outa]',
            '-c:v', gpu_encoder, '-preset', 'p4', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            '-progress', 'pipe:1', '-y', output_path
        ]
        
        return await self._execute_with_progress(command, metadata_list, status_message, output_path, "GPU-Accelerated")
    
    async def _filter_complex_merge(
        self, 
        video_files: List[str], 
        metadata_list: List[VideoMetadata], 
        compatibility: Dict[str, Any], 
        status_message
    ) -> Optional[str]:
        """Robust filter complex merge with re-encoding"""
        output_path = os.path.join(self.user_download_dir, f"merged_robust_{int(time.time())}.mkv")
        
        await status_message.edit_text("⚙️ **Robust Merge with Re-encoding**")
        
        input_args = []
        filter_parts = []
        
        for i, file in enumerate(video_files):
            input_args.extend(['-i', file])
            filter_parts.append(f"[{i}:v:0][{i}:a:0]")
        
        filter_complex = "".join(filter_parts) + f"concat=n={len(video_files)}:v=1:a=1[outv][outa]"
        
        # Choose optimal encoder
        video_encoder, encoder_opts = self._get_optimal_encoder()
        
        command = [
            'ffmpeg', '-hide_banner', *input_args,
            '-filter_complex', filter_complex,
            '-map', '[outv]', '-map', '[outa]',
            '-c:v', video_encoder, *encoder_opts,
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart',
            '-progress', 'pipe:1', '-y', output_path
        ]
        
        return await self._execute_with_progress(command, metadata_list, status_message, output_path, "Robust")
    
    async def _execute_with_progress(
        self, 
        command: List[str], 
        metadata_list: List[VideoMetadata], 
        status_message, 
        output_path: str, 
        method_name: str
    ) -> Optional[str]:
        """Execute FFmpeg command with progress tracking"""
        total_duration = sum(m.duration for m in metadata_list)
        
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        start_time = time.time()
        
        # Progress monitoring
        while process.returncode is None:
            try:
                line_bytes = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                if not line_bytes:
                    break
                    
                line = line_bytes.decode('utf-8').strip()
                
                if 'out_time_ms' in line:
                    parts = line.split('=')
                    if len(parts) > 1 and parts[1].strip().isdigit():
                        current_time_ms = int(parts[1])
                        if total_duration > 0:
                            progress_percent = max(0, min(1, (current_time_ms / 1000000) / total_duration))
                            elapsed_time = time.time() - start_time
                            
                            progress_text = (
                                f"⚙️ **{method_name} Merge in Progress**\n"
                                f"➢ {get_progress_bar(progress_percent)} `{progress_percent:.1%}`\n"
                                f"➢ **Time Left:** `{get_time_left(elapsed_time, progress_percent)}`"
                            )
                            await smart_progress_editor(status_message, progress_text)
                            
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.debug(f"Progress parsing error: {e}")
                continue
        
        await process.wait()
        
        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            await status_message.edit_text(f"✅ **{method_name} Merge Complete!**")
            return output_path
        else:
            stderr = await process.stderr.read()
            error_output = stderr.decode().strip()
            logger.error(f"{method_name} merge failed: {error_output}")
            await status_message.edit_text(f"❌ **{method_name} Merge Failed!**")
            return None
    
    def _get_optimal_encoder(self) -> Tuple[str, List[str]]:
        """Get optimal encoder based on quality profile and hardware"""
        if self.quality_profile == QualityProfile.PRESERVE_QUALITY:
            return 'libx264', ['-crf', '18', '-preset', 'slower']
        elif self.quality_profile == QualityProfile.ULTRA_FAST:
            return 'libx264', ['-crf', '28', '-preset', 'ultrafast']
        elif self.quality_profile == QualityProfile.FAST:
            return 'libx264', ['-crf', '23', '-preset', 'fast']
        elif self.quality_profile == QualityProfile.MEDIUM:
            return 'libx264', ['-crf', '23', '-preset', 'medium']
        else:  # SLOW
            return 'libx264', ['-crf', '20', '-preset', 'slow']
    
    def _get_gpu_encoder(self) -> Optional[str]:
        """Get available GPU encoder"""
        if self.hardware_caps.get('nvidia'):
            return 'h264_nvenc'
        elif self.hardware_caps.get('intel'):
            return 'h264_qsv'
        elif self.hardware_caps.get('amd'):
            return 'h264_amf'
        elif self.hardware_caps.get('apple'):
            return 'h264_videotoolbox'
        return None

# --- Main Public Functions (Backward Compatible) ---
async def merge_videos(
    video_files: List[str], 
    user_id: int, 
    status_message, 
    strategy: MergeStrategy = MergeStrategy.ADAPTIVE,
    quality_profile: QualityProfile = QualityProfile.FAST
) -> Optional[str]:
    """
    Advanced video merger - main entry point
    
    Args:
        video_files: List of video file paths to merge
        user_id: User ID for directory management
        status_message: Message object for progress updates
        strategy: Merge strategy to use
        quality_profile: Quality profile for encoding
    
    Returns:
        Path to merged video file or None if failed
    """
    merger = AdvancedVideoMerger(user_id, quality_profile)
    return await merger.merge_videos_advanced(
        video_files, status_message, strategy
    )

# Backward compatibility functions
async def _merge_videos_filter(video_files: List[str], user_id: int, status_message) -> str | None:
    """Backward compatibility wrapper"""
    merger = AdvancedVideoMerger(user_id)
    return await merger.merge_videos_advanced(
        video_files, status_message, MergeStrategy.FILTER_COMPLEX
    )
