"""
Indo-Fact Automation Engine - Source Modules
=============================================

Modules:
- scraper: Content mining dari Reddit dan web
- llm_engine: Script generation dengan Ollama LLM
- tts_engine: Text-to-speech dengan Edge TTS / XTTS
- asset_manager: Stock footage download dari Pexels/Pixabay
- video_editor: Video assembly dengan MoviePy
- assets: Modular asset management (new structure)
"""

import importlib

# Cache untuk module yang sudah di-import
_module_cache = {}

# Lazy imports menggunakan importlib untuk menghindari recursion
def __getattr__(name):
    if name in _module_cache:
        return _module_cache[name]
    
    if name in ("scraper", "llm_engine", "tts_engine", "asset_manager", "video_editor", "assets"):
        try:
            module = importlib.import_module(f"src.{name}")
            _module_cache[name] = module
            return module
        except ImportError as e:
            raise AttributeError(f"module 'src' has no attribute '{name}': {e}")
    
    raise AttributeError(f"module 'src' has no attribute '{name}'")

__all__ = [
    "scraper",
    "llm_engine", 
    "tts_engine",
    "asset_manager",
    "video_editor",
    "assets"
]
