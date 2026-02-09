"""
Modul C: The Narrator (TTS Engine)
===================================
Bertugas mengubah teks menjadi audio narasi.

Hybrid System:
- edge_tts: Fast fallback, cloud-based (default)
- xtts_v2: Custom voice dari Kaggle training

Output: List file audio per segment (01.wav, 02.wav, dst)
"""

import os
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
import hashlib

import aiohttp
import aiofiles

from config import config


@dataclass
class AudioSegment:
    """Data class untuk audio segment"""
    index: int
    text: str
    file_path: str
    duration: float = 0.0
    
    def exists(self) -> bool:
        return os.path.exists(self.file_path)


class Narrator:
    """
    Class untuk generate narasi audio.
    
    Supports:
    - Edge TTS (Microsoft, free, cloud-based)
    - XTTS v2 (Coqui, custom voice via Kaggle)
    """
    
    def __init__(self):
        self.tts_model = config.tts_model
        self.voice_id = config.tts_voice_id
        self.kaggle_voice = config.kaggle_voice  # Voice for Kaggle Edge TTS
        self.output_dir = config.get_path("temp_audio")
        self.kaggle_url = config.env.KAGGLE_NGROK_URL
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_audio_path(self, index: int, session_id: str = "default") -> Path:
        """Generate path untuk audio file"""
        return self.output_dir / session_id / f"{index:02d}.wav"
    
    def _text_hash(self, text: str) -> str:
        """Generate hash untuk caching"""
        return hashlib.md5(text.encode()).hexdigest()[:8]
    
    async def _generate_edge_tts(self, text: str, output_path: Path, retry_count: int = 0) -> bool:
        """
        Generate audio menggunakan Edge TTS dengan retry logic.
        
        Edge TTS adalah layanan Microsoft yang gratis dan cepat.
        Jika gagal (403 error), akan retry dengan delay eksponensial.
        """
        max_retries = 1  # Only 1 retry before fallback
        retry_delay = 12  # Longer delay (12s) to avoid rate limiting
        
        try:
            import edge_tts
            
            # Create output directory if not exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Add larger staggered delay based on retry count
            if retry_count == 0:
                import random
                await asyncio.sleep(random.uniform(2, 5))
            
            communicate = edge_tts.Communicate(text, self.voice_id)
            await communicate.save(str(output_path))
            
            if output_path.exists() and output_path.stat().st_size > 0:
                return True
            else:
                raise Exception("File tidak dibuat atau kosong")
            
        except ImportError:
            print("❌ edge-tts tidak terinstall. Run: pip install edge-tts")
            return False
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's a rate limit error (403)
            if "403" in error_msg or "Invalid response status" in error_msg:
                if retry_count < max_retries:
                    print(f"    ⚠️ Edge TTS rate limited, retry {retry_count + 1}/{max_retries} dalam {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    return await self._generate_edge_tts(text, output_path, retry_count + 1)
                else:
                    print(f"    ⚠️ Edge TTS gagal setelah {max_retries} retries (403 rate limit)")
                    return False
            else:
                print(f"    ❌ Edge TTS error: {e}")
                return False
    
    async def _check_kaggle_health(self) -> dict:
        """
        Check Kaggle server health dan status.
        
        Returns:
            Dict dengan status server, atau None jika tidak bisa konek
        """
        if not self.kaggle_url:
            return None
        
        try:
            url = f"{self.kaggle_url}/health"
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    return None
        except Exception as e:
            print(f"⚠️ Kaggle health check failed: {e}")
            return None
    
    async def _generate_xtts_kaggle(self, text: str, output_path: Path) -> bool:
        """
        Generate audio menggunakan Edge TTS via Kaggle server.
        
        Memerlukan Kaggle notebook running dengan ngrok tunnel.
        Endpoint: POST /generate
        Body: {"text": "...", "voice": "ardi"} 
        Response: audio/mp3 binary
        """
        if not self.kaggle_url:
            print("⚠️ KAGGLE_NGROK_URL tidak dikonfigurasi di .env")
            return False
        
        # Optional: Check health first
        health = await self._check_kaggle_health()
        if health:
            status = health.get('status', 'unknown')
            if status != 'ready':
                print(f"⚠️ Kaggle server status: {status}")
                if health.get('metrics', {}).get('last_error'):
                    print(f"   Last error: {health['metrics']['last_error']}")
        
        try:
            url = f"{self.kaggle_url}/generate"
            
            # Payload untuk Edge TTS Kaggle server
            payload = {
                "text": text,
                "voice": self.kaggle_voice,  # Indonesian voice (ardi=male, gadis=female)
                "rate": "+0%",    # Normal speed
                "pitch": "+0Hz"   # Normal pitch
            }
            
            # Timeout Edge TTS (lebih cepat dari XTTS)
            timeout = aiohttp.ClientTimeout(total=60)
            
            print(f"🎙️ Generating audio via Kaggle Edge TTS...")
            print(f"   Text length: {len(text)} chars")
            print(f"   Voice: {self.kaggle_voice} (Indonesian {'Male' if self.kaggle_voice == 'ardi' else 'Female'})")
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_data = await response.text()
                        try:
                            error_json = await response.json()
                            error_msg = error_json.get('error', error_data)
                        except:
                            error_msg = error_data
                        print(f"❌ Kaggle Edge TTS error ({response.status}): {error_msg}")
                        return False
                    
                    # Verify content type
                    content_type = response.headers.get('Content-Type', '')
                    if 'audio' not in content_type and 'octet-stream' not in content_type:
                        print(f"⚠️ Unexpected content type: {content_type}")
                    
                    # Download audio file (MP3 from Edge TTS)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Edge TTS returns MP3, convert to WAV if needed
                    temp_mp3_path = output_path.with_suffix('.mp3')
                    
                    audio_data = await response.read()
                    
                    async with aiofiles.open(temp_mp3_path, 'wb') as f:
                        await f.write(audio_data)
                    
                    if not temp_mp3_path.exists():
                        print("❌ Audio file tidak tersimpan")
                        return False
                    
                    # Convert MP3 to WAV for compatibility with MoviePy
                    conversion_success = False
                    
                    # Method 1: Try pydub with imageio-ffmpeg's FFmpeg
                    try:
                        from pydub import AudioSegment
                        import imageio_ffmpeg
                        
                        # Configure pydub to use imageio-ffmpeg's FFmpeg binary
                        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
                        AudioSegment.converter = ffmpeg_path
                        AudioSegment.ffprobe = ffmpeg_path.replace('ffmpeg', 'ffprobe') if 'ffprobe' not in ffmpeg_path else ffmpeg_path
                        
                        audio = AudioSegment.from_mp3(str(temp_mp3_path))
                        audio.export(str(output_path), format="wav")
                        
                        # Clean up temp MP3
                        if temp_mp3_path.exists():
                            temp_mp3_path.unlink()
                        
                        if output_path.exists():
                            file_size = output_path.stat().st_size
                            print(f"✅ Edge TTS audio saved: {output_path.name} ({file_size} bytes)")
                            return True
                        else:
                            print("❌ WAV conversion failed")
                            conversion_success = False
                    except Exception as pydub_error:
                        print(f"⚠️ pydub conversion failed: {pydub_error}")
                        conversion_success = False
                    
                    # Method 2: Use imageio-ffmpeg directly via subprocess
                    if not conversion_success:
                        try:
                            import imageio_ffmpeg
                            import subprocess
                            
                            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
                            
                            # Delete existing WAV file if exists
                            if output_path.exists():
                                output_path.unlink()
                            
                            # Convert MP3 to WAV using FFmpeg
                            cmd = [
                                ffmpeg_path, '-y', '-i', str(temp_mp3_path),
                                '-acodec', 'pcm_s16le', '-ar', '22050', '-ac', '1',
                                str(output_path)
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True)
                            
                            if temp_mp3_path.exists():
                                temp_mp3_path.unlink()
                            
                            if output_path.exists():
                                file_size = output_path.stat().st_size
                                print(f"✅ Edge TTS audio saved: {output_path.name} ({file_size} bytes)")
                                return True
                        except Exception as ffmpeg_error:
                            print(f"⚠️ FFmpeg conversion failed: {ffmpeg_error}")
                    
                    # Method 3: Fallback - just rename MP3 to WAV (MoviePy may still work)
                    print("⚠️ Using MP3 directly (no conversion)")
                    if output_path.exists():
                        output_path.unlink()
                    if temp_mp3_path.exists():
                        temp_mp3_path.rename(output_path)
                    if output_path.exists():
                        file_size = output_path.stat().st_size
                        print(f"✅ Edge TTS audio saved: {output_path.name} ({file_size} bytes)")
                        return True
                    return False
                    
        except asyncio.TimeoutError:
            print(f"❌ Kaggle Edge TTS timeout")
            return False
        except aiohttp.ClientError as e:
            print(f"❌ Kaggle connection error: {e}")
            return False
        except Exception as e:
            print(f"❌ Edge TTS Kaggle error: {e}")
            return False
    
    async def generate_audio(
        self, 
        text: str, 
        output_path: Path,
        fallback: bool = True
    ) -> bool:
        """
        Generate audio untuk satu segment dengan smart fallback.
        
        Fallback logic:
        1. Try primary engine (edge_tts atau xtts_v2)
        2. If failed, try secondary engine
        3. Ensure audio file exists and valid
        
        Args:
            text: Teks untuk di-convert
            output_path: Path output file
            fallback: Enable fallback ke engine lain
            
        Returns:
            True jika berhasil
        """
        # Choose TTS engine
        if self.tts_model == "xtts_v2":
            success = await self._generate_xtts_kaggle(text, output_path)
            
            # Fallback to edge_tts if failed
            if not success and fallback:
                print("⚠️ XTTS gagal, fallback ke Edge TTS...")
                success = await self._generate_edge_tts(text, output_path)
        else:
            # Default: edge_tts first
            success = await self._generate_edge_tts(text, output_path)
            
            # Fallback to Kaggle XTTS if Edge TTS failed
            # User's Kaggle model uses Edge TTS with Indonesian native voices
            if not success and fallback and self.kaggle_url:
                print("⚠️ Edge TTS gagal, fallback ke Kaggle Edge TTS...")
                success = await self._generate_xtts_kaggle(text, output_path)
            elif not success:
                print("❌ TTS generation failed - no fallback available")
        
        return success
    
    async def generate_all_segments(
        self,
        texts: List[str],
        session_id: str = "default"
    ) -> List[AudioSegment]:
        """
        Generate audio untuk semua segment.
        
        Args:
            texts: List of text segments
            session_id: Unique ID untuk session ini
            
        Returns:
            List of AudioSegment objects
        """
        print(f"🎙️ Generating {len(texts)} audio segments dengan {self.tts_model}...")
        
        results = []
        session_dir = self.output_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        for i, text in enumerate(texts):
            output_path = session_dir / f"{i:02d}.wav"
            
            print(f"  [{i+1}/{len(texts)}] Generating: {text[:40]}...")
            
            success = await self.generate_audio(text, output_path)
            
            segment = AudioSegment(
                index=i,
                text=text,
                file_path=str(output_path),
                duration=0.0  # Will be calculated later by video editor
            )
            
            if success and output_path.exists():
                # Get audio duration
                segment.duration = await self._get_audio_duration(output_path)
                if segment.duration > 0:
                    print(f"    ✅ Generated: {segment.duration:.2f}s")
                else:
                    print(f"    ⚠️ Audio file exists but duration is 0")
                    success = False
            else:
                # Generation failed, mark it clearly
                success = False
            
            results.append(segment)
            
            # Larger delay between segments to avoid rate limiting
            # If we're processing multiple segments, wait longer
            if i < len(texts) - 1:  # Don't delay after last segment
                delay = 8 if len(texts) > 2 else 5
                print(f"    ⏱️ Waiting {delay}s before next segment...")
                await asyncio.sleep(delay)
        
        # Count actual successful generations (file exists AND has valid duration)
        success_count = sum(1 for s in results if s.exists() and s.duration > 0)
        total_count = len(texts)
        
        if success_count == 0:
            print(f"❌ Audio generation FAILED: 0/{total_count} berhasil")
        elif success_count < total_count:
            print(f"⚠️ Audio generation partial: {success_count}/{total_count} berhasil")
        else:
            print(f"✅ Audio generation complete: {success_count}/{total_count} berhasil")
        
        return results
    
    async def _get_audio_duration(self, audio_path: Path) -> float:
        """Get durasi audio file dalam detik"""
        try:
            from moviepy.editor import AudioFileClip
            
            clip = AudioFileClip(str(audio_path))
            duration = clip.duration
            clip.close()
            
            return duration
        except Exception as e:
            print(f"⚠️ Gagal get duration: {e}")
            return 0.0
    
    async def check_edge_tts_voices(self) -> List[str]:
        """List available Edge TTS voices untuk Indonesia"""
        try:
            import edge_tts
            
            voices = await edge_tts.list_voices()
            id_voices = [v for v in voices if v["Locale"].startswith("id")]
            
            return [f"{v['ShortName']}: {v['Gender']}" for v in id_voices]
        except Exception:
            return []
    
    async def check_kaggle_status(self) -> bool:
        """Check apakah Kaggle TTS server available"""
        if not self.kaggle_url:
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.kaggle_url}/health", timeout=5) as response:
                    return response.status == 200
        except Exception:
            return False


