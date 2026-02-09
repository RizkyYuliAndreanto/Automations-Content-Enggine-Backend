"""
Modul B: The Editor Brain (Local LLM)
======================================
Bertugas mengubah teks mentah menjadi naskah video terstruktur.

Engine: Ollama (Gemma 2B)
Input: Raw text dari scraper
Output: Strict JSON dengan segments (text, visual_keyword, duration_estimate)
"""

import json
import re
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config


@dataclass
class Segment:
    """Satu segment narasi video"""
    text: str
    visual_keyword: str
    duration_estimate: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass 
class VideoScript:
    """Script video lengkap hasil generate LLM"""
    segments: List[Segment]
    total_duration: float
    title: str = ""
    source_url: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "source_url": self.source_url,
            "total_duration": self.total_duration,
            "segments": [seg.to_dict() for seg in self.segments]
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class ScriptWriter:
    """
    Class untuk generate script video menggunakan Ollama LLM.
    
    Fitur:
    - Convert raw text ke structured JSON
    - Extract visual keywords per kalimat
    - Estimate durasi per segment
    - Style bahasa kasual Indonesia
    """
    
    def __init__(self):
        self.ollama_url = config.env.OLLAMA_URL
        self.model = config.llm_model
        self.max_duration = config.max_script_duration
        
        # System prompt untuk style dan format
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Build system prompt berdasarkan config"""
        
        style_guide = {
            "casual": "santai dan friendly, seperti ngobrol sama teman",
            "gaul": "pakai bahasa gaul Jakarta, banyak singkatan",
            "formal": "bahasa Indonesia baku dan profesional"
        }
        
        style = style_guide.get(config.content_style, style_guide["casual"])
        
        return f"""Kamu adalah script writer untuk video fakta menarik Indonesia.

TUGAS:
1. Ubah teks input menjadi narasi video pendek (maksimal {self.max_duration} detik)
2. Gunakan bahasa Indonesia yang {style}
3. Bagi menjadi beberapa segment (kalimat)
4. Untuk setiap kalimat, ekstrak visual_keyword LANGSUNG DARI KALIMAT (kata kunci utama yang disebutkan)

ATURAN PENTING - JANGAN BUAT SEGMENT UNTUK:
- JANGAN buat segment dengan text "Judul" atau "Konten" atau "Sumber"
- JANGAN buat segment yang hanya berisi label metadata
- LANGSUNG mulai dengan narasi konten faktual
- Contoh SALAH: "Judul: Piramida Mesir" - JANGAN BUAT INI!
- Contoh BENAR: "Piramida Mesir adalah bangunan kuno yang megah"

ATURAN VISUAL KEYWORD (CRITICAL):
- EKSTRAK kata kunci LANGSUNG dari kalimat narasi
- Contoh: "Mesir adalah negara di Afrika" → visual_keyword: "Mesir"
- Contoh: "Piramida Giza terletak di perbatasan" → visual_keyword: "Piramida Giza perbatasan"
- Contoh: "Teleskop Hubble mengorbit Bumi" → visual_keyword: "Teleskop Hubble orbit Bumi"
- JANGAN buat keyword generic seperti "country", "building", "space" - gunakan NAMA SPESIFIK dari narasi
- Keyword HARUS dalam bahasa yang sama dengan objek (Mesir, Piramida, Indonesia, dll)
- Setiap visual_keyword harus SINKRON dengan apa yang dibicarakan di kalimat
- SETIAP SEGMENT HARUS PUNYA KEYWORD YANG BERBEDA - JANGAN ADA DUPLIKAT!
- Jika topik sama, tambahkan detail berbeda (misal: "Mesir panorama", "Mesir piramida", "Mesir sungai nil")
- Estimasi durasi: ~150 kata per menit (2.5 kata per detik)
- Total durasi semua segment maksimal {self.max_duration} detik

