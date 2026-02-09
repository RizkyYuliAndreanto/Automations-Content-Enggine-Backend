"""
Indo-Fact Automation Engine - Configuration
============================================
Menggabungkan settings dari .env (secrets) dan config.yaml (parameters)
"""

import os
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List, Tuple

# Base directory
BASE_DIR = Path(__file__).parent


class Settings(BaseSettings):
    """Settings dari .env file (API Keys & Secrets)"""
    
    # App Config
    APP_NAME: str = "Indo-Fact Automation Engine"
    APP_DEBUG: bool = True
    APP_VERSION: str = "1.0.0"

    # External API Keys (dari .env)
    PEXELS_API_KEY: str = ""
    PIXABAY_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "IndoFactBot/1.0"

    # Service URLs
    KAGGLE_NGROK_URL: str = ""  # URL TTS Server di Kaggle (untuk XTTS)
    OLLAMA_URL: str = "http://localhost:11434"
    
    class Config:
        env_file = ".env"
        extra = "ignore"


class YAMLConfig:
    """Load configuration dari config.yaml"""
    
    def __init__(self, yaml_path: str = "config.yaml"):
        self.yaml_path = BASE_DIR / yaml_path
        self._config = self._load_yaml()
    
    def _load_yaml(self) -> dict:
        if self.yaml_path.exists():
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    @property
    def video(self) -> dict:
        return self._config.get("video", {})
    
    @property
    def content(self) -> dict:
        return self._config.get("content", {})
    
    @property
    def tts(self) -> dict:
        return self._config.get("tts", {})
    
    @property
    def llm(self) -> dict:
        return self._config.get("llm", {})
    
    @property
    def scraper(self) -> dict:
        return self._config.get("scraper", {})
    
    @property
    def assets(self) -> dict:
        return self._config.get("assets", {})
    
    @property
    def paths(self) -> dict:
        return self._config.get("paths", {})


class AppConfig:
    """Unified configuration combining .env and config.yaml"""
    
    def __init__(self):
        self.env = Settings()
        self.yaml = YAMLConfig()
        self._setup_directories()
    
    def _setup_directories(self):
        """Create necessary directories"""
        dirs = [
            self.paths.get("input_scripts", "data/input_scripts"),
            self.paths.get("temp_audio", "data/temp_audio"),
            self.paths.get("temp_video", "data/temp_video"),
            self.paths.get("output", "data/output"),
            self.paths.get("cache", "data/cache"),
            self.paths.get("models", "models"),
        ]
        for d in dirs:
            os.makedirs(BASE_DIR / d, exist_ok=True)
    
    # === Video Settings ===
    @property
    def max_clip_duration(self) -> float:
        return self.yaml.video.get("max_clip_duration", 4.0)
    
    @property
    def min_clip_duration(self) -> float:
        return self.yaml.video.get("min_clip_duration", 1.5)
    
    @property
    def video_format(self) -> str:
        return self.yaml.video.get("format", "9:16")
    
    @property
    def video_resolution(self) -> Tuple[int, int]:
        res = self.yaml.video.get("resolution", {"width": 1080, "height": 1920})
        return (res["width"], res["height"])
    
    @property
    def video_fps(self) -> int:
        return self.yaml.video.get("fps", 30)
    
    @property
    def bg_music_volume(self) -> int:
        return self.yaml.video.get("background_music_volume", -20)
    
    # === Content Settings ===
    @property
    def language(self) -> str:
        return self.yaml.content.get("language", "id")
    
    @property
    def content_style(self) -> str:
        return self.yaml.content.get("style", "casual")
    
    @property
    def max_script_duration(self) -> int:
        return self.yaml.content.get("max_script_duration", 60)
    
    # === TTS Settings ===
    @property
    def tts_model(self) -> str:
        return self.yaml.tts.get("use_model", "edge_tts")
    
    @property
    def tts_voice_id(self) -> str:
        return self.yaml.tts.get("voice_id", "id-ID-ArdiNeural")
    
    @property
    def kaggle_voice(self) -> str:
        """Voice untuk Kaggle Edge TTS server (ardi atau gadis)"""
        return self.yaml.tts.get("kaggle_voice", "ardi")
    
    @property
    def xtts_model_path(self) -> str:
        return str(BASE_DIR / self.yaml.tts.get("xtts_model_path", "models/my_voice.pth"))
    
    # === LLM Settings ===
    @property
    def llm_model(self) -> str:
        return self.yaml.llm.get("model", "gemma:2b")
    
    @property
    def llm_temperature(self) -> float:
        return self.yaml.llm.get("temperature", 0.7)
    
    @property
    def llm_max_tokens(self) -> int:
        return self.yaml.llm.get("max_tokens", 2048)
    
    # === Scraper Settings ===
    @property
    def subreddits(self) -> List[str]:
        return self.yaml.scraper.get("subreddits", ["todayilearned"])
    
    @property
    def post_limit(self) -> int:
        return self.yaml.scraper.get("post_limit", 10)
    
    @property
    def time_filter(self) -> str:
        return self.yaml.scraper.get("time_filter", "day")
    
    # === Assets Settings ===
    @property
    def asset_source(self) -> str:
        return self.yaml.assets.get("primary_source", "pexels")
    
    @property
    def cache_enabled(self) -> bool:
        return self.yaml.assets.get("cache_enabled", True)
    
    # === Paths ===
    @property
    def paths(self) -> dict:
        return self.yaml.paths
    
    def get_path(self, key: str) -> Path:
        return BASE_DIR / self.paths.get(key, f"data/{key}")


# Global config instance
config = AppConfig()
