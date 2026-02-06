"""
Indo-Fact Automation Engine
============================
Orchestrator utama yang menjalankan seluruh pipeline.

Pipeline Flow:
1. Mining: Ambil konten dari Reddit/Web
2. Scripting: Generate structured JSON script via LLM
3. Narration: Generate audio per segment via TTS
4. Assets: Download stock footage secara parallel
5. Editing: Rakit video final dengan clip duration logic

Usage:
    python main.py
    python main.py --topic "Space"
    python main.py --random
"""

import asyncio
import argparse
import uuid
from datetime import datetime
from pathlib import Path

from colorama import init, Fore, Style

from config import config

# Init colorama
init(autoreset=True)


def print_banner():
    """Print startup banner"""
    banner = f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════╗
║  {Fore.YELLOW}🎬 INDO-FACT AUTOMATION ENGINE{Fore.CYAN}                            ║
║  {Fore.WHITE}Automated Short Video Generator{Fore.CYAN}                           ║
╠═══════════════════════════════════════════════════════════╣
║  {Fore.GREEN}Version:{Fore.WHITE} {config.env.APP_VERSION:<10}{Fore.CYAN}                                      ║
║  {Fore.GREEN}LLM:{Fore.WHITE} {config.llm_model:<15}{Fore.CYAN}                                 ║
║  {Fore.GREEN}TTS:{Fore.WHITE} {config.tts_model:<15}{Fore.CYAN}                                 ║
║  {Fore.GREEN}Max Clip:{Fore.WHITE} {config.max_clip_duration}s{Fore.CYAN}                                         ║
╚═══════════════════════════════════════════════════════════╝
"""
    print(banner)


async def check_dependencies() -> bool:
    """Check semua dependencies yang dibutuhkan"""
    print(f"{Fore.YELLOW}🔍 Checking dependencies...")
    
    issues = []
    
    # Check Ollama
    from src import llm_engine
    if not await llm_engine.check_status():
        issues.append("Ollama tidak tersedia atau model belum di-pull")
    
    # Check API Keys
    from src import asset_manager
    api_status = asset_manager.check_api_keys()
    if not any(api_status.values()):
        issues.append("Tidak ada API key untuk stock footage (Pexels/Pixabay)")
    
    # Check Edge TTS
    from src import tts_engine
    tts_status = await tts_engine.check_status()
    if not tts_status["edge_tts"]:
        issues.append("Edge TTS tidak tersedia")
    
    if issues:
        print(f"{Fore.RED}❌ Dependency Issues:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    
    print(f"{Fore.GREEN}✅ All dependencies ready!")
    return True


async def run_pipeline(topic: str = "random") -> str:
    """
    Main pipeline execution.
    
    Args:
        topic: Topik untuk mining atau "random"
        
    Returns:
        Path ke output video atau error message
    """
    # Generate unique session ID
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    
    print(f"\n{Fore.CYAN}📦 Session ID: {session_id}")
    
    # === FASE 1: MINING ===
    print(f"\n{Fore.MAGENTA}{'='*60}")
    print(f"{Fore.MAGENTA}📝 FASE 1: CONTENT MINING")
    print(f"{Fore.MAGENTA}{'='*60}")
    
    from src import scraper
    
    raw_content = await scraper.run(topic)
    
    if not raw_content:
        return "❌ Gagal mendapatkan konten. Coba topik lain atau periksa Reddit API."
    
    print(f"{Fore.GREEN}✅ Konten ditemukan: {raw_content.title[:60]}...")
    
    # === FASE 2: SCRIPT GENERATION ===
    print(f"\n{Fore.MAGENTA}{'='*60}")
    print(f"{Fore.MAGENTA}🧠 FASE 2: SCRIPT GENERATION (LLM)")
    print(f"{Fore.MAGENTA}{'='*60}")
    
    from src import llm_engine
    
    raw_text = scraper.miner.format_for_llm(raw_content)
    script = await llm_engine.generate(
        raw_text, 
        title=raw_content.title,
        source_url=raw_content.url
    )
    
    if not script:
        return "❌ Gagal generate script. Pastikan Ollama running."
    
    print(f"{Fore.GREEN}✅ Script generated: {len(script.segments)} segments")
    
    # Preview segments
    for i, seg in enumerate(script.segments):
        print(f"   [{i+1}] {seg.text[:50]}... ({seg.duration_estimate:.1f}s)")
    
    # === FASE 3: AUDIO GENERATION (TTS) ===
    print(f"\n{Fore.MAGENTA}{'='*60}")
    print(f"{Fore.MAGENTA}🎙️ FASE 3: AUDIO GENERATION (TTS)")
    print(f"{Fore.MAGENTA}{'='*60}")
    
    from src import tts_engine
    
    texts = [seg.text for seg in script.segments]
    audio_segments = await tts_engine.generate(texts, session_id)
    
    success_audio = sum(1 for a in audio_segments if a.exists())
    print(f"{Fore.GREEN}✅ Audio generated: {success_audio}/{len(texts)}")
    
    if success_audio == 0:
        return "❌ Gagal generate audio. Periksa TTS engine."
    
    # === FASE 4: ASSET FETCHING (Parallel dengan fase sebelumnya) ===
    print(f"\n{Fore.MAGENTA}{'='*60}")
    print(f"{Fore.MAGENTA}📹 FASE 4: ASSET FETCHING")
    print(f"{Fore.MAGENTA}{'='*60}")
    
    from src import asset_manager
    
    keywords = [seg.visual_keyword for seg in script.segments]
    video_assets = await asset_manager.fetch(keywords, session_id)
    
    success_video = sum(1 for v in video_assets if v is not None and v.exists())
    print(f"{Fore.GREEN}✅ Assets fetched: {success_video}/{len(keywords)}")
    
    if success_video == 0:
        return "❌ Gagal download video assets. Periksa API keys."
    
    # === FASE 5: VIDEO ASSEMBLY ===
    print(f"\n{Fore.MAGENTA}{'='*60}")
    print(f"{Fore.MAGENTA}🎬 FASE 5: VIDEO ASSEMBLY")
    print(f"{Fore.MAGENTA}{'='*60}")
    
    from src import video_editor
    
    # Preview render plan
    preview = video_editor.preview(script, audio_segments, video_assets)
    print(f"{Fore.YELLOW}📋 Render Plan:")
    print(f"   Total segments: {preview['total_segments']}")
    print(f"   Total clip parts: {preview['total_clip_parts']}")
    print(f"   Split clips: {preview['split_clips']}")
    print(f"   Estimated duration: {preview['total_duration']:.1f}s")
    
    # Render
    output_name = f"indo_fact_{session_id}"
    output_path = await video_editor.render(
        script=script,
        audio_segments=audio_segments,
        video_assets=video_assets,
        output_filename=output_name,
        include_subtitles=True
    )
    
    if not output_path:
        return "❌ Gagal render video."
    
    # === SELESAI ===
    print(f"\n{Fore.GREEN}{'='*60}")
    print(f"{Fore.GREEN}✅ PIPELINE COMPLETE!")
    print(f"{Fore.GREEN}{'='*60}")
    print(f"{Fore.WHITE}📁 Output: {output_path}")
    print(f"{Fore.WHITE}⏱️ Duration: {preview['total_duration']:.1f}s")
    print(f"{Fore.WHITE}📊 Segments: {len(script.segments)}")
    
    # Save script JSON for reference
    script_path = config.get_path("input_scripts") / f"{session_id}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script.to_json())
    print(f"{Fore.WHITE}📝 Script saved: {script_path}")
    
    return f"✅ Video tersimpan: {output_path}"


async def main():
    """Main entry point"""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Indo-Fact Automation Engine")
    parser.add_argument("--topic", "-t", type=str, default=None, help="Topik spesifik")
    parser.add_argument("--random", "-r", action="store_true", help="Gunakan topik random")
    parser.add_argument("--skip-check", action="store_true", help="Skip dependency check")
    
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    # Check dependencies (unless skipped)
    if not args.skip_check:
        if not await check_dependencies():
            print(f"\n{Fore.RED}⚠️ Fix issues di atas sebelum melanjutkan.")
            print(f"{Fore.YELLOW}Tip: Jalankan dengan --skip-check untuk bypass")
            return
    
    # Determine topic
    if args.topic:
        topic = args.topic
    elif args.random:
        topic = "random"
    else:
        # Interactive mode
        topic = input(f"\n{Fore.GREEN}🎯 Masukkan topik (atau ketik 'random'): ").strip()
        if not topic:
            topic = "random"
    
    print(f"\n{Fore.CYAN}🚀 Starting pipeline for topic: {topic}")
    
    # Run pipeline
    try:
        result = await run_pipeline(topic)
        print(f"\n{Fore.CYAN}{result}")
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}⛔ Pipeline dibatalkan pengguna.")
    except Exception as e:
        print(f"\n{Fore.RED}❌ Pipeline error: {e}")
        if config.env.APP_DEBUG:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}⛔ Program dihentikan.")