OUTPUT FORMAT (HARUS JSON VALID):
{{
  "segments": [
    {{
      "text": "Kalimat narasi dalam Bahasa Indonesia",
      "visual_keyword": "kata kunci spesifik yang DISEBUTKAN dalam kalimat (extract dari text)",
      "duration_estimate": 3.5
    }}
  ]
}}

PENTING: Output HANYA JSON, tanpa markdown code block atau penjelasan lain."""
    
    def _build_user_prompt(self, raw_text: str) -> str:
        """Build user prompt dengan raw text"""
        return f"""Ubah teks berikut menjadi script video fakta menarik:

---
{raw_text}
---

Buat script yang engaging dengan durasi total maksimal {self.max_duration} detik.
Output dalam format JSON sesuai instruksi."""
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_ollama(self, prompt: str) -> str:
        """
        Call Ollama API untuk generate response.
        
        Args:
            prompt: Full prompt (system + user)
            
        Returns:
            Generated text response
        """
        url = f"{self.ollama_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": config.llm_temperature,
                "num_predict": config.llm_max_tokens,
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=120) as response:
                if response.status != 200:
                    error = await response.text()
                    raise Exception(f"Ollama error: {error}")
                
                result = await response.json()
                return result.get("response", "")
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """
        Parse JSON dari response LLM.
        Handle berbagai format output yang mungkin.
        """
        # Clean response
        cleaned = response.strip()
        
        # Remove markdown code blocks jika ada
        if "```json" in cleaned:
            match = re.search(r'```json\s*(.*?)\s*```', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
        elif "```" in cleaned:
            match = re.search(r'```\s*(.*?)\s*```', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
        
        # Try parse JSON
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try find JSON object in response
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        
        return None
    
    def _validate_and_fix_segments(self, data: Dict) -> List[Segment]:
        """
        Validate dan fix segments dari LLM response.
        Includes deduplication of visual keywords.
        """
        segments = []
        raw_segments = data.get("segments", [])
        
        # Track used keywords to prevent duplicates
        used_keywords = {}  # keyword -> count
        
        # Metadata labels yang harus difilter dari narasi
        metadata_labels = [
            "judul", "konten", "sumber", "title", "content", "source",
            "judul video", "konten video", "timer", "logo"
        ]
        
        for seg in raw_segments:
            text = seg.get("text", "").strip()
            keyword = seg.get("visual_keyword", "").strip()
            duration = seg.get("duration_estimate", 3.0)
            
            if not text:
                continue
            
            # FILTER: Skip segments yang hanya berisi metadata labels
            text_lower = text.lower()
            is_metadata = False
            for label in metadata_labels:
                # Skip jika text dimulai dengan label atau HANYA berisi label
                if text_lower.startswith(label + ":") or text_lower.startswith(label + " :"):
                    is_metadata = True
                    break
                if text_lower == label or text_lower.rstrip(".!?") == label:
                    is_metadata = True
                    break
            
            if is_metadata:
                print(f"  ⚠️ Skipping metadata segment: '{text[:30]}...'")
                continue
            
            # Fix keyword jika kosong
            if not keyword:
                # Extract noun dari text sebagai fallback
                words = text.split()
                keyword = " ".join(words[:3]) if len(words) > 3 else text
            
            # DEDUPLICATION: Make keyword unique if already used
            keyword_lower = keyword.lower()
            if keyword_lower in used_keywords:
                used_keywords[keyword_lower] += 1
                count = used_keywords[keyword_lower]
                
                # Try to extract additional context from text
                text_words = text.split()
                extra_words = [w for w in text_words if w.lower() not in keyword_lower and len(w) > 2]
                
                if extra_words:
                    # Add context from text to make it unique
                    keyword = f"{keyword} {extra_words[0]}"
                else:
                    # Add variation suffixes
                    variations = ["detail", "closeup", "wide", "panorama", "scene", "view"]
                    if count <= len(variations):
                        keyword = f"{keyword} {variations[count-1]}"
                    else:
                        keyword = f"{keyword} {count}"
            else:
                used_keywords[keyword_lower] = 1
            
            # Validate duration
            if not isinstance(duration, (int, float)):
                # Estimate: ~2.5 words per second
                word_count = len(text.split())
                duration = word_count / 2.5
            
            # Clamp duration
            duration = max(config.min_clip_duration, min(duration, config.max_clip_duration * 2))
            
            segments.append(Segment(
                text=text,
                visual_keyword=keyword,
                duration_estimate=float(duration)
            ))
        
        return segments
    
    async def generate_script(
        self, 
        raw_text: str,
        title: str = "",
        source_url: str = ""
    ) -> Optional[VideoScript]:
        """
        Generate video script dari raw text.
        
        Args:
            raw_text: Teks mentah dari scraper
            title: Judul original (opsional)
            source_url: URL sumber (opsional)
            
        Returns:
            VideoScript object atau None jika gagal
        """
        print(f"🧠 Generating script dengan {self.model}...")
        
        # Build full prompt
        full_prompt = f"{self.system_prompt}\n\nUSER:\n{self._build_user_prompt(raw_text)}"
        
        try:
            # Call LLM
            response = await self._call_ollama(full_prompt)
            
            # Parse JSON
            data = self._parse_json_response(response)
            
            if not data:
                print("❌ Gagal parse JSON dari LLM response")
                print(f"Raw response: {response[:500]}...")
                return None
            
            # Validate segments
            segments = self._validate_and_fix_segments(data)
            
            if not segments:
                print("❌ Tidak ada segment valid dari LLM")
                return None
            
            # Calculate total duration
            total_duration = sum(seg.duration_estimate for seg in segments)
            
            script = VideoScript(
                segments=segments,
                total_duration=total_duration,
                title=title,
                source_url=source_url
            )
            
            print(f"✅ Script generated: {len(segments)} segments, {total_duration:.1f}s total")
            
            return script
            
        except Exception as e:
            print(f"❌ Error generating script: {e}")
            return None
    
    async def check_ollama_status(self) -> bool:
        """Check apakah Ollama server running dan model tersedia"""
        try:
            url = f"{self.ollama_url}/api/tags"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = [m["name"] for m in data.get("models", [])]
                        
                        if self.model in models or any(self.model in m for m in models):
                            print(f"✅ Ollama ready dengan model: {self.model}")
                            return True
                        else:
                            print(f"⚠️ Model {self.model} tidak ditemukan. Available: {models}")
                            return False
        except Exception as e:
            print(f"❌ Ollama tidak tersedia: {e}")
            return False


# Singleton instance
writer = ScriptWriter()


async def generate(raw_text: str, title: str = "", source_url: str = "") -> Optional[VideoScript]:
    """
    Entry point untuk modul LLM.
    
    Args:
        raw_text: Teks mentah dari scraper
        title: Judul original
        source_url: URL sumber
        
    Returns:
        VideoScript object
    """
    return await writer.generate_script(raw_text, title, source_url)


async def check_status() -> bool:
    """Check Ollama status"""
    return await writer.check_ollama_status()


# Test module
if __name__ == "__main__":
    async def test():
        # Check status
        if not await check_status():
            print("Pastikan Ollama running: ollama serve")
            return
        
        # Test generate
        sample_text = """
        Tahukah kamu bahwa madu adalah satu-satunya makanan yang tidak pernah basi?
        Para arkeolog menemukan pot madu di makam Fir'aun Mesir yang berusia 3000 tahun,
        dan madu tersebut masih bisa dimakan! Hal ini karena madu memiliki kandungan
        gula yang sangat tinggi dan pH yang rendah, sehingga bakteri tidak bisa bertahan hidup.
        """
        
        script = await generate(sample_text, "Fakta Madu")
        
        if script:
            print("\n📝 Generated Script:")
            print(script.to_json())
    
    asyncio.run(test())
