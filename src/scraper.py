"""
Modul A: The Miner (Scraping & Cleaning)
=========================================
Bertugas mencari bahan mentah dari berbagai sumber.

Sumber yang didukung (TANPA API KEY):
- Wikipedia Indonesia (random facts) ⭐
- YouTube Transcripts (subtitle dari video fakta) ⭐ NEW!
- RSS Feeds (berita sains, teknologi)
- Web scraping langsung (situs fakta)
- Reddit (OPSIONAL, jika punya API key)

KONTEN DIJAMIN:
- Original dari sumber resmi (Wikipedia, YouTube official transcripts)
- Tanpa watermark (hanya teks/transcript)
- Dapat dimodifikasi oleh LLM menjadi script unik

Input: Keyword topik atau "random"
Output: Teks mentah (RawContent)
"""

import re
import random
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote, urljoin, parse_qs, urlparse

import trafilatura
from bs4 import BeautifulSoup
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config


@dataclass
class RawContent:
    """Data class untuk konten mentah hasil scraping"""
    title: str
    body: str
    source: str
    url: str
    author: str = "Unknown"
    score: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    category: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "source": self.source,
            "url": self.url,
            "author": self.author,
            "score": self.score,
            "created_at": self.created_at.isoformat(),
            "category": self.category
        }


