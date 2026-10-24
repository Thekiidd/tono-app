import os
import time
import httpx
import yt_dlp
from ytmusicapi import YTMusic
from typing import List, Dict, Any, Optional
import asyncio
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "music_storage", "cache")
COVERS_DIR = os.path.join(BASE_DIR, "music_storage", "covers")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(COVERS_DIR, exist_ok=True)

# Stream cache: { video_id: (url, expiry_timestamp, codec) }
STREAM_CACHE: Dict[str, Any] = {}
CACHE_TTL = 3600 * 4  # 4 hours

def get_storage_dir() -> str:
    """Retrieve user configured storage directory or default CACHE_DIR."""
    try:
        from database import get_setting
        custom_dir = get_setting("storage_dir", "")
        if custom_dir and os.path.exists(custom_dir):
            return custom_dir
    except Exception:
        pass
    return CACHE_DIR

def is_track_cached(video_id: str) -> bool:
    """Check if track audio exists in active storage directory or cache."""
    dirs = {get_storage_dir(), CACHE_DIR}
    for d in dirs:
        if os.path.exists(os.path.join(d, f"{video_id}.opus")) or os.path.exists(os.path.join(d, f"{video_id}.mp3")):
            return True
    return False

# Initialize YTMusic instance
try:
    ytm = YTMusic()
except Exception as e:
    print("YTMusic initialization warning:", e)
    ytm = None

def clean_thumbnail(thumbnails: List[Dict[str, Any]]) -> str:
    """Return the highest quality thumbnail URL available."""
    if not thumbnails:
        return "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=500&q=80"
    # Sort by width or pick the last one
    sorted_thumbs = sorted(thumbnails, key=lambda x: x.get("width", 0))
    url = sorted_thumbs[-1].get("url", "")
    # Upgrade standard resolution if possible
    if "=w" in url and "=h" in url:
        url = re.sub(r"=w\d+-h\d+", "=w800-h800", url)
    return url

