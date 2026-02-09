"""
Indo-Fact Automation Engine - REST API
=======================================
FastAPI backend untuk testing semua fitur engine.

Usage:
    cd Backend
    uvicorn api:app --reload --port 8000
"""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from config import config

# Initialize FastAPI
app = FastAPI(
    title="Indo-Fact Automation API",
    description="API untuk testing fitur Indo-Fact Automation Engine",
    version=config.env.APP_VERSION
)

# CORS untuk frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store untuk pipeline status
pipeline_status: Dict[str, Dict[str, Any]] = {}


# === Request/Response Models ===

class StatusResponse(BaseModel):
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


class ScraperRequest(BaseModel):
    topic: str = "random"
    source: str = "wikipedia"


class LLMRequest(BaseModel):
    raw_text: str
    title: str = "Untitled"


class TTSRequest(BaseModel):
    texts: List[str]
    session_id: Optional[str] = None


class AssetRequest(BaseModel):
    keywords: List[str]
    session_id: Optional[str] = None


class PipelineRequest(BaseModel):
    topic: str = "random"
    skip_check: bool = False


# === Health Check & Status ===

@app.get("/", response_model=StatusResponse)
async def root():
    """Root endpoint - API info"""
    return StatusResponse(
        status="ok",
        message="Indo-Fact Automation API",
        data={
            "version": config.env.APP_VERSION,
            "llm_model": config.llm_model,
            "tts_model": config.tts_model
        }
    )


@app.get("/health", response_model=StatusResponse)
async def health_check():
    """Check semua dependencies"""
    from src import llm_engine, asset_manager, tts_engine
    
    issues = []
    checks = {
        "ollama": False,
        "pexels": False,
        "pixabay": False,
        "edge_tts": False,
        "xtts_kaggle": False
    }
    
    try:
        # Check Ollama
        ollama_status = await llm_engine.check_status()
        checks["ollama"] = ollama_status
        if not ollama_status:
            issues.append("Ollama tidak tersedia")
    except Exception as e:
        issues.append(f"Ollama error: {str(e)}")
    
    try:
        # Check API Keys
        api_status = asset_manager.check_api_keys()
        checks["pexels"] = api_status.get("pexels", False)
        checks["pixabay"] = api_status.get("pixabay", False)
        
        if not any(api_status.values()):
            issues.append("Tidak ada API key untuk stock footage")
    except Exception as e:
        issues.append(f"Asset manager error: {str(e)}")
    
    try:
        # Check Edge TTS
        tts_status = await tts_engine.check_status()
        checks["edge_tts"] = tts_status.get("edge_tts", False)
        checks["xtts_kaggle"] = tts_status.get("kaggle_xtts", False)
        
        if not tts_status.get("edge_tts"):
            issues.append("Edge TTS tidak tersedia")
    except Exception as e:
        issues.append(f"TTS error: {str(e)}")
    
    return StatusResponse(
        status="ok" if not issues else "warning",
        message="All systems ready!" if not issues else "; ".join(issues),
        data={"checks": checks, "issues": issues}
    )


@app.get("/config", response_model=StatusResponse)
async def get_config():
    """Get current configuration"""
    try:
        return StatusResponse(
            status="ok",
            message="Current configuration",
            data={
                "video": {
                    "max_clip_duration": config.max_clip_duration,
                    "min_clip_duration": config.min_clip_duration,
                    "format": config.video_format,
                    "resolution": list(config.video_resolution),
                    "fps": config.video_fps
                },
                "content": {
                    "language": config.language,
                    "style": config.content_style,
                    "max_script_duration": config.max_script_duration
                },
                "tts": {
                    "model": config.tts_model,
                    "voice_id": config.tts_voice_id
                },
                "llm": {
                    "model": config.llm_model,
                    "temperature": config.llm_temperature
                },
                "scraper": {
                    "subreddits": config.subreddits,
                    "post_limit": config.post_limit
                }
            }
        )
    except Exception as e:
        return StatusResponse(
            status="error",
            message=f"Config error: {str(e)}",
            data=None
        )


# === Scraper Module ===