class ContentMiner:
    """
    Class untuk mining konten dari berbagai sumber TANPA API KEY.
    
    Sumber Utama (Prioritas):
    1. Wikipedia Indonesia (Random article) - GRATIS, tanpa API key
    2. RSS Feeds (Kompas Sains, Detik, dll) - GRATIS
    3. Web scraping situs fakta - GRATIS
    4. Reddit (opsional, jika ada API key)
    """
    
    def __init__(self):
        # PENTING: Wikipedia API memerlukan User-Agent header
        self.headers = {
            "User-Agent": "IndoFactBot/1.0 (Educational project; Python/aiohttp)",
            "Accept": "application/json"
        }
        
        self.cleaning_patterns = [
            (r'\[.*?\]\(.*?\)', ''),      # Remove markdown links
            (r'http\S+', ''),              # Remove URLs
            (r'\[\d+\]', ''),              # Remove Wikipedia references [1], [2]
            (r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', ''),  # Emojis
            (r'[^\w\s.,!?;:\'"()\-–—]', ''),  # Special chars
            (r'\s+', ' '),                 # Normalize whitespace
        ]
        
        # RSS Feeds yang bagus untuk fakta (Indonesia)
        self.rss_feeds = {
            "sains": [
                "https://www.liputan6.com/feed/rss2?channel=tekno",
            ],
            "teknologi": [
                "https://www.liputan6.com/feed/rss2?channel=tekno",
            ],
            "umum": [
                "https://www.liputan6.com/feed/rss2",
            ]
        }
        
        # Wikipedia endpoints
        self.wikipedia_api = "https://id.wikipedia.org/api/rest_v1"
        self.wikipedia_random = f"{self.wikipedia_api}/page/random/summary"
        
        # Topik mapping untuk Wikipedia search
        self.topic_categories = {
            "space": ["astronomi", "tata surya", "planet", "bintang", "galaksi", "luar angkasa"],
            "history": ["sejarah", "perang dunia", "kerajaan", "arkeologi", "sejarah indonesia"],
            "science": ["fisika", "kimia", "biologi", "sains", "ilmu pengetahuan"],
            "sains": ["fisika", "kimia", "biologi", "sains", "ilmu pengetahuan"],
            "nature": ["hewan", "tumbuhan", "ekologi", "lingkungan", "alam"],
            "technology": ["teknologi", "komputer", "internet", "robotika", "kecerdasan buatan"],
            "teknologi": ["teknologi", "komputer", "internet", "robotika", "kecerdasan buatan"],
            "indonesia": ["indonesia", "budaya indonesia", "sejarah indonesia", "pulau jawa"],
            "animals": ["hewan", "mamalia", "reptil", "burung", "ikan"],
            "hewan": ["hewan", "mamalia", "reptil", "burung", "ikan"],
        }
        
        # Fakta menarik untuk fallback (jika semua sumber gagal)
        self.fallback_facts = [
            {
                "title": "Madu Tidak Pernah Basi",
                "body": "Madu adalah satu-satunya makanan yang tidak pernah membusuk. Para arkeolog menemukan pot madu berusia 3000 tahun di makam Mesir kuno, dan madu tersebut masih bisa dimakan! Hal ini karena madu memiliki kandungan gula yang sangat tinggi dan pH yang rendah, sehingga bakteri tidak bisa berkembang biak.",
                "category": "sains"
            },
            {
                "title": "Gurita Memiliki 3 Jantung",
                "body": "Gurita memiliki 3 jantung dan darah berwarna biru! Dua jantung memompa darah ke insang, sedangkan satu jantung memompa ke seluruh tubuh. Darahnya berwarna biru karena mengandung hemosianin yang berbasis tembaga, bukan hemoglobin berbasis besi seperti manusia.",
                "category": "hewan"
            },
            {
                "title": "Pisang Adalah Berry, Strawberry Bukan",
                "body": "Secara botani, pisang diklasifikasikan sebagai berry, sedangkan strawberry bukan! Berry sejati berasal dari satu bunga dengan satu ovarium dan memiliki beberapa biji di dalam dagingnya. Pisang memenuhi kriteria ini, sementara strawberry sebenarnya adalah 'aksesori buah'.",
                "category": "sains"
            },
            {
                "title": "Sidik Jari Koala Mirip Manusia",
                "body": "Koala memiliki sidik jari yang sangat mirip dengan manusia, bahkan bisa membingungkan penyelidik forensik! Ini adalah contoh evolusi konvergen, di mana dua spesies yang tidak berkerabat mengembangkan ciri yang sama untuk tujuan serupa - dalam hal ini, untuk memegang objek.",
                "category": "hewan"
            },
            {
                "title": "Hujan Berlian di Neptunus",
                "body": "Di planet Neptunus dan Uranus, hujan berlian benar-benar terjadi! Tekanan dan suhu yang ekstrem di atmosfer planet-planet ini mengubah metana menjadi kristal berlian yang kemudian jatuh seperti hujan ke inti planet.",
                "category": "space"
            },
        ]
        
        # ==========================================
        # YOUTUBE CONFIGURATION (TANPA API KEY) ⭐
        # ==========================================
        # Channel-channel YouTube Indonesia yang bagus untuk fakta
        # Transcript/subtitle diambil langsung (original, tanpa watermark)
        self.youtube_search_queries = {
            "sains": [
                "fakta sains unik indonesia",
                "fakta menarik ilmu pengetahuan",
                "tahukah kamu sains",
            ],
            "space": [
                "fakta luar angkasa indonesia",
                "fakta planet tata surya",
                "misteri alam semesta",
            ],
            "hewan": [
                "fakta unik hewan",
                "fakta mengejutkan binatang",
                "hewan langka indonesia",
            ],
            "history": [
                "sejarah indonesia menarik",
                "fakta sejarah dunia",
                "misteri sejarah kuno",
            ],
            "technology": [
                "fakta teknologi terbaru",
                "inovasi teknologi masa depan",
            ],
            "random": [
                "fakta unik yang jarang diketahui",
                "tahukah kamu fakta menarik",
                "fakta mengejutkan dunia",
            ]
        }
    
    def clean_text(self, text: str) -> str:
        """Membersihkan teks dari sampah"""
        if not text:
            return ""
        
        cleaned = text
        for pattern, replacement in self.cleaning_patterns:
            cleaned = re.sub(pattern, replacement, cleaned)
        
        return cleaned.strip()
    
    # ==========================================
    # WIKIPEDIA SCRAPING (TANPA API KEY) ⭐
    # ==========================================
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_wikipedia_random(self) -> Optional[RawContent]:
        """Ambil artikel random dari Wikipedia Indonesia"""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(self.wikipedia_random, timeout=15) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    title = data.get("title", "")
                    extract = data.get("extract", "")
                    page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
                    
                    # Skip artikel yang terlalu pendek atau tidak menarik
                    if len(extract) < 100:
                        return None
                    
                    # Skip jika hanya daftar atau disambiguation
                    skip_patterns = ["adalah sebuah", "merujuk kepada", "dapat merujuk", "daftar"]
                    if any(pattern in extract.lower()[:100] for pattern in skip_patterns):
                        return None
                    
                    return RawContent(
                        title=title,
                        body=self.clean_text(extract),
                        source="wikipedia",
                        url=page_url,
                        author="Wikipedia",
                        category="random"
                    )
                    
        except Exception as e:
            print(f"⚠️ Wikipedia random error: {e}")
            return None
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def _fetch_wikipedia_search(self, query: str) -> List[RawContent]:
        """Search artikel Wikipedia berdasarkan query"""
        results = []
        
        try:
            search_url = "https://id.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 5,
                "utf8": 1
            }
            
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(search_url, params=params, timeout=15) as response:
                    if response.status != 200:
                        return results
                    
                    data = await response.json()
                    search_results = data.get("query", {}).get("search", [])
                    
                    # Fetch summary untuk 3 hasil teratas
                    for item in search_results[:3]:
                        title = item.get("title", "")
                        summary = await self._fetch_wikipedia_page(title)
                        if summary:
                            results.append(summary)
                        await asyncio.sleep(0.3)  # Rate limiting
                            
        except Exception as e:
            print(f"⚠️ Wikipedia search error: {e}")
        
        return results
    
    async def search_wikipedia(self, query: str) -> Optional[RawContent]:
        """
        Search Wikipedia by query and return the best result.
        This is a public method for API endpoint.
        """
        try:
            results = await self._fetch_wikipedia_search(query)
            if results:
                return results[0]  # Return the first/best result
            return None
        except Exception as e:
            print(f"⚠️ search_wikipedia error: {e}")
            return None
    
    async def _fetch_wikipedia_page(self, title: str) -> Optional[RawContent]:
        """Fetch halaman Wikipedia spesifik"""
        try:
            url = f"{self.wikipedia_api}/page/summary/{quote(title)}"
            
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=15) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    extract = data.get("extract", "")
                    if len(extract) < 100:
                        return None
                    
                    return RawContent(
                        title=data.get("title", title),
                        body=self.clean_text(extract),
                        source="wikipedia",
                        url=data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                        author="Wikipedia",
                        category="search"
                    )
                    
        except Exception as e:
            print(f"⚠️ Wikipedia page error: {e}")
            return None
    
    # ==========================================
    # YOUTUBE TRANSCRIPT SCRAPING (TANPA API KEY) ⭐
    # ==========================================
    
    async def _search_youtube_videos(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Search YouTube videos menggunakan web scraping.
        Mengembalikan list video IDs dan titles.
        """
        results = []
        
        try:
            search_url = f"https://www.youtube.com/results?search_query={quote(query)}"
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
                }
                async with session.get(search_url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        return results
                    
                    html = await response.text()
                    
                    # Extract video IDs dari HTML
                    video_pattern = r'"videoId":"([a-zA-Z0-9_-]{11})"'
                    title_pattern = r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]'
                    
                    video_ids = re.findall(video_pattern, html)
                    titles = re.findall(title_pattern, html)
                    
                    # Deduplicate dan limit
                    seen_ids = set()
                    for vid, title in zip(video_ids, titles):
                        if vid not in seen_ids and len(results) < max_results:
                            seen_ids.add(vid)
                            results.append({
                                "video_id": vid,
                                "title": title,
                                "url": f"https://www.youtube.com/watch?v={vid}"
                            })
                    
        except Exception as e:
            print(f"⚠️ YouTube search error: {e}")
        
        return results
    
    async def _fetch_youtube_transcript(self, video_id: str) -> Optional[str]:
        """
        Fetch transcript/subtitle dari video YouTube.
        Menggunakan youtube-transcript-api (gratis, tanpa API key).
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
            
            # Coba ambil transcript Indonesia, fallback ke English
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                
                # Prioritas: Indonesia > English > Auto-generated
                transcript = None
                try:
                    transcript = transcript_list.find_transcript(['id'])
                except:
                    try:
                        transcript = transcript_list.find_transcript(['en'])
                    except:
                        # Ambil yang pertama tersedia
                        for t in transcript_list:
                            transcript = t
                            break
                
                if transcript:
                    transcript_data = transcript.fetch()
                    # Gabungkan semua teks
                    full_text = " ".join([entry['text'] for entry in transcript_data])
                    return full_text
                    
            except (TranscriptsDisabled, NoTranscriptFound):
                return None
                
        except ImportError:
            print("⚠️ youtube-transcript-api tidak terinstall")
            return None
        except Exception as e:
            print(f"⚠️ YouTube transcript error: {e}")
            return None
        
        return None
    
    async def mine_youtube(self, topic: str = "random") -> List[RawContent]:
        """
        Mining konten dari YouTube transcripts.
        Konten dijamin original (dari subtitle resmi video).
        """
        results = []
        
        # Pilih query berdasarkan topik
        queries = self.youtube_search_queries.get(
            topic.lower(), 
            self.youtube_search_queries.get("random", ["fakta unik menarik"])
        )
        
        query = random.choice(queries)
        print(f"🎬 Searching YouTube: {query}")
        
        # Search videos
        videos = await self._search_youtube_videos(query, max_results=5)
        
        for video in videos:
            video_id = video["video_id"]
            title = video["title"]
            
            print(f"  📺 Fetching transcript: {title[:40]}...")
            
            # Fetch transcript
            transcript = await self._fetch_youtube_transcript(video_id)
            
            if transcript and len(transcript) > 100:
                # Clean dan truncate
                clean_transcript = self.clean_text(transcript)
                
                # Ambil bagian yang cukup panjang tapi tidak terlalu panjang
                if len(clean_transcript) > 500:
                    clean_transcript = clean_transcript[:1500]
                
                results.append(RawContent(
                    title=title,
                    body=clean_transcript,
                    source="youtube",
                    url=video["url"],
                    author="YouTube Creator",
                    category=topic
                ))
                
                # Satu video saja cukup untuk random
                if topic.lower() == "random" and len(results) >= 1:
                    break
            
            await asyncio.sleep(0.5)  # Rate limiting
        
        return results
    
    # ==========================================
    # RSS FEED SCRAPING (TANPA API KEY)
    # ==========================================
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def _fetch_rss_feed(self, feed_url: str) -> List[RawContent]:
        """Parse RSS feed dan ambil artikel"""
        results = []
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with session.get(feed_url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        return results
                    
                    xml_content = await response.text()
                    
                    # Parse XML
                    root = ET.fromstring(xml_content)
                    
                    # Find items (RSS 2.0 format)
                    items = root.findall(".//item")
                    
                    for item in items[:5]:
                        title = item.find("title")
                        link = item.find("link")
                        description = item.find("description")
                        
                        if title is not None and link is not None:
                            title_text = title.text or ""
                            link_text = link.text or ""
                            desc_text = description.text if description is not None else ""
                            
                            # Clean HTML dari description
                            if desc_text:
                                soup = BeautifulSoup(desc_text, "html.parser")
                                desc_text = soup.get_text()
                            
                            # Fetch full article jika description pendek
                            body = desc_text
                            if len(desc_text) < 200 and link_text:
                                full_content = await self._scrape_url(link_text)
                                if full_content and len(full_content) > len(desc_text):
                                    body = full_content
                            
                            if len(body) > 50:
                                results.append(RawContent(
                                    title=self.clean_text(title_text),
                                    body=self.clean_text(body),
                                    source="rss",
                                    url=link_text,
                                    category="news"
                                ))
                    
        except Exception as e:
            print(f"⚠️ RSS feed error ({feed_url}): {e}")
        
        return results
    
    async def mine_rss(self, category: str = "sains") -> List[RawContent]:
        """Mining dari RSS feeds berdasarkan kategori"""
        feeds = self.rss_feeds.get(category, self.rss_feeds.get("umum", []))
        all_results = []
        
        for feed_url in feeds:
            try:
                results = await self._fetch_rss_feed(feed_url)
                all_results.extend(results)
            except Exception:
                continue
        
        return all_results
    
    # ==========================================
    # WEB SCRAPING LANGSUNG
    # ==========================================
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _scrape_url(self, url: str) -> Optional[str]:
        """Scrape konten dari URL menggunakan Trafilatura"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()
            
            # Extract dengan Trafilatura
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False
            )
            
            return extracted
            
        except Exception as e:
            print(f"⚠️ Scrape error ({url}): {e}")
            return None
    
    # ==========================================
    # REDDIT (OPSIONAL - JIKA ADA API KEY)
    # ==========================================
    
    async def mine_reddit(self, topic: Optional[str] = None) -> List[RawContent]:
        """Mining dari Reddit (memerlukan API key)"""
        # Check if Reddit credentials available
        if not config.env.REDDIT_CLIENT_ID or not config.env.REDDIT_CLIENT_SECRET:
            return []
        
        try:
            import praw
            
            reddit = praw.Reddit(
                client_id=config.env.REDDIT_CLIENT_ID,
                client_secret=config.env.REDDIT_CLIENT_SECRET,
                user_agent=config.env.REDDIT_USER_AGENT
            )
            
            results = []
            subreddits = config.subreddits
            
            for sub_name in subreddits:
                try:
                    subreddit = reddit.subreddit(sub_name)
                    posts = subreddit.top(time_filter="day", limit=5)
                    
                    for post in posts:
                        if topic and topic.lower() != "random":
                            if topic.lower() not in post.title.lower():
                                continue
                        
                        body = post.selftext if post.is_self else ""
                        
                        results.append(RawContent(
                            title=self.clean_text(post.title),
                            body=self.clean_text(body),
                            source="reddit",
                            url=f"https://reddit.com{post.permalink}",
                            author=str(post.author),
                            score=post.score,
                            category=sub_name
                        ))
                except Exception as e:
                    continue
            
            return results
            
        except ImportError:
            return []
        except Exception as e:
            print(f"⚠️ Reddit error: {e}")
            return []
    
    # ==========================================
    # FALLBACK FACTS (BUILT-IN)
    # ==========================================
    
    def get_fallback_fact(self, category: Optional[str] = None) -> RawContent:
        """Ambil fakta dari database built-in sebagai fallback"""
        if category:
            matching = [f for f in self.fallback_facts if f["category"] == category.lower()]
            fact = random.choice(matching) if matching else random.choice(self.fallback_facts)
        else:
            fact = random.choice(self.fallback_facts)
        
        return RawContent(
            title=fact["title"],
            body=fact["body"],
            source="builtin",
            url="",
            author="IndoFact Database",
            category=fact["category"]
        )
    
    # ==========================================
    # MAIN MINING FUNCTIONS
    # ==========================================
    
    async def get_random_fact(self) -> Optional[RawContent]:
        """
        Ambil satu fakta random dari berbagai sumber.
        Prioritas: Wikipedia > YouTube > RSS > Reddit > Fallback
        
        Semua konten DIJAMIN original:
        - Wikipedia: Teks artikel resmi
        - YouTube: Transcript/subtitle resmi (bukan watermark)
        - RSS: Artikel berita resmi
        """
        print("📖 Mencoba Wikipedia Indonesia...")
        
        # Try Wikipedia (paling reliable, 5 attempts)
        for i in range(5):
            content = await self._fetch_wikipedia_random()
            if content and len(content.body) > 150:
                print(f"✅ Found from Wikipedia: {content.title[:50]}...")
                return content
            await asyncio.sleep(0.5)
        
        print("🎬 Wikipedia tidak tersedia, mencoba YouTube transcripts...")
        
        # Try YouTube transcripts (original content dari subtitle)
        try:
            yt_results = await self.mine_youtube("random")
            if yt_results:
                content = yt_results[0]
                print(f"✅ Found from YouTube: {content.title[:50]}...")
                return content
        except Exception as e:
            print(f"⚠️ YouTube error: {e}")
        
        print("📰 YouTube tidak tersedia, mencoba RSS feeds...")
        
        # Try RSS feeds
        for category in ["sains", "teknologi", "umum"]:
            try:
                results = await self.mine_rss(category)
                if results:
                    # Pilih yang paling panjang/detail
                    results.sort(key=lambda x: len(x.body), reverse=True)
                    content = results[0]
                    print(f"✅ Found from RSS ({category}): {content.title[:50]}...")
                    return content
            except Exception:
                continue
        
        print("🔴 RSS tidak tersedia, mencoba Reddit...")
        
        # Try Reddit if available
        results = await self.mine_reddit("random")
        if results:
            content = random.choice(results)
            print(f"✅ Found from Reddit: {content.title[:50]}...")
            return content
        
        print("💾 Menggunakan fakta built-in...")
        
        # Fallback to built-in facts
        content = self.get_fallback_fact()
        print(f"✅ Using fallback: {content.title}")
        return content
    
    async def search_by_topic(self, topic: str) -> List[RawContent]:
        """
        Cari konten berdasarkan topik spesifik.
        Semua konten DIJAMIN original dan tanpa watermark.
        """
        all_results = []
        
        # 1. Search Wikipedia (prioritas utama)
        print(f"🔍 Searching Wikipedia untuk: {topic}")
        wiki_results = await self._fetch_wikipedia_search(topic)
        all_results.extend(wiki_results)
        
        # Juga coba search related terms
        related_terms = self.topic_categories.get(topic.lower(), [])
        for term in related_terms[:2]:
            print(f"🔍 Searching related: {term}")
            more_results = await self._fetch_wikipedia_search(term)
            all_results.extend(more_results)
            await asyncio.sleep(0.3)
        
        # 2. YouTube transcripts (original content)
        print(f"🎬 Searching YouTube untuk: {topic}")
        try:
            yt_results = await self.mine_youtube(topic)
            all_results.extend(yt_results)
        except Exception as e:
            print(f"⚠️ YouTube search error: {e}")
        
        # 3. RSS feeds berdasarkan kategori
        rss_category = "umum"
        if topic.lower() in ["science", "sains", "space", "alam"]:
            rss_category = "sains"
        elif topic.lower() in ["technology", "tech", "teknologi"]:
            rss_category = "teknologi"
        
        rss_results = await self.mine_rss(rss_category)
        # Filter RSS yang relevan dengan topik
        for r in rss_results:
            if topic.lower() in r.title.lower() or topic.lower() in r.body.lower()[:200]:
                all_results.append(r)
        
        # 4. Reddit jika tersedia
        reddit_results = await self.mine_reddit(topic)
        all_results.extend(reddit_results)
        
        # 5. Fallback jika tidak ada hasil
        if not all_results:
            print(f"⚠️ Tidak ditemukan hasil untuk '{topic}', menggunakan fallback...")
            fallback = self.get_fallback_fact(topic)
            all_results.append(fallback)
        
        # Sort by content length (longer = more detailed)
        all_results.sort(key=lambda x: len(x.body), reverse=True)
        
        return all_results
    
    def format_for_llm(self, content: RawContent) -> str:
        """Format konten untuk input ke LLM"""
        # PENTING: Jangan gunakan label "Judul:", "Konten:", dll
        # karena LLM akan memasukkannya ke narasi video!
        # Cukup berikan konten langsung tanpa label
        
        if content.body:
            body = content.body[:2000] if len(content.body) > 2000 else content.body
            return body
        
        return content.title


# Singleton instance
miner = ContentMiner()


async def run(topic: str = "random") -> Optional[RawContent]:
    """
    Entry point untuk modul scraper.
    
    Args:
        topic: Topik yang dicari atau "random"
        
    Returns:
        RawContent terbaik yang ditemukan
    """
    print(f"🔍 Mining konten untuk topik: {topic}")
    print("=" * 50)
    
    if topic.lower() == "random":
        content = await miner.get_random_fact()
    else:
        results = await miner.search_by_topic(topic)
        content = results[0] if results else None
    
    if content:
        print("=" * 50)
        print(f"✅ Ditemukan: {content.title[:50]}...")
        print(f"   📌 Sumber: {content.source}")
        print(f"   📏 Panjang: {len(content.body)} karakter")
        return content
    else:
        print("=" * 50)
        print("❌ Tidak ditemukan konten yang sesuai")
        return None


# Test module
if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("🧪 Testing Content Miner (No API Key Required)")
        print("=" * 60)
        
        # Test random fact
        print("\n📌 Test 1: Random Fact")
        result = await run("random")
        if result:
            print(f"\n📄 Title: {result.title}")
            print(f"📝 Body: {result.body[:300]}...")
            print(f"🔗 URL: {result.url}")
        
        # Test topic search
        print("\n" + "=" * 60)
        print("\n📌 Test 2: Topic Search (sains)")
        result = await run("sains")
        if result:
            print(f"\n📄 Title: {result.title}")
            print(f"📝 Body: {result.body[:300]}...")
    
    asyncio.run(test())