# Singleton instance
narrator = Narrator()


async def generate(texts: List[str], session_id: str = "default") -> List[AudioSegment]:
    """
    Entry point untuk modul TTS.
    
    Args:
        texts: List of text segments
        session_id: Unique session ID
        
    Returns:
        List of AudioSegment objects
    """
    return await narrator.generate_all_segments(texts, session_id)


async def check_status() -> dict:
    """Check TTS engine status"""
    voices = await narrator.check_edge_tts_voices()
    kaggle = await narrator.check_kaggle_status()
    
    return {
        "edge_tts": len(voices) > 0,
        "edge_tts_voices": voices,
        "kaggle_xtts": kaggle,
        "active_model": config.tts_model
    }


# Test module
if __name__ == "__main__":
    async def test():
        # Check status
        status = await check_status()
        print("📊 TTS Status:")
        print(f"  Edge TTS: {'✅' if status['edge_tts'] else '❌'}")
        print(f"  Indonesian voices: {status['edge_tts_voices']}")
        print(f"  Kaggle XTTS: {'✅' if status['kaggle_xtts'] else '❌'}")
        print(f"  Active model: {status['active_model']}")
        
        # Test generate
        test_texts = [
            "Tahukah kamu, kalau madu itu gak bisa basi?",
            "Para arkeolog bahkan menemukan madu di makam Mesir kuno.",
            "Dan madu tersebut masih bisa dimakan!"
        ]
        
        segments = await generate(test_texts, "test_session")
        
        print("\n🎙️ Generated Segments:")
        for seg in segments:
            status = "✅" if seg.exists() else "❌"
            print(f"  {status} [{seg.index}] {seg.duration:.2f}s - {seg.file_path}")
    
    asyncio.run(test())