def search_music(query: str, source: str = "all") -> List[Dict[str, Any]]:
    """Search for music across YouTube Music and SoundCloud."""
    results = []
    
    if source in ("all", "youtube", "ytmusic") and ytm:
        try:
            yt_results = ytm.search(query, filter="songs")
            for item in yt_results:
                vid = item.get("videoId")
                if not vid:
                    continue
                
                artists = [a.get("name", "") for a in item.get("artists", [])]
                artist_name = ", ".join(artists) if artists else "Unknown Artist"
                
                album_info = item.get("album")
                album_name = album_info.get("name", "") if album_info else ""
                
                results.append({
                    "video_id": vid,
                    "title": item.get("title", "Unknown Title"),
                    "artist": artist_name,
                    "album": album_name,
                    "duration": item.get("duration", "0:00"),
                    "duration_seconds": item.get("duration_seconds", 0),
                    "thumbnail": clean_thumbnail(item.get("thumbnails", [])),
                    "source": "youtube",
                    "is_cached": is_track_cached(vid)
                })
        except Exception as e:
            print("Error in ytm search:", e)
            
    # If query mentions remix/dj/sc or user asked for soundcloud
    if source in ("all", "soundcloud") and (source == "soundcloud" or len(results) < 5 or "remix" in query.lower()):
        try:
            ydl_opts = {"quiet": True, "extract_flat": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                sc_info = ydl.extract_info(f"scsearch8:{query}", download=False)
                for entry in sc_info.get("entries", []):
                    sc_id = entry.get("id")
                    if not sc_id:
                        continue
                    
                    duration_sec = entry.get("duration") or 0
                    m, s = divmod(int(duration_sec), 60)
                    
                    results.append({
                        "video_id": f"sc_{sc_id}",
                        "title": entry.get("title", "SoundCloud Track"),
                        "artist": entry.get("uploader", "SoundCloud Artist"),
                        "album": "SoundCloud",
                        "duration": f"{m}:{s:02d}",
                        "duration_seconds": int(duration_sec),
                        "thumbnail": entry.get("thumbnail") or "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=500&q=80",
                        "source": "soundcloud",
                        "url": entry.get("url"),
                        "is_cached": False
                    })
        except Exception as e:
            print("SoundCloud search note:", e)

    return results

def get_trending_feed() -> List[Dict[str, Any]]:
    """Return top trending tracks and curated recommendations."""
    if not ytm:
        return []
    
    trending = []
    # Try getting charts or top songs
    try:
        charts = ytm.get_charts(country="US")
        tracks = charts.get("videos", {}).get("items", []) or charts.get("tracks", {}).get("items", [])
        for item in tracks[:20]:
            vid = item.get("videoId")
            if not vid:
                continue
            artists = [a.get("name", "") for a in item.get("artists", [])]
            trending.append({
                "video_id": vid,
                "title": item.get("title", ""),
                "artist": ", ".join(artists) if artists else "Popular Artist",
                "album": "Top Charts",
                "duration": item.get("duration", "3:30"),
                "thumbnail": clean_thumbnail(item.get("thumbnails", [])),
                "source": "youtube",
                "is_cached": is_track_cached(vid)
            })
    except Exception as e:
        print("Charts fallback to popular search:", e)
        # Fallback to search popular songs
        return search_music("Global Top Hits 2026", source="youtube")[:15]
        
    return trending

def resolve_stream(video_id: str, source: str = "youtube", title: str = "", artist: str = "") -> Dict[str, Any]:
    """Resolve direct audio stream URL with caching, mobile android extraction, and resilient SoundCloud fallback."""
    # 1. Check if downloaded locally in active storage directory or default cache
    active_dir = get_storage_dir()
    for d in {active_dir, CACHE_DIR}:
        local_opus = os.path.join(d, f"{video_id}.opus")
        local_mp3 = os.path.join(d, f"{video_id}.mp3")
        if os.path.exists(local_opus):
            return {"url": f"/api/local-audio/{video_id}.opus", "is_local": True, "codec": "opus"}
        if os.path.exists(local_mp3):
            return {"url": f"/api/local-audio/{video_id}.mp3", "is_local": True, "codec": "mp3"}

    # 2. Check memory cache
    now = time.time()
    if video_id in STREAM_CACHE:
        cached_url, expiry, codec = STREAM_CACHE[video_id]
        if now < expiry:
            return {"url": cached_url, "is_local": False, "codec": codec}

    # 3. Extract via yt-dlp with mobile android client to avoid datacenter bot blocks
    target_url = f"https://www.youtube.com/watch?v={video_id}"
    if source == "soundcloud" or video_id.startswith("sc_"):
        target_url = f"https://api.soundcloud.com/tracks/{video_id.replace('sc_', '')}"

    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "js_runtimes": {"node": {}},
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            stream_url = info.get("url")
            codec = info.get("acodec", "opus")
            
            if stream_url:
                STREAM_CACHE[video_id] = (stream_url, now + CACHE_TTL, codec)
                return {"url": stream_url, "is_local": False, "codec": codec}
    except Exception as yt_err:
        print(f"Primary YouTube stream extraction note for {video_id}: {yt_err}")
        # Multi-CDN Resilient Fallback: Search SoundCloud by Track & Artist (skipping DRM tracks)
        query = f"{artist} {title}".strip()
        if not query and ytm:
            try:
                meta = ytm.get_song(video_id)
                v_det = meta.get("videoDetails", {})
                query = f"{v_det.get('author', '')} {v_det.get('title', '')}".strip()
            except Exception:
                pass

        if query:
            try:
                sc_opts = {
                    "format": "bestaudio/best",
                    "quiet": True,
                    "noplaylist": True,
                    "ignoreerrors": True,
                }
                with yt_dlp.YoutubeDL(sc_opts) as sc_ydl:
                    sc_res = sc_ydl.extract_info(f"scsearch5:{query}", download=False)
                    for entry in sc_res.get("entries", []) or []:
                        if entry and entry.get("url"):
                            sc_url = entry["url"]
                            codec = entry.get("acodec", "mp3")
                            STREAM_CACHE[video_id] = (sc_url, now + CACHE_TTL, codec)
                            return {"url": sc_url, "is_local": False, "codec": codec}
            except Exception as sc_err:
                print(f"SoundCloud fallback stream note: {sc_err}")

        raise RuntimeError(f"Could not resolve audio stream URL: {yt_err}")

    raise RuntimeError("Could not resolve audio stream URL")

def download_audio_track(video_id: str, title: str = "", artist: str = "") -> str:
    """Download audio file locally in high quality Opus/MP3 into active storage directory."""
    target_dir = get_storage_dir()
    os.makedirs(target_dir, exist_ok=True)
    output_template = os.path.join(target_dir, f"{video_id}.%(ext)s")
    
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": "192",
        }],
    }
    
    target_url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([target_url])
        
    final_file = os.path.join(target_dir, f"{video_id}.opus")
    return final_file

