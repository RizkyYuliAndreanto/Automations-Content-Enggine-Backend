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
    
    async def _generate_edge_tts(self, text: str, output_path: Path) -> bool:
        """
        Generate audio menggunakan Edge TTS.
        
        Edge TTS adalah layanan Microsoft yang gratis dan cepat.
        """
        try:
            import edge_tts
            
            # Create output directory if not exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            communicate = edge_tts.Communicate(text, self.voice_id)
            await communicate.save(str(output_path))
            
            return output_path.exists()
            
        except ImportError:
            print("❌ edge-tts tidak terinstall. Run: pip install edge-tts")
            return False
        except Exception as e:
            print(f"❌ Edge TTS error: {e}")
            return False
    
    async def _generate_xtts_kaggle(self, text: str, output_path: Path) -> bool:
        """
        Generate audio menggunakan XTTS v2 via Kaggle server.
        
        Memerlukan Kaggle notebook running dengan ngrok tunnel.
        """
        if not self.kaggle_url:
            print("⚠️ KAGGLE_NGROK_URL tidak dikonfigurasi")
            return False
        
        try:
            url = f"{self.kaggle_url}/generate"
            
            payload = {
                "text": text,
                "language": config.language,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=60) as response:
                    if response.status != 200:
                        error = await response.text()
                        print(f"❌ Kaggle TTS error: {error}")
                        return False
                    
                    # Download audio file
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    async with aiofiles.open(output_path, 'wb') as f:
                        await f.write(await response.read())
                    
                    return output_path.exists()
                    
        except Exception as e:
            print(f"❌ XTTS Kaggle error: {e}")
            return False
    
    async def generate_audio(
        self, 
        text: str, 
        output_path: Path,
        fallback: bool = True
    ) -> bool:
        """
        Generate audio untuk satu segment.
        
        Args:
            text: Teks untuk di-convert
            output_path: Path output file
            fallback: Fallback ke edge_tts jika xtts gagal
            
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
            # Default: edge_tts
            success = await self._generate_edge_tts(text, output_path)
        
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
            
            if success:
                # Get audio duration
                segment.duration = await self._get_audio_duration(output_path)
                print(f"    ✅ Generated: {segment.duration:.2f}s")
            else:
                print(f"    ❌ Failed")
            
            results.append(segment)
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
        
        success_count = sum(1 for s in results if s.exists())
        print(f"✅ Audio generation complete: {success_count}/{len(texts)} berhasil")
        
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
