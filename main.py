"""
Indo-Fact Automation Engine
============================
API Server untuk frontend dashboard.

Usage:
    python main.py
    python main.py --port 8000
"""

import argparse
from colorama import init, Fore

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


def run_server(port: int = 8000):
    """Run API server untuk frontend"""
    print_banner()
    print(f"{Fore.CYAN}🌐 Starting API Server...")
    print(f"{Fore.GREEN}📡 Server berjalan di http://localhost:{port}")
    print(f"{Fore.YELLOW}💡 Buka http://localhost:5173 untuk frontend")
    print(f"{Fore.YELLOW}💡 Tekan Ctrl+C untuk menghentikan server\n")
    
    import uvicorn
    from api import app
    
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Indo-Fact Automation Engine - API Server")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port untuk API server (default: 8000)")
    
    args = parser.parse_args()
    
    try:
        run_server(args.port)
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}⛔ Server dihentikan.")