def get_artist_profile(artist_name: str) -> Dict[str, Any]:
    """Retrieve full artist profile including bio, top songs, albums and stats."""
    if not ytm:
        return {}
    try:
        search_res = ytm.search(artist_name, filter="artists")
        if not search_res:
            return {}
        
        browse_id = search_res[0].get("browseId")
        if not browse_id:
            return {}
        
        data = ytm.get_artist(browse_id)
        
        # Clean top songs
        top_songs = []
        for s in data.get("songs", {}).get("results", []):
            vid = s.get("videoId")
            if not vid:
                continue
            artists = [a.get("name", "") for a in s.get("artists", [])]
            top_songs.append({
                "video_id": vid,
                "title": s.get("title", ""),
                "artist": ", ".join(artists) if artists else data.get("name", ""),
                "album": s.get("album", {}).get("name", "") if s.get("album") else "",
                "duration": s.get("duration", "3:30"),
                "thumbnail": clean_thumbnail(s.get("thumbnails", [])),
                "source": "youtube"
            })
            
        # Clean albums & singles
        albums = []
        for alb in data.get("albums", {}).get("results", []) + data.get("singles", {}).get("results", []):
            albums.append({
                "browse_id": alb.get("browseId"),
                "title": alb.get("title", ""),
                "year": alb.get("year", ""),
                "type": alb.get("type", "Álbum"),
                "thumbnail": clean_thumbnail(alb.get("thumbnails", []))
            })

        return {
            "name": data.get("name", artist_name),
            "description": data.get("description", ""),
            "subscribers": data.get("subscribers", ""),
            "banner": clean_thumbnail(data.get("thumbnails", [])),
            "top_songs": top_songs,
            "albums": albums
        }
    except Exception as e:
        print("Error fetching artist profile:", e)
        return {}

def get_track_credits(video_id: str) -> Dict[str, Any]:
    """Extract official credits: composers, writers, producers, engineers, and record label."""
    target_url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        "js_runtimes": {"node": {}},
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    
    credits_data = {
        "performers": [],
        "writers": [],
        "producers": [],
        "engineers": [],
        "label": "",
        "release_date": "",
        "raw": []
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            desc = info.get("description", "")
            
            for line in desc.splitlines():
                line = line.strip()
                if not line:
                    continue
                
                if "Provided to YouTube by" in line:
                    credits_data["label"] = line.replace("Provided to YouTube by", "").strip()
                elif "Released on:" in line:
                    credits_data["release_date"] = line.replace("Released on:", "").strip()
                elif ":" in line:
                    role, person = [p.strip() for p in line.split(":", 1)]
                    role_lower = role.lower()
                    
                    if any(w in role_lower for w in ["composer", "lyricist", "writer", "autor"]):
                        credits_data["writers"].append({"role": role, "name": person})
                    elif any(w in role_lower for w in ["producer", "productor"]):
                        credits_data["producers"].append({"role": role, "name": person})
                    elif any(w in role_lower for w in ["engineer", "mixing", "mastering", "ingeniero"]):
                        credits_data["engineers"].append({"role": role, "name": person})
                    elif any(w in role_lower for w in ["vocal", "guitar", "bass", "drum", "keyboard", "piano", "percussion", "strings"]):
                        credits_data["performers"].append({"role": role, "name": person})
                    else:
                        credits_data["raw"].append({"role": role, "name": person})
    except Exception as e:
        print("Error extracting credits:", e)

    return credits_data

def fetch_synced_lyrics(title: str, artist: str) -> Dict[str, Any]:
    """Fetch time-synced or plain lyrics from lrclib.net."""
    # Clean title (remove (Official Video), [Remastered], etc.)
    clean_t = re.sub(r"\(.*?\)|\[.*?\]", "", title).strip()
    clean_a = re.sub(r"\(.*?\)|\[.*?\]", "", artist).strip().split(",")[0]
    
    try:
        headers = {"User-Agent": "SpotyStream/1.0 (https://github.com/spotystream)"}
        with httpx.Client(timeout=4.0, headers=headers) as client:
            resp = client.get("https://lrclib.net/api/get", params={"artist_name": clean_a, "track_name": clean_t})
            if resp.status_code == 200:
                data = resp.json()
                synced = data.get("syncedLyrics")
                plain = data.get("plainLyrics")
                
                parsed_lines = []
                if synced:
                    for line in synced.splitlines():
                        match = re.match(r"\[(\d+):(\d+\.?\d*)\](.*)", line)
                        if match:
                            mins, secs, text = match.groups()
                            total_sec = int(mins) * 60 + float(secs)
                            parsed_lines.append({"time": total_sec, "text": text.strip()})
                            
                return {
                    "has_lyrics": True,
                    "is_synced": bool(synced),
                    "synced": parsed_lines,
                    "plain": plain or ""
                }
    except Exception as e:
        print("Lyrics fetch error:", e)

    return {"has_lyrics": False, "is_synced": False, "synced": [], "plain": "No lyrics found for this track."}