@app.post("/scraper/mine", response_model=StatusResponse)
async def scrape_content(request: ScraperRequest):
    """
    Mining konten dari sumber yang dipilih.
    
    Sources: wikipedia, rss, reddit
    """
    try:
        from src import scraper
        
        raw_content = await scraper.run(request.topic)
        
        if not raw_content:
            return StatusResponse(
                status="error",
                message="Gagal mendapatkan konten",
                data=None
            )
        
        return StatusResponse(
            status="ok",
            message="Konten berhasil di-mining",
            data={
                "title": raw_content.title,
                "body": raw_content.body,
                "source": raw_content.source,
                "url": raw_content.url,
                "category": raw_content.category
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scraper/wikipedia/random", response_model=StatusResponse)
async def get_random_wikipedia():
    """Get random Wikipedia article"""
    try:
        from src.scraper import ContentMiner
        
        miner = ContentMiner()
        content = await miner.get_wikipedia_random()
        
        if not content:
            return StatusResponse(
                status="error",
                message="Gagal mendapatkan artikel Wikipedia",
                data=None
            )
        
        return StatusResponse(
            status="ok",
            message="Artikel Wikipedia berhasil diambil",
            data=content.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scraper/wikipedia/search", response_model=StatusResponse)
async def search_wikipedia(query: str):
    """Search Wikipedia by query"""
    try:
        from src.scraper import ContentMiner
        
        miner = ContentMiner()
        content = await miner.search_wikipedia(query)
        
        if not content:
            return StatusResponse(
                status="error",
                message=f"Tidak ditemukan hasil untuk '{query}'",
                data=None
            )
        
        return StatusResponse(
            status="ok",
            message=f"Artikel ditemukan untuk '{query}'",
            data=content.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === LLM Module ===

@app.get("/llm/status", response_model=StatusResponse)
async def llm_status():
    """Check status LLM (Ollama)"""
    try:
        from src import llm_engine
        
        is_available = await llm_engine.check_status()
        
        return StatusResponse(
            status="ok" if is_available else "error",
            message="Ollama tersedia" if is_available else "Ollama tidak tersedia",
            data={
                "available": is_available,
                "model": config.llm_model,
                "url": config.env.OLLAMA_URL
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/llm/generate", response_model=StatusResponse)
async def generate_script(request: LLMRequest):
    """
    Generate video script dari raw text.
    
    Returns structured script dengan segments.
    """
    try:
        from src import llm_engine
        
        script = await llm_engine.generate(
            request.raw_text,
            title=request.title
        )
        
        if not script:
            return StatusResponse(
                status="error",
                message="Gagal generate script",
                data=None
            )
        
        return StatusResponse(
            status="ok",
            message=f"Script generated: {len(script.segments)} segments",
            data=script.to_dict()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === TTS Module ===

@app.get("/tts/status", response_model=StatusResponse)
async def tts_status():
    """Check status TTS engines"""
    try:
        from src import tts_engine
        
        status = await tts_engine.check_status()
        
        return StatusResponse(
            status="ok",
            message="TTS status checked",
            data={
                "edge_tts": status.get("edge_tts", False),
                "xtts_kaggle": status.get("xtts_kaggle", False),
                "current_model": config.tts_model,
                "voice_id": config.tts_voice_id
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tts/voices", response_model=StatusResponse)
async def list_voices():
    """List available Edge TTS voices"""
    try:
        import edge_tts
        
        voices = await edge_tts.list_voices()
        
        # Filter Indonesian voices
        id_voices = [v for v in voices if v.get("Locale", "").startswith("id-ID")]
        
        return StatusResponse(
            status="ok",
            message=f"Found {len(id_voices)} Indonesian voices",
            data={
                "voices": id_voices,
                "current_voice": config.tts_voice_id
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts/generate", response_model=StatusResponse)
async def generate_audio(request: TTSRequest):
    """
    Generate audio dari list teks.
    
    Returns list paths ke file audio.
    """
    try:
        from src import tts_engine
        
        session_id = request.session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        
        audio_segments = await tts_engine.generate(request.texts, session_id)
        
        results = []
        for seg in audio_segments:
            results.append({
                "index": seg.index,
                "text": seg.text[:50] + "..." if len(seg.text) > 50 else seg.text,
                "file_path": seg.file_path,
                "exists": seg.exists(),
                "duration": seg.duration
            })
        
        success_count = sum(1 for r in results if r["exists"])
        
        return StatusResponse(
            status="ok" if success_count > 0 else "error",
            message=f"Generated {success_count}/{len(request.texts)} audio files",
            data={
                "session_id": session_id,
                "segments": results
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts/preview", response_model=StatusResponse)
async def preview_tts(text: str):
    """Generate preview audio for single text"""
    try:
        from src import tts_engine
        
        session_id = f"preview_{uuid.uuid4().hex[:8]}"
        audio_segments = await tts_engine.generate([text], session_id)
        
        if audio_segments and audio_segments[0].exists():
            return StatusResponse(
                status="ok",
                message="Preview audio generated",
                data={
                    "file_path": audio_segments[0].file_path,
                    "duration": audio_segments[0].duration
                }
            )
        
        return StatusResponse(
            status="error",
            message="Failed to generate preview",
            data=None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Asset Manager Module ===

@app.get("/assets/status", response_model=StatusResponse)
async def assets_status():
    """Check status API keys untuk stock footage"""
    try:
        from src import asset_manager
        
        api_status = asset_manager.check_api_keys()
        
        return StatusResponse(
            status="ok" if any(api_status.values()) else "error",
            message="API keys status",
            data={
                "pexels": api_status.get("pexels", False),
                "pixabay": api_status.get("pixabay", False),
                "primary_source": config.asset_source,
                "cache_enabled": config.cache_enabled
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/assets/search", response_model=StatusResponse)
async def search_assets(keyword: str, source: str = "pexels"):
    """
    Search video assets without downloading.
    
    Returns metadata only.
    """
    try:
        from src.asset_manager import StockDownloader
        
        downloader = StockDownloader()
        
        if source == "pexels":
            result = await downloader._search_pexels(keyword)
        else:
            result = await downloader._search_pixabay(keyword)
        
        if not result:
            return StatusResponse(
                status="error",
                message=f"No results for '{keyword}'",
                data=None
            )
        
        return StatusResponse(
            status="ok",
            message=f"Found video for '{keyword}'",
            data={
                "keyword": keyword,
                "source": source,
                "metadata": result
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/assets/fetch", response_model=StatusResponse)
async def fetch_assets(request: AssetRequest):
    """
    Fetch dan download video assets.
    
    Returns list paths ke file video.
    """
    try:
        from src import asset_manager
        
        session_id = request.session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        
        video_assets = await asset_manager.fetch(request.keywords, session_id)
        
        results = []
        for asset in video_assets:
            if asset:
                results.append({
                    "keyword": asset.keyword,
                    "file_path": asset.file_path,
                    "exists": asset.exists(),
                    "source": asset.source,
                    "duration": asset.duration,
                    "orientation": asset.orientation
                })
            else:
                results.append(None)
        
        success_count = sum(1 for r in results if r and r.get("exists"))
        
        return StatusResponse(
            status="ok" if success_count > 0 else "error",
            message=f"Fetched {success_count}/{len(request.keywords)} videos",
            data={
                "session_id": session_id,
                "assets": results
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Video Editor Module ===

@app.get("/editor/preview", response_model=StatusResponse)
async def editor_preview_info():
    """Get video editor settings dan preview info"""
    return StatusResponse(
        status="ok",
        message="Video editor settings",
        data={
            "max_clip_duration": config.max_clip_duration,
            "min_clip_duration": config.min_clip_duration,
            "resolution": config.video_resolution,
            "fps": config.video_fps,
            "bg_music_volume": config.bg_music_volume
        }
    )


@app.get("/outputs", response_model=StatusResponse)
async def list_outputs():
    """List semua output video yang tersedia"""
    try:
        output_dir = config.get_path("output")
        
        videos = []
        if output_dir.exists():
            for f in output_dir.glob("*.mp4"):
                videos.append({
                    "name": f.name,
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / (1024*1024), 2),
                    "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
                })
        
        videos.sort(key=lambda x: x["created"], reverse=True)
        
        return StatusResponse(
            status="ok",
            message=f"Found {len(videos)} output videos",
            data={"videos": videos}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Full Pipeline ===

@app.post("/pipeline/start", response_model=StatusResponse)
async def start_pipeline(request: PipelineRequest, background_tasks: BackgroundTasks):
    """
    Start full pipeline di background.
    
    Returns session_id untuk tracking.
    """
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    
    pipeline_status[session_id] = {
        "status": "running",
        "phase": "initializing",
        "progress": 0,
        "message": "Starting pipeline...",
        "started_at": datetime.now().isoformat(),
        "topic": request.topic
    }
    
    background_tasks.add_task(run_pipeline_task, session_id, request.topic)
    
    return StatusResponse(
        status="ok",
        message="Pipeline started",
        data={"session_id": session_id}
    )


@app.get("/pipeline/status/{session_id}", response_model=StatusResponse)
async def get_pipeline_status(session_id: str):
    """Get status pipeline yang sedang berjalan"""
    if session_id not in pipeline_status:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return StatusResponse(
        status="ok",
        message="Pipeline status",
        data=pipeline_status[session_id]
    )


@app.get("/pipeline/list", response_model=StatusResponse)
async def list_pipelines():
    """List semua pipeline sessions"""
    return StatusResponse(
        status="ok",
        message=f"{len(pipeline_status)} pipeline sessions",
        data={"sessions": pipeline_status}
    )


async def run_pipeline_task(session_id: str, topic: str):
    """Background task untuk menjalankan pipeline"""
    try:
        from src import scraper, llm_engine, tts_engine, asset_manager, video_editor
        
        # Phase 1: Mining
        pipeline_status[session_id]["phase"] = "mining"
        pipeline_status[session_id]["progress"] = 10
        pipeline_status[session_id]["message"] = "Mining content..."
        
        raw_content = await scraper.run(topic)
        if not raw_content:
            pipeline_status[session_id]["status"] = "error"
            pipeline_status[session_id]["message"] = "Failed to mine content"
            return
        
        pipeline_status[session_id]["progress"] = 20
        pipeline_status[session_id]["message"] = f"Content found: {raw_content.title[:50]}..."
        
        # Phase 2: Script Generation
        pipeline_status[session_id]["phase"] = "scripting"
        pipeline_status[session_id]["progress"] = 30
        pipeline_status[session_id]["message"] = "Generating script..."
        
        raw_text = scraper.miner.format_for_llm(raw_content)
        script = await llm_engine.generate(raw_text, title=raw_content.title)
        
        if not script:
            pipeline_status[session_id]["status"] = "error"
            pipeline_status[session_id]["message"] = "Failed to generate script"
            return
        
        pipeline_status[session_id]["progress"] = 40
        pipeline_status[session_id]["message"] = f"Script generated: {len(script.segments)} segments"
        
        # Phase 3: TTS
        pipeline_status[session_id]["phase"] = "tts"
        pipeline_status[session_id]["progress"] = 50
        pipeline_status[session_id]["message"] = "Generating audio..."
        
        texts = [seg.text for seg in script.segments]
        audio_segments = await tts_engine.generate(texts, session_id)
        
        success_audio = sum(1 for a in audio_segments if a.exists())
        if success_audio == 0:
            pipeline_status[session_id]["status"] = "error"
            pipeline_status[session_id]["message"] = "Failed to generate audio"
            return
        
        pipeline_status[session_id]["progress"] = 60
        pipeline_status[session_id]["message"] = f"Audio generated: {success_audio}/{len(texts)}"
        
        # Phase 4: Asset Fetching
        pipeline_status[session_id]["phase"] = "assets"
        pipeline_status[session_id]["progress"] = 70
        pipeline_status[session_id]["message"] = "Fetching video assets..."
        pipeline_status[session_id]["assets_detail"] = {"total": len(script.segments), "fetched": 0, "keywords": []}
        
        keywords = [seg.visual_keyword for seg in script.segments]
        
        # Track individual asset downloads
        video_assets = []
        for i, keyword in enumerate(keywords):
            pipeline_status[session_id]["message"] = f"Downloading asset {i+1}/{len(keywords)}: {keyword}"
            pipeline_status[session_id]["assets_detail"]["keywords"].append({"keyword": keyword, "status": "downloading"})
            
            asset = await asset_manager.fetch_single(keyword, session_id)
            video_assets.append(asset)
            
            if asset and asset.exists():
                pipeline_status[session_id]["assets_detail"]["fetched"] += 1
                pipeline_status[session_id]["assets_detail"]["keywords"][i]["status"] = "success"
                pipeline_status[session_id]["assets_detail"]["keywords"][i]["source"] = asset.source
            else:
                pipeline_status[session_id]["assets_detail"]["keywords"][i]["status"] = "failed"
        
        success_video = sum(1 for v in video_assets if v is not None and v.exists())
        
        pipeline_status[session_id]["progress"] = 80
        pipeline_status[session_id]["message"] = f"Assets fetched: {success_video}/{len(keywords)}"
        
        if success_video == 0:
            pipeline_status[session_id]["status"] = "error"
            pipeline_status[session_id]["message"] = "Failed to fetch any video assets"
            return
        
        # Phase 5: Video Assembly
        pipeline_status[session_id]["phase"] = "rendering"
        pipeline_status[session_id]["progress"] = 90
        pipeline_status[session_id]["message"] = "Rendering video..."
        
        output_name = f"indo_fact_{session_id}"
        output_path = await video_editor.render(
            script=script,
            audio_segments=audio_segments,
            video_assets=video_assets,
            output_filename=output_name,
            include_subtitles=False  # Disabled: requires ImageMagick installation
        )
        
        if not output_path:
            pipeline_status[session_id]["status"] = "error"
            pipeline_status[session_id]["message"] = "Failed to render video"
            return
        
        # Complete!
        pipeline_status[session_id]["status"] = "completed"
        pipeline_status[session_id]["phase"] = "done"
        pipeline_status[session_id]["progress"] = 100
        pipeline_status[session_id]["message"] = "Pipeline completed!"
        pipeline_status[session_id]["output"] = str(output_path)
        pipeline_status[session_id]["completed_at"] = datetime.now().isoformat()
        
    except Exception as e:
        pipeline_status[session_id]["status"] = "error"
        pipeline_status[session_id]["message"] = str(e)


# === Run Server ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
