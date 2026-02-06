# 🎬 Indo-Fact Automation Engine

Sistem otomasi pembuatan video fakta menarik dalam Bahasa Indonesia.

## 📋 Filosofi Desain

Sistem ini menganut prinsip **Hybrid Workflow**:

- **Heavy Training (Kaggle)**: Digunakan hanya untuk melatih model suara (TTS) agar unik
- **Lightweight Inference (Localhost)**: Digunakan untuk menjalankan pipeline pembuatan video sehari-hari
- **Modular & Async**: Setiap komponen bekerja independen namun terorkestrasi secara paralel

## 🏗️ Arsitektur

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  📝 Scraper  │────▶│  🧠 LLM      │────▶│  🎙️ TTS     │
│  (Mining)    │     │  (Scripting) │     │  (Narration) │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                     ┌──────────────┐             │
                     │  📹 Assets   │◀────────────┤
                     │  (Footage)   │             │
                     └──────┬───────┘             │
                            │                     │
                            ▼                     ▼
                     ┌─────────────────────────────┐
                     │     🎬 Video Editor         │
                     │     (Assembly + Render)     │
                     └─────────────────────────────┘
```

## 📁 Struktur Project

```
/Backend
├── config.py              # Python config loader
├── config.yaml            # Setting durasi clip, paths, parameters
├── .env                   # API keys (dari .env.example)
├── main.py                # Orchestrator (Entry point)
├── requirements.txt       # Dependencies
│
├── /data
│   ├── /input_scripts     # Hasil scraping dalam JSON
│   ├── /temp_audio        # Audio TTS per segment
│   ├── /temp_video        # Stock footage download
│   ├── /output            # Video final
│   └── /cache             # Cache untuk stock footage
│
├── /models
│   └── my_voice.pth       # Hasil training XTTS di Kaggle
│
└── /src
    ├── scraper.py         # Modul A: Content Mining
    ├── llm_engine.py      # Modul B: Script Generation
    ├── tts_engine.py      # Modul C: TTS Engine
    ├── asset_manager.py   # Modul D: Stock Footage
    └── video_editor.py    # Modul E: Video Assembly
```

## 🚀 Quick Start

### 1. Setup Environment

```powershell
# Clone/create project
cd D:\PROJECT\Automation-Project\Backend

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Setup API Keys

```powershell
# Copy .env.example ke .env
Copy-Item .env.example .env

# Edit .env dengan API keys Anda
notepad .env
```

API Keys yang dibutuhkan:

- **Pexels API**: https://www.pexels.com/api/ (gratis)
- **Reddit API**: https://www.reddit.com/prefs/apps (gratis)
- **Pixabay API** (opsional): https://pixabay.com/api/docs/

### 3. Setup Ollama

```powershell
# Install Ollama: https://ollama.com/download

# Pull model Gemma 2B
ollama pull gemma:2b

# Jalankan server (biarkan running)
ollama serve
```

### 4. Jalankan Pipeline

```powershell
# Interactive mode
python main.py

# Dengan topik spesifik
python main.py --topic "Space"

# Random topic
python main.py --random
```

## ⚙️ Konfigurasi

### config.yaml

```yaml
video:
  max_clip_duration: 4.0 # Detik. Jika audio > 4s, visual berganti
  min_clip_duration: 1.5 # Minimum durasi per clip
  format: "9:16" # Shorts/TikTok format
  fps: 30

tts:
  use_model: "edge_tts" # atau "xtts_v2" untuk custom voice
  voice_id: "id-ID-ArdiNeural"

llm:
  model: "gemma:2b"
  temperature: 0.7
```

### Clip Duration Logic

**CRITICAL FEATURE**: Video editor menerapkan logika clip duration:

1. **Jika audio > `max_clip_duration`**:
   - Visual dipotong di batas maksimum
   - Sisa durasi diisi dengan video stock berikutnya
   - Tujuan: Menjaga retensi penonton dengan visual dinamis

2. **Jika audio < `min_clip_duration`**:
   - Video di-extend ke durasi minimum
   - Atau menggunakan slow motion

## 📦 Modul Detail

### Modul A: The Miner (`scraper.py`)

- Mining dari Reddit (r/todayilearned, r/science, dll)
- Web scraping dengan Trafilatura
- Auto-cleaning text (hapus emoji, link, dsb)

### Modul B: The Editor Brain (`llm_engine.py`)

- Generate script dengan Ollama (Gemma 2B)
- Output JSON terstruktur dengan `visual_keyword` per segment
- Bahasa kasual Indonesia

### Modul C: The Narrator (`tts_engine.py`)

- Edge TTS (default): Cepat, gratis, cloud-based
- XTTS v2 (opsional): Custom voice dari Kaggle training

### Modul D: The Asset Manager (`asset_manager.py`)

- Download dari Pexels/Pixabay
- Hash-based caching
- Async parallel download

### Modul E: The Director (`video_editor.py`)

- Clip duration logic (split jika audio terlalu panjang)
- Subtitle burning
- Audio ducking dengan background music
- Output: MP4 dengan codec H.264

## 🎯 Output JSON Format

Script yang dihasilkan LLM:

```json
{
  "segments": [
    {
      "text": "Tahukah kamu, kalau madu itu gak bisa basi?",
      "visual_keyword": "honey jar pouring close up",
      "duration_estimate": 3.0
    },
    {
      "text": "Para arkeolog bahkan menemukan madu di makam Mesir kuno.",
      "visual_keyword": "egyptian pyramid ancient tomb",
      "duration_estimate": 4.5
    }
  ]
}
```

## 🔧 Troubleshooting

### Ollama tidak tersedia

```powershell
# Pastikan Ollama running
ollama serve

# Cek model sudah di-pull
ollama list
```

### Edge TTS error

```powershell
# Reinstall edge-tts
pip uninstall edge-tts
pip install edge-tts
```

### Video tidak ter-render

- Pastikan FFmpeg tersedia (via imageio-ffmpeg)
- Cek disk space cukup
- Periksa file video source tidak corrupt

## 📄 License

MIT License - Feel free to use and modify!

---

Built with ❤️ for Indonesian content creators
