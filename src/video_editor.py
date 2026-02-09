"""
Modul E: The Director (Video Assembly)
=======================================
Bertugas merakit video final dari audio dan footage.

Engine: MoviePy + FFmpeg
Features:
- Clip duration logic (MAX/MIN clip duration)
- Audio ducking dengan background music
- Subtitle burning
- Smart clip splitting

CRITICAL LOGIC:
- Jika audio > MAX_CLIP_DURATION: Split visual menjadi multiple clips
- Jika audio < MIN_CLIP_DURATION: Extend atau slow motion
"""

import os
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
import json
import tempfile

from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    CompositeAudioClip, concatenate_videoclips, TextClip,
    ColorClip
)
from moviepy.video.fx.all import resize, crop, speedx
from moviepy.audio.fx.all import volumex
import numpy as np

from config import config
from src.llm_engine import VideoScript, Segment
from src.tts_engine import AudioSegment
from src.asset_manager import VideoAsset


@dataclass
class ClipPart:
    """Represents a part of a video clip for assembly"""
    video_path: str
    audio_path: str
    start_time: float  # Start dalam audio/timeline
    duration: float
    text: str
    is_split: bool = False  # True jika ini hasil split dari segment panjang
    video_start: float = 0.0  # Start position dalam source video


class StudioEditor:
    """
    Class untuk assembly video final.
    
    Implements critical clip duration logic:
    - MAX_CLIP_DURATION: Jika audio lebih panjang, visual berganti
    - MIN_CLIP_DURATION: Jika audio terlalu pendek, extend/slow mo
    """
    
    def __init__(self):
        self.max_clip_duration = config.max_clip_duration
        self.min_clip_duration = config.min_clip_duration
        self.video_resolution = config.video_resolution
        self.video_fps = config.video_fps
        self.bg_music_volume = config.bg_music_volume
        self.output_dir = config.get_path("output")
        
        # Track used video segments to prevent repetition
        self._used_video_segments = {}  # {video_path: [used_time_ranges]}
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _reset_used_segments(self):
        """Reset tracking for new video render"""
        self._used_video_segments = {}
    
    def _get_available_segment(self, video_path: str, video_duration: float, needed_duration: float) -> Tuple[float, float]:
        """
        Get an available (unused) segment from a video.
        
        Args:
            video_path: Path to video file
            video_duration: Total video duration
            needed_duration: Duration needed for this clip
            
        Returns:
            (start_time, actual_duration) - may be less than needed if video is short
        """
        if video_path not in self._used_video_segments:
            self._used_video_segments[video_path] = []
        
        used_ranges = self._used_video_segments[video_path]
        
        # Try to find an unused segment
        potential_starts = [0.0]
        
        # Add potential start points after each used segment
        for start, end in sorted(used_ranges):
            if end < video_duration:
                potential_starts.append(end)
        
        # Find a segment that doesn't overlap with used ones
        for start in potential_starts:
            end = min(start + needed_duration, video_duration)
            actual_duration = end - start
            
            if actual_duration < 0.5:  # Too short, skip
                continue
            
            # Check for overlap with used segments
            overlaps = False
            for used_start, used_end in used_ranges:
                if not (end <= used_start or start >= used_end):
                    overlaps = True
                    break
            
            if not overlaps:
                # Mark this segment as used
                self._used_video_segments[video_path].append((start, end))
                return start, actual_duration
        
        # All segments used - return from beginning but don't track (allow reuse as last resort)
        return 0.0, min(needed_duration, video_duration)
    
    def _plan_clip_splits(
        self,
        segments: List[Segment],
        audio_segments: List[AudioSegment],
        video_assets: List[VideoAsset]
    ) -> List[ClipPart]:
        """
        Plan bagaimana clip akan di-split berdasarkan durasi.
        OPTIMIZED: Prevents video repetition.
        
        CRITICAL ALGORITHM:
        1. Untuk setiap segment, cek durasi audio actual
        2. Jika audio > MAX_CLIP_DURATION:
           - Split menjadi multiple visual clips
           - Gunakan video asset berikutnya atau segment berbeda
        3. Jika audio < MIN_CLIP_DURATION:
           - Extend ke minimum atau gunakan slow motion
        """
        # Reset used segment tracking for this render
        self._reset_used_segments()
        
        clip_parts = []
        
        # Build list of all valid videos for fallback pool
        all_valid_videos = [v for v in video_assets if v and v.exists()]
        
        for i, (segment, audio) in enumerate(zip(segments, audio_segments)):
            audio_duration = audio.duration
            
            if audio_duration <= 0:
                print(f"⚠️ Segment {i} tidak punya audio, skip")
                continue
            
            # Get video asset untuk segment ini
            current_video = video_assets[i] if i < len(video_assets) else None
            
            if not current_video or not current_video.exists():
                print(f"⚠️ Segment {i} tidak punya video asset")
                continue
            
            # LOGIKA UTAMA: Cek apakah perlu split
            if audio_duration > self.max_clip_duration:
                # SPLIT MODE: Audio lebih panjang dari max clip
                parts = self._create_split_clips(
                    audio_duration=audio_duration,
                    audio_path=audio.file_path,
                    primary_video=current_video,
                    fallback_videos=video_assets[i+1:] if i+1 < len(video_assets) else [],
                    text=segment.text,
                    all_video_assets=all_valid_videos
                )
                clip_parts.extend(parts)
                
            elif audio_duration < self.min_clip_duration:
                # EXTEND MODE: Audio terlalu pendek
                # Use segment tracking for consistency
                try:
                    from moviepy.editor import VideoFileClip
                    temp_clip = VideoFileClip(current_video.file_path)
                    video_duration = temp_clip.duration
                    temp_clip.close()
                except:
                    video_duration = current_video.duration or 10.0
                
                segment_start, _ = self._get_available_segment(
                    current_video.file_path,
                    video_duration,
                    self.min_clip_duration
                )
                
                clip_parts.append(ClipPart(
                    video_path=current_video.file_path,
                    audio_path=audio.file_path,
                    start_time=0,
                    duration=self.min_clip_duration,  # Extend ke minimum
                    text=segment.text,
                    is_split=False,
                    video_start=segment_start
                ))
                
            else:
                # NORMAL MODE: Durasi dalam range
                try:
                    from moviepy.editor import VideoFileClip
                    temp_clip = VideoFileClip(current_video.file_path)
                    video_duration = temp_clip.duration
                    temp_clip.close()
                except:
                    video_duration = current_video.duration or 10.0
                
                segment_start, _ = self._get_available_segment(
                    current_video.file_path,
                    video_duration,
                    audio_duration
                )
                
                clip_parts.append(ClipPart(
                    video_path=current_video.file_path,
                    audio_path=audio.file_path,
                    start_time=0,
                    duration=audio_duration,
                    text=segment.text,
                    is_split=False,
                    video_start=segment_start
                ))
        
        return clip_parts
    
    def _create_split_clips(
        self,
        audio_duration: float,
        audio_path: str,
        primary_video: VideoAsset,
        fallback_videos: List[VideoAsset],
        text: str,
        all_video_assets: List[VideoAsset] = None
    ) -> List[ClipPart]:
        """
        Split satu segment audio menjadi multiple visual clips.
        OPTIMIZED: Prevents video repetition by using different segments.
        
        Contoh: Audio 10 detik dengan MAX_CLIP_DURATION 4 detik
        -> 3 visual clips dari BERBEDA video atau segment berbeda
        """
        parts = []
        remaining_duration = audio_duration
        time_offset = 0
        
        # Build video pool - prioritize unused videos
        video_pool = []
        seen_paths = set()
        
        # Add primary first
        if primary_video and primary_video.exists():
            video_pool.append(primary_video)
            seen_paths.add(primary_video.file_path)
        
        # Add fallbacks
        for v in fallback_videos:
            if v and v.exists() and v.file_path not in seen_paths:
                video_pool.append(v)
                seen_paths.add(v.file_path)
        
        # Add all assets as emergency pool
        if all_video_assets:
            for v in all_video_assets:
                if v and v.exists() and v.file_path not in seen_paths:
                    video_pool.append(v)
                    seen_paths.add(v.file_path)
        
        if not video_pool:
            print("  ⚠️ No videos available for split clips")
            return parts
        
        video_idx = 0
        clips_created = 0
        max_clips = 10  # Safety limit
        
        while remaining_duration > 0 and clips_created < max_clips:
            # Durasi clip ini
            clip_duration = min(self.max_clip_duration, remaining_duration)
            
            # Pastikan tidak kurang dari minimum (kecuali sisa terakhir)
            if clip_duration < self.min_clip_duration and remaining_duration > self.min_clip_duration:
                clip_duration = self.min_clip_duration
            
            # Try to find an unused video/segment
            found_segment = False
            attempts = 0
            max_attempts = len(video_pool) * 2
            
            while not found_segment and attempts < max_attempts:
                current_video = video_pool[video_idx % len(video_pool)]
                video_idx += 1
                attempts += 1
                
                # Get video duration
                try:
                    from moviepy.editor import VideoFileClip
                    temp_clip = VideoFileClip(current_video.file_path)
                    video_duration = temp_clip.duration
                    temp_clip.close()
                except:
                    video_duration = current_video.duration or 10.0
                
                # Try to get an unused segment from this video
                segment_start, actual_duration = self._get_available_segment(
                    current_video.file_path,
                    video_duration,
                    clip_duration
                )
                
                if actual_duration >= 0.5:
                    found_segment = True
                    
                    parts.append(ClipPart(
                        video_path=current_video.file_path,
                        audio_path=audio_path,
                        start_time=time_offset,
                        duration=min(actual_duration, clip_duration),
                        text=text,
                        is_split=True,
                        video_start=segment_start  # Track where in video to start
                    ))
                    
                    clip_duration = min(actual_duration, clip_duration)
            
            if not found_segment:
                # Fallback: just use first video from beginning
                parts.append(ClipPart(
                    video_path=video_pool[0].file_path,
                    audio_path=audio_path,
                    start_time=time_offset,
                    duration=clip_duration,
                    text=text,
                    is_split=True,
                    video_start=0
                ))
            
            time_offset += clip_duration
            remaining_duration -= clip_duration
            clips_created += 1
        
        return parts
    
    def _prepare_video_clip(
        self,
        video_path: str,
        duration: float,
        video_start: float = 0
    ) -> VideoFileClip:
        """
        Prepare video clip dengan resize dan crop untuk fit target resolution.
        Uses video_start to extract different segments from same video.
        """
        target_w, target_h = self.video_resolution
        
        clip = VideoFileClip(video_path)
        
        # Calculate end position
        video_end = video_start + duration
        
        # Handle if start position is beyond video duration
        if video_start >= clip.duration:
            video_start = 0  # Reset to beginning
            video_end = duration
        
        # Handle durasi - check if we need to loop
        if video_end > clip.duration:
            # Need to loop or extend
            available_duration = clip.duration - video_start
            
            if available_duration < 0.5:
                # Start from beginning
                video_start = 0
                available_duration = clip.duration
            
            if duration > available_duration:
                # Extract what we have from start position
                if video_start > 0 and video_start < clip.duration:
                    clip = clip.subclip(video_start, clip.duration)
                
                # Loop to fill remaining duration
                n_loops = int(duration / clip.duration) + 1
                clips = [clip] * n_loops
                clip = concatenate_videoclips(clips)
                clip = clip.subclip(0, duration)
            else:
                clip = clip.subclip(video_start, video_start + duration)
        else:
            # Normal subclip from video_start
            clip = clip.subclip(video_start, video_end)
        
        # Resize dan crop untuk fit target aspect ratio
        clip_w, clip_h = clip.size
        target_ratio = target_w / target_h
        clip_ratio = clip_w / clip_h
        
        if clip_ratio > target_ratio:
            # Video lebih wide, crop horizontal
            new_h = clip_h
            new_w = int(clip_h * target_ratio)
            clip = clip.crop(
                x_center=clip_w/2,
                width=new_w,
                height=new_h
            )
        else:
            # Video lebih tall, crop vertical
            new_w = clip_w
            new_h = int(clip_w / target_ratio)
            clip = clip.crop(
                y_center=clip_h/2,
                width=new_w,
                height=new_h
            )
        
        # Resize ke target resolution
        clip = clip.resize((target_w, target_h))
        
        return clip
    
    def _create_subtitle_clip(
        self,
        text: str,
        duration: float,
        video_size: Tuple[int, int]
    ) -> TextClip:
        """
        Create subtitle text overlay.
        """
        font_size = 50
        margin = 100
        
        try:
            subtitle = TextClip(
                text,
                fontsize=font_size,
                color='white',
                font='Arial-Bold',
                stroke_color='black',
                stroke_width=3,
                method='caption',
                size=(video_size[0] - margin * 2, None),
                align='center'
            )
            
            # Position di bawah tengah
            subtitle = subtitle.set_position(('center', video_size[1] - 200))
            subtitle = subtitle.set_duration(duration)
            
            return subtitle
            
        except Exception as e:
            print(f"⚠️ Subtitle error: {e}")
            return None
    
    async def render_video(
        self,
        script: VideoScript,
        audio_segments: List[AudioSegment],
        video_assets: List[VideoAsset],
        output_filename: str = "output",
        background_music_path: Optional[str] = None,
        include_subtitles: bool = True
    ) -> Optional[str]:
        """
        Render final video.
        
        Args:
            script: VideoScript dari LLM
            audio_segments: List of audio files dari TTS
            video_assets: List of video files dari asset manager
            output_filename: Nama file output (tanpa extension)
            background_music_path: Path ke background music (opsional)
            include_subtitles: Include burned subtitles
            
        Returns:
            Path ke output file atau None jika gagal
        """
        print("🎬 Memulai video rendering...")
        
        # Plan clip structure
        clip_parts = self._plan_clip_splits(
            script.segments,
            audio_segments,
            video_assets
        )
        
        if not clip_parts:
            print("❌ Tidak ada clip parts yang valid")
            return None
        
        print(f"📋 Render plan: {len(clip_parts)} clip parts dari {len(script.segments)} segments")
        
        # Build final video
        final_clips = []
        audio_clips = []
        current_time = 0
        
        for i, part in enumerate(clip_parts):
            print(f"  [{i+1}/{len(clip_parts)}] Processing: {part.duration:.2f}s from video offset {part.video_start:.1f}s...")
            
            try:
                # Prepare video - use video_start for where to begin in source video
                video_clip = self._prepare_video_clip(
                    part.video_path,
                    part.duration,
                    part.video_start  # Use video_start, not start_time
                )
                
                # Add subtitle if enabled
                if include_subtitles and part.text:
                    subtitle = self._create_subtitle_clip(
                        part.text,
                        part.duration,
                        self.video_resolution
                    )
                    
                    if subtitle:
                        video_clip = CompositeVideoClip([video_clip, subtitle])
                
                video_clip = video_clip.set_start(current_time)
                final_clips.append(video_clip)
                
                # Prepare audio
                if os.path.exists(part.audio_path):
                    audio_clip = AudioFileClip(part.audio_path)
                    
                    # Handle split audio - hanya ambil portion yang relevan
                    if part.is_split:
                        start = part.start_time
                        end = min(part.start_time + part.duration, audio_clip.duration)
                        if start < audio_clip.duration:
                            audio_clip = audio_clip.subclip(start, end)
                    
                    audio_clip = audio_clip.set_start(current_time)
                    audio_clips.append(audio_clip)
                
                current_time += part.duration
                
            except Exception as e:
                print(f"  ❌ Error processing clip: {e}")
                continue
        
        if not final_clips:
            print("❌ Tidak ada clip yang berhasil diproses")
            return None
        
        # Concatenate all clips
        print("🔧 Concatenating clips...")
        final_video = CompositeVideoClip(final_clips, size=self.video_resolution)
        
        # Combine audio
        if audio_clips:
            narration_audio = CompositeAudioClip(audio_clips)
            
            # Add background music if provided
            if background_music_path and os.path.exists(background_music_path):
                bg_music = AudioFileClip(background_music_path)
                
                # Loop bg music untuk match video duration
                if bg_music.duration < final_video.duration:
                    n_loops = int(final_video.duration / bg_music.duration) + 1
                    bg_music = concatenate_videoclips([bg_music] * n_loops)
                
                bg_music = bg_music.subclip(0, final_video.duration)
                
                # Apply ducking (reduce volume)
                db_reduction = self.bg_music_volume
                volume_factor = 10 ** (db_reduction / 20)  # Convert dB to linear
                bg_music = bg_music.volumex(volume_factor)
                
                # Combine
                final_audio = CompositeAudioClip([narration_audio, bg_music])
            else:
                final_audio = narration_audio
            
            final_video = final_video.set_audio(final_audio)
        
        # Output path
        output_path = self.output_dir / f"{output_filename}.mp4"
        
        # Render
        print(f"🎥 Rendering ke {output_path}...")
        
        try:
            final_video.write_videofile(
                str(output_path),
                fps=self.video_fps,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=str(self.output_dir / 'temp_audio.m4a'),
                remove_temp=True,
                threads=4,
                preset='medium',
                verbose=False,
                logger=None
            )
            
            # Cleanup
            final_video.close()
            for clip in final_clips:
                clip.close()
            
            print(f"✅ Video saved: {output_path}")
            return str(output_path)
            
        except Exception as e:
            print(f"❌ Render error: {e}")
            return None
    
    def get_render_preview(
        self,
        script: VideoScript,
        audio_segments: List[AudioSegment],
        video_assets: List[VideoAsset]
    ) -> Dict[str, Any]:
        """
        Get preview/plan dari render tanpa actually rendering.
        Berguna untuk debugging dan preview.
        """
        clip_parts = self._plan_clip_splits(
            script.segments,
            audio_segments,
            video_assets
        )
        
        total_duration = sum(p.duration for p in clip_parts)
        split_count = sum(1 for p in clip_parts if p.is_split)
        
        return {
            "total_segments": len(script.segments),
            "total_clip_parts": len(clip_parts),
            "total_duration": total_duration,
            "split_clips": split_count,
            "clips": [
                {
                    "index": i,
                    "duration": p.duration,
                    "is_split": p.is_split,
                    "text_preview": p.text[:50] + "..." if len(p.text) > 50 else p.text
                }
                for i, p in enumerate(clip_parts)
            ]
        }


# Singleton instance
editor = StudioEditor()


async def render(
    script: VideoScript,
    audio_segments: List[AudioSegment],
    video_assets: List[VideoAsset],
    output_filename: str = "output",
    background_music: Optional[str] = None,
    include_subtitles: bool = True
) -> Optional[str]:
    """
    Entry point untuk modul video editor.
    
    Returns path ke output file.
    """
    return await editor.render_video(
        script=script,
        audio_segments=audio_segments,
        video_assets=video_assets,
        output_filename=output_filename,
        background_music_path=background_music,
        include_subtitles=include_subtitles
    )


def preview(
    script: VideoScript,
    audio_segments: List[AudioSegment],
    video_assets: List[VideoAsset]
) -> Dict[str, Any]:
    """Get render preview/plan"""
    return editor.get_render_preview(script, audio_segments, video_assets)


# Test module
if __name__ == "__main__":
    print("🎬 Video Editor Module")
    print(f"  Max clip duration: {config.max_clip_duration}s")
    print(f"  Min clip duration: {config.min_clip_duration}s")
    print(f"  Video resolution: {config.video_resolution}")
    print(f"  Output directory: {config.get_path('output')}")
