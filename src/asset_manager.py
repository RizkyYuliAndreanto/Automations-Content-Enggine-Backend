"""
Modul D: The Asset Manager (Stock Footage)
============================================
Bertugas mencari dan download video stock footage.

⚠️  FILE INI ADALAH WRAPPER UNTUK BACKWARDS COMPATIBILITY
    Implementasi sebenarnya ada di folder src/assets/

Structure:
    src/assets/
    ├── __init__.py          # Entry point utama
    ├── models.py            # VideoAsset dataclass
    ├── cache.py             # Cache management
    ├── translator.py        # Indonesian-English translation
    ├── filters.py           # Content filtering & scoring
    ├── downloader.py        # Download utilities
    ├── manager.py           # Main orchestrator
    └── providers/           # Video source providers
        ├── base.py          # Base provider class
        ├── youtube.py       # YouTube provider
        ├── pexels.py        # Pexels API
        ├── pixabay.py       # Pixabay API
        ├── unsplash.py      # Unsplash API
        ├── nasa.py          # NASA API
        ├── wikimedia.py     # Wikimedia Commons
        └── internet_archive.py  # Internet Archive

Features: 
- Cache berbasis hash untuk menghindari download ulang
- Async parallel download
- Filter orientasi (portrait/landscape)
- Translation Indonesian → English
- Multiple video sources

Output: List file video per keyword

Usage:
    from src.asset_manager import fetch, fetch_single, VideoAsset
    
    # Fetch multiple
    assets = await fetch(["eagle", "pyramid"], session_id="my_session")
    
    # Fetch single  
    asset = await fetch_single("eagle")
"""

# Re-export semua dari package assets untuk backwards compatibility
from .assets import (
    # Main API functions
    fetch,
    fetch_single,
    check_api_keys,
    get_cache_stats,
    clear_cache,
    
    # Models
    VideoAsset,
    
    # Manager (untuk akses langsung jika diperlukan)
    asset_manager,
    AssetManager,
    
    # Cache
    cache_manager,
    CacheManager,
    
    # Translator
    translator,
    KeywordTranslator,
    
    # Filters
    content_filter,
    ContentFilter,
    
    # Downloader
    download_manager,
    DownloadManager,
)

# Backwards compatibility: StockDownloader alias
StockDownloader = AssetManager

# Backwards compatibility: downloader instance
downloader = asset_manager

__all__ = [
    # Main API
    'fetch',
    'fetch_single',
    'check_api_keys',
    'get_cache_stats',
    'clear_cache',
    
    # Models
    'VideoAsset',
    
    # Classes (backwards compatible)
    'StockDownloader',
    'AssetManager',
    
    # Instances
    'downloader',
    'asset_manager',
    'cache_manager',
    'translator',
    'content_filter',
    'download_manager',
]


# Test module
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Check API keys
        keys = check_api_keys()
        print("🔑 API Keys Status:")
        print(f"  Pexels: {'✅' if keys['pexels'] else '❌'}")
        print(f"  Pixabay: {'✅' if keys['pixabay'] else '❌'}")
        
        # Test fetch
        test_keywords = [
            "elang",
            "piramida mesir",
            "telescope galaxy"
        ]
        
        assets = await fetch(test_keywords, "test_session")
        
        print("\n📹 Fetched Assets:")
        for asset in assets:
            if asset:
                status = "✅" if asset.exists() else "❌"
                print(f"  {status} {asset.keyword}: {asset.source}")
            else:
                print(f"  ❌ Missing asset")
        
        # Cache stats
        print("\n📊 Cache Stats:")
        stats = get_cache_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    asyncio.run(test())
