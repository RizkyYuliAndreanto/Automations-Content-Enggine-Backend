"""
Modul D: The Asset Manager (Stock Footage)
============================================
Bertugas mencari dan download video stock footage.

Source: Pexels API / Pixabay API
Features: 
- Cache berbasis hash untuk menghindari download ulang
- Async parallel download
- Filter orientasi (portrait/landscape)

Output: List file video per keyword
"""

import os
import hashlib
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any
from dataclasses import dataclass
import json

import aiohttp
import aiofiles
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config


@dataclass
class VideoAsset:
    """Data class untuk video asset"""
    keyword: str
    file_path: str
    source: str
    width: int
    height: int
    duration: float
    url: str = ""
    
    def exists(self) -> bool:
        return os.path.exists(self.file_path)
    
    @property
    def orientation(self) -> str:
        if self.height > self.width:
            return "portrait"
        elif self.width > self.height:
            return "landscape"
        return "square"


class StockDownloader:
    """
    Class untuk download stock footage dari Pexels/Pixabay.
    
    Features:
    - Hash-based caching
    - Async parallel downloads
    - Orientation filtering
    """
    
    def __init__(self):
        self.pexels_key = config.env.PEXELS_API_KEY
        self.pixabay_key = config.env.PIXABAY_API_KEY
        self.output_dir = config.get_path("temp_video")
        self.cache_dir = config.get_path("cache")
        self.cache_enabled = config.cache_enabled
        self.preferred_orientation = config.yaml.assets.get("preferred_orientation", "portrait")
        
        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load cache index
        self.cache_index_path = self.cache_dir / "video_cache.json"
        self.cache_index = self._load_cache_index()
    
    def _load_cache_index(self) -> Dict[str, str]:
        """Load cache index from disk"""
        if self.cache_index_path.exists():
            try:
                with open(self.cache_index_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_cache_index(self):
        """Save cache index to disk"""
        try:
            with open(self.cache_index_path, "w") as f:
                json.dump(self.cache_index, f, indent=2)
        except Exception as e:
            print(f"⚠️ Gagal save cache: {e}")
    
    def _keyword_hash(self, keyword: str) -> str:
        """Generate hash dari keyword untuk filename"""
        return hashlib.md5(keyword.lower().encode()).hexdigest()[:12]
    
    def _get_cached_path(self, keyword: str) -> Optional[Path]:
        """Check apakah keyword sudah ada di cache"""
        if not self.cache_enabled:
            return None
        
        hash_key = self._keyword_hash(keyword)
        
        if hash_key in self.cache_index:
            cached_path = Path(self.cache_index[hash_key])
            if cached_path.exists():
                return cached_path
        
        return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_pexels(
        self, 
        keyword: str, 
        orientation: str = "portrait"
    ) -> Optional[Dict[str, Any]]:
        """
        Search video di Pexels.
        
        Returns best matching video metadata.
        """
        if not self.pexels_key:
            return None
        
        url = "https://api.pexels.com/videos/search"
        headers = {"Authorization": self.pexels_key}
        params = {
            "query": keyword,
            "orientation": orientation,
            "size": "medium",
            "per_page": 5
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=30) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                videos = data.get("videos", [])
                
                if not videos:
                    return None
                
                # Pilih video terbaik (prioritas: durasi cukup, resolusi tinggi)
                best = None
                best_score = 0
                
                for video in videos:
                    duration = video.get("duration", 0)
                    
                    # Skip video terlalu pendek
                    if duration < config.min_clip_duration:
                        continue
                    
                    # Get best video file
                    video_files = video.get("video_files", [])
                    suitable_files = [
                        f for f in video_files 
                        if f.get("quality") in ["hd", "sd"] and f.get("width", 0) >= 720
                    ]
                    
                    if not suitable_files:
                        continue
                    
                    # Score based on duration and resolution
                    best_file = max(suitable_files, key=lambda x: x.get("width", 0))
                    score = duration * 10 + best_file.get("width", 0) / 100
                    
                    if score > best_score:
                        best_score = score
                        best = {
                            "url": best_file.get("link"),
                            "width": best_file.get("width"),
                            "height": best_file.get("height"),
                            "duration": duration,
                            "source": "pexels"
                        }
                
                return best
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_pixabay(
        self, 
        keyword: str
    ) -> Optional[Dict[str, Any]]:
        """
        Search video di Pixabay.
        
        Returns best matching video metadata.
        """
        if not self.pixabay_key:
            return None
        
        url = "https://pixabay.com/api/videos/"
        params = {
            "key": self.pixabay_key,
            "q": keyword,
            "video_type": "film",
            "per_page": 5
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                videos = data.get("hits", [])
                
                if not videos:
                    return None
                
                # Pilih video pertama yang cocok
                for video in videos:
                    duration = video.get("duration", 0)
                    
                    if duration < config.min_clip_duration:
                        continue
                    
                    # Get medium or large video
                    video_data = video.get("videos", {})
                    medium = video_data.get("medium", {})
                    large = video_data.get("large", {})
                    
                    selected = large if large.get("url") else medium
                    
                    if selected.get("url"):
                        return {
                            "url": selected.get("url"),
                            "width": selected.get("width", 1280),
                            "height": selected.get("height", 720),
                            "duration": duration,
                            "source": "pixabay"
                        }
                
                return None
    
    async def _download_video(self, url: str, output_path: Path) -> bool:
        """Download video dari URL ke file"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=120) as response:
                    if response.status != 200:
                        return False
                    
                    async with aiofiles.open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                    
                    return output_path.exists()
                    
        except Exception as e:
            print(f"❌ Download error: {e}")
            return False
    
    async def get_video_for_keyword(
        self, 
        keyword: str,
        session_id: str = "default"
    ) -> Optional[VideoAsset]:
        """
        Get video untuk keyword tertentu.
        Cek cache dulu, baru download jika tidak ada.
        
        Args:
            keyword: Visual keyword untuk search
            session_id: Session ID untuk organize files
            
        Returns:
            VideoAsset atau None
        """
        # Check cache first
        cached = self._get_cached_path(keyword)
        if cached:
            print(f"  📦 Cache hit: {keyword}")
            # Return cached asset (we don't have full metadata, estimate)
            return VideoAsset(
                keyword=keyword,
                file_path=str(cached),
                source="cache",
                width=1080,
                height=1920,
                duration=10.0
            )
        
        # Search video
        orientation = self.preferred_orientation
        video_meta = await self._search_pexels(keyword, orientation)
        
        # Fallback to pixabay
        if not video_meta:
            video_meta = await self._search_pixabay(keyword)
        
        # Fallback dengan generic keyword
        if not video_meta:
            generic_keywords = ["abstract background", "nature landscape", "city lights"]
            for generic in generic_keywords:
                video_meta = await self._search_pexels(generic, orientation)
                if video_meta:
                    print(f"  ⚠️ Using fallback: {generic}")
                    break
        
        if not video_meta:
            print(f"  ❌ No video found for: {keyword}")
            return None
        
        # Download video
        hash_key = self._keyword_hash(keyword)
        output_path = self.output_dir / session_id / f"{hash_key}.mp4"
        
        print(f"  ⬇️ Downloading: {keyword}...")
        success = await self._download_video(video_meta["url"], output_path)
        
        if not success:
            return None
        
        # Update cache
        self.cache_index[hash_key] = str(output_path)
        self._save_cache_index()
        
        return VideoAsset(
            keyword=keyword,
            file_path=str(output_path),
            source=video_meta["source"],
            width=video_meta["width"],
            height=video_meta["height"],
            duration=video_meta["duration"],
            url=video_meta["url"]
        )
    
    async def get_videos_for_keywords(
        self,
        keywords: List[str],
        session_id: str = "default"
    ) -> List[VideoAsset]:
        """
        Get videos untuk multiple keywords secara parallel.
        
        Args:
            keywords: List of visual keywords
            session_id: Session ID
            
        Returns:
            List of VideoAsset objects
        """
        print(f"📹 Fetching {len(keywords)} video assets...")
        
        # Deduplicate keywords
        unique_keywords = list(dict.fromkeys(keywords))
        
        # Create tasks for parallel download
        tasks = [
            self.get_video_for_keyword(kw, session_id)
            for kw in unique_keywords
        ]
        
        # Execute with semaphore to limit concurrent downloads
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent downloads
        
        async def bounded_download(task):
            async with semaphore:
                return await task
        
        bounded_tasks = [bounded_download(t) for t in tasks]
        results = await asyncio.gather(*bounded_tasks, return_exceptions=True)
        
        # Map back to original order
        keyword_to_asset = {}
        for kw, result in zip(unique_keywords, results):
            if isinstance(result, VideoAsset):
                keyword_to_asset[kw] = result
        
        # Build final list matching input order
        final_results = []
        for keyword in keywords:
            asset = keyword_to_asset.get(keyword)
            if asset:
                final_results.append(asset)
            else:
                # Create placeholder for missing
                final_results.append(None)
        
        success_count = sum(1 for r in final_results if r is not None)
        print(f"✅ Assets fetched: {success_count}/{len(keywords)}")
        
        return final_results


# Singleton instance
downloader = StockDownloader()


async def fetch(keywords: List[str], session_id: str = "default") -> List[VideoAsset]:
    """
    Entry point untuk modul asset manager.
    
    Args:
        keywords: List of visual keywords
        session_id: Session ID
        
    Returns:
        List of VideoAsset objects
    """
    return await downloader.get_videos_for_keywords(keywords, session_id)


async def fetch_single(keyword: str, session_id: str = "default") -> Optional[VideoAsset]:
    """Fetch single video asset"""
    return await downloader.get_video_for_keyword(keyword, session_id)


def check_api_keys() -> dict:
    """Check API keys status"""
    return {
        "pexels": bool(config.env.PEXELS_API_KEY),
        "pixabay": bool(config.env.PIXABAY_API_KEY)
    }


# Test module
if __name__ == "__main__":
    async def test():
        # Check API keys
        keys = check_api_keys()
        print("🔑 API Keys Status:")
        print(f"  Pexels: {'✅' if keys['pexels'] else '❌'}")
        print(f"  Pixabay: {'✅' if keys['pixabay'] else '❌'}")
        
        if not any(keys.values()):
            print("⚠️ Tidak ada API key yang dikonfigurasi")
            return
        
        # Test fetch
        test_keywords = [
            "honey jar pouring",
            "egyptian pyramid ancient",
            "laboratory scientist"
        ]
        
        assets = await fetch(test_keywords, "test_session")
        
        print("\n📹 Fetched Assets:")
        for asset in assets:
            if asset:
                status = "✅" if asset.exists() else "❌"
                print(f"  {status} {asset.keyword}: {asset.file_path}")
            else:
                print(f"  ❌ Missing asset")
    
    asyncio.run(test())
