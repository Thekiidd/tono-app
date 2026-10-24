import os
import shutil
import string
from fastapi import FastAPI, HTTPException, Query, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx

from database import (
    init_db, add_favorite, remove_favorite, get_favorites, is_favorite,
    create_playlist, get_playlists, get_playlist_tracks, add_track_to_playlist,
    delete_playlist, add_history, get_recent_history, get_setting, set_setting
)
from engine import (
    search_music, get_trending_feed, resolve_stream, download_audio_track,
    fetch_synced_lyrics, get_artist_profile, get_track_credits,
    get_smart_recommendations, ytm, clean_thumbnail,
    get_storage_dir, is_track_cached, STREAM_CACHE,
    CACHE_DIR, COVERS_DIR, BASE_DIR
)

FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

# Initialize database
init_db()

app = FastAPI(title="Tono Audio Core API", version="1.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve cached audio files dynamically from configured storage directory or default cache
@app.get("/api/local-audio/{filename}")
def serve_local_audio(filename: str):
    """Serve cached audio files from active storage dir or fallback CACHE_DIR."""
    active_dir = get_storage_dir()
    for d in {active_dir, CACHE_DIR}:
        fpath = os.path.join(d, filename)
        if os.path.exists(fpath):
            media_type = "audio/ogg" if filename.endswith(".opus") else "audio/mpeg"
            return FileResponse(fpath, media_type=media_type)
    raise HTTPException(status_code=404, detail="Audio file not found")

# Models
class TrackModel(BaseModel):
    video_id: str
    title: str
    artist: str
    album: Optional[str] = ""
    duration: Optional[str] = "0:00"
    duration_seconds: Optional[int] = 0
    thumbnail: Optional[str] = ""
    source: Optional[str] = "youtube"

class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = ""

class StorageConfig(BaseModel):
    drive: Optional[str] = None
    path: Optional[str] = None
    folder_name: Optional[str] = "Tono_Music"

class PrefetchRequest(BaseModel):
    video_id: str
    title: Optional[str] = ""
    artist: Optional[str] = ""
    source: Optional[str] = "youtube"

def prefetch_feed_streams(tracks: List[Dict[str, Any]], limit: int = 8):
    """Background worker to pre-resolve direct stream URLs for top tracks."""
    for t in tracks[:limit]:
        vid = t.get("video_id")
        if vid and vid not in STREAM_CACHE:
            try:
                resolve_stream(vid, source=t.get("source", "youtube"), title=t.get("title", ""), artist=t.get("artist", ""))
            except Exception:
                pass

# --- Endpoints ---

@app.get("/api/health")
def health():
    return {"status": "online", "service": "Tono Audio Core", "version": "1.0.6"}

@app.get("/api/search")
def search(q: str = Query(..., min_length=1), source: str = "all", background_tasks: BackgroundTasks = BackgroundTasks()):
    """Search YouTube Music, SoundCloud and local tracks with matched artist discovery."""
    results = search_music(q, source=source)
    for item in results:
        item["is_favorite"] = is_favorite(item["video_id"])
    if len(results) > 0:
        background_tasks.add_task(prefetch_feed_streams, results, 4)

    matched_artist = None
    try:
        if ytm and source in ("all", "youtube", "ytmusic"):
            art_res = ytm.search(q.strip(), filter="artists")
            if art_res:
                top_art = art_res[0]
                matched_artist = {
                    "name": top_art.get("artist"),
                    "browse_id": top_art.get("browseId"),
                    "subscribers": top_art.get("subscribers", ""),
                    "radio_id": top_art.get("radioId", ""),
                    "thumbnail": clean_thumbnail(top_art.get("thumbnails", []))
                }
    except Exception as e:
        print("Search artist match note:", e)

    return {
        "query": q,
        "matched_artist": matched_artist,
        "count": len(results),
        "results": results
    }

@app.get("/api/recommendations/radio")
def get_radio(video_id: Optional[str] = None, artist: Optional[str] = None, limit: int = 20, background_tasks: BackgroundTasks = BackgroundTasks()):
    """Get smart radio stream of similar tracks based on a track or artist."""
    recs = get_smart_recommendations(video_id=video_id, artist=artist, limit=limit)
    for item in recs:
        item["is_favorite"] = is_favorite(item["video_id"])
    if len(recs) > 0:
        background_tasks.add_task(prefetch_feed_streams, recs, 4)
    return {"seed_video_id": video_id, "seed_artist": artist, "count": len(recs), "tracks": recs}

@app.get("/api/recommendations/for-you")
def get_for_you_feed(background_tasks: BackgroundTasks = BackgroundTasks()):
    """Contextual 'Because you listened to [Artist]' discovery feed."""
    history = get_recent_history(limit=10)
    seed_track = None
    seed_artist = None
    
    if history:
        for h in history:
            if h.get("artist") and h["artist"] != "Unknown":
                seed_track = h
                seed_artist = h["artist"]
                break
                
    if not seed_artist:
        seed_artist = "Imagine Dragons"
        seed_track = {"video_id": "Kx7B-XvmFtE", "title": "Believer", "artist": "Imagine Dragons"}

    recs = get_smart_recommendations(video_id=seed_track.get("video_id"), artist=seed_artist, limit=14)
    for item in recs:
        item["is_favorite"] = is_favorite(item["video_id"])
        
    art_profile = get_artist_profile(seed_artist)
    similar_artists = art_profile.get("related_artists", [])[:8]
    
    if len(recs) > 0:
        background_tasks.add_task(prefetch_feed_streams, recs, 4)

    return {
        "heading": f"Porque escuchaste a {seed_artist}",
        "seed_artist": seed_artist,
        "seed_track": seed_track,
        "tracks": recs,
        "similar_artists": similar_artists
    }

@app.get("/api/trending")
def trending(background_tasks: BackgroundTasks):
    """Get home trending tracks and auto-prefetch top tracks in background."""
    feed = get_trending_feed()
    for item in feed:
        item["is_favorite"] = is_favorite(item["video_id"])
    background_tasks.add_task(prefetch_feed_streams, feed, 8)
    return {"results": feed}

@app.post("/api/stream/prefetch")
def prefetch_single_track(req: PrefetchRequest, background_tasks: BackgroundTasks):
    """Silently pre-resolve a track in the background for zero-latency future playback."""
    if req.video_id not in STREAM_CACHE:
        def task():
            try:
                resolve_stream(req.video_id, source=req.source or "youtube", title=req.title or "", artist=req.artist or "")
            except Exception:
                pass
        background_tasks.add_task(task)
    return {"status": "prefetching", "video_id": req.video_id}

@app.get("/api/stream/{video_id}")
def stream_info(video_id: str, source: str = "youtube", title: Optional[str] = "", artist: Optional[str] = ""):
    """Resolve direct audio streaming URL with automatic multi-source fallback."""
    try:
        info = resolve_stream(video_id, source=source, title=title or "", artist=artist or "")
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audio-proxy/{video_id}")
async def audio_proxy(video_id: str, request: Request, source: str = "youtube", title: Optional[str] = "", artist: Optional[str] = ""):
    """Proxy audio stream with HTTP Range support for seamless seeking and no CORS issues."""
    try:
        # Check if local file exists first in active storage dir or cache
        active_dir = get_storage_dir()
        for d in {active_dir, CACHE_DIR}:
            local_opus = os.path.join(d, f"{video_id}.opus")
            local_mp3 = os.path.join(d, f"{video_id}.mp3")
            if os.path.exists(local_opus):
                return FileResponse(local_opus, media_type="audio/ogg")
            if os.path.exists(local_mp3):
                return FileResponse(local_mp3, media_type="audio/mpeg")

        # Resolve stream URL
        stream_data = resolve_stream(video_id, source=source, title=title or "", artist=artist or "")
        stream_url = stream_data["url"]

        # Forward range headers
        headers = {}
        range_header = request.headers.get("Range")
        if range_header:
            headers["Range"] = range_header

        client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        req = client.build_request("GET", stream_url, headers=headers)
        r = await client.send(req, stream=True)

        async def stream_generator():
            try:
                async for chunk in r.aiter_bytes(chunk_size=1024 * 64):
                    yield chunk
            finally:
                await r.aclose()
                await client.aclose()

        response_headers = {
            "Content-Type": r.headers.get("Content-Type", "audio/webm"),
            "Accept-Ranges": "bytes",
        }
        if "Content-Range" in r.headers:
            response_headers["Content-Range"] = r.headers["Content-Range"]
        if "Content-Length" in r.headers:
            response_headers["Content-Length"] = r.headers["Content-Length"]

        return StreamingResponse(
            stream_generator(),
            status_code=r.status_code,
            headers=response_headers,
        )
    except Exception as e:
        print("Audio proxy error:", e)
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")

@app.get("/api/lyrics")
def lyrics(title: str, artist: str):
    """Retrieve time-synced or text lyrics."""
    return fetch_synced_lyrics(title, artist)

@app.get("/api/artist")
def artist_profile(name: str):
    """Retrieve artist bio, stats, top tracks, and albums."""
    data = get_artist_profile(name)
    if not data:
        raise HTTPException(status_code=404, detail="Artist not found")
    return data

@app.get("/api/credits/{video_id}")
def song_credits(video_id: str):
    """Retrieve song composers, writers, producers, and record label."""
    return get_track_credits(video_id)

# --- Favorites ---
@app.get("/api/favorites")
def list_favorites():
    return {"favorites": get_favorites()}

@app.post("/api/favorites")
def add_fav(track: TrackModel):
    success = add_favorite(track.dict())
    return {"success": success}

@app.delete("/api/favorites/{video_id}")
def remove_fav(video_id: str):
    success = remove_favorite(video_id)
    return {"success": success}

# --- Playlists ---
@app.get("/api/playlists")
def list_playlists():
    return {"playlists": get_playlists()}

@app.post("/api/playlists")
def make_playlist(p: PlaylistCreate):
    pid = create_playlist(p.name, p.description or "")
    return {"id": pid, "name": p.name}

@app.get("/api/playlists/{playlist_id}")
def view_playlist(playlist_id: int):
    tracks = get_playlist_tracks(playlist_id)
    for t in tracks:
        t["is_favorite"] = is_favorite(t["video_id"])
    return {"playlist_id": playlist_id, "tracks": tracks}

@app.post("/api/playlists/{playlist_id}/tracks")
def add_to_playlist(playlist_id: int, track: TrackModel):
    success = add_track_to_playlist(playlist_id, track.dict())
    return {"success": success}

@app.delete("/api/playlists/{playlist_id}")
def delete_pl(playlist_id: int):
    success = delete_playlist(playlist_id)
    return {"success": success}

# --- History ---
@app.post("/api/history")
def record_history(track: TrackModel):
    add_history(track.dict())
    return {"status": "ok"}

@app.get("/api/history")
def view_history():
    return {"history": get_recent_history()}

# --- Caching & Downloads ---
@app.post("/api/download/{video_id}")
def download_song(video_id: str, track: TrackModel, background_tasks: BackgroundTasks):
    """Save track offline in Drive D storage."""
    def task():
        try:
            download_audio_track(video_id, track.title, track.artist)
            # update favorite record with is_downloaded
            add_favorite({**track.dict(), "is_downloaded": True, "local_path": f"{video_id}.opus"})
            print(f"Track {track.title} successfully cached locally!")
        except Exception as e:
            print("Download task error:", e)

    background_tasks.add_task(task)
    return {"status": "download_started", "video_id": video_id}

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Tono Audio Core API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "search": "/api/search?q=...",
            "trending": "/api/trending",
            "docs": "/docs"
        }
    }

def get_system_drives() -> Dict[str, Any]:
    """Scan and return available storage drives and current storage target."""
    active_dir = get_storage_dir()
    drives = []
    
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive_root = f"{letter}:\\"
            if os.path.exists(drive_root):
                try:
                    usage = shutil.disk_usage(drive_root)
                    total_gb = round(usage.total / (1024**3), 1)
                    free_gb = round(usage.free / (1024**3), 1)
                    used_gb = round(usage.used / (1024**3), 1)
                    pct = round((usage.used / usage.total) * 100, 1)
                    
                    label = f"Disco Local ({letter}:)"
                    if letter == "C":
                        label = "Disco Principal Sistema (C:)"
                    elif letter == "D":
                        label = "Disco Secundario / Datos (D:)"
                        
                    is_active = active_dir.upper().startswith(f"{letter}:")
                    drives.append({
                        "letter": letter,
                        "path": drive_root,
                        "name": label,
                        "total_gb": total_gb,
                        "free_gb": free_gb,
                        "used_gb": used_gb,
                        "percent_used": pct,
                        "is_active": is_active,
                        "is_recommended": letter == "D" or (letter != "C" and free_gb > 20)
                    })
                except Exception:
                    pass
    else:
        root_path = "/"
        try:
            usage = shutil.disk_usage(root_path)
            total_gb = round(usage.total / (1024**3), 1)
            free_gb = round(usage.free / (1024**3), 1)
            used_gb = round(usage.used / (1024**3), 1)
            pct = round((usage.used / usage.total) * 100, 1)
            drives.append({
                "letter": "/",
                "path": root_path,
                "name": "Almacenamiento del Servidor (/)",
                "total_gb": total_gb,
                "free_gb": free_gb,
                "used_gb": used_gb,
                "percent_used": pct,
                "is_active": True,
                "is_recommended": True
            })
        except Exception:
            pass

    if not any(d["is_active"] for d in drives) and drives:
        drives[0]["is_active"] = True

    return {
        "active_storage_dir": active_dir,
        "drives": drives
    }

@app.get("/api/drives")
def list_drives():
    """List detected system storage drives and current active path."""
    return get_system_drives()

@app.post("/api/settings/storage")
def configure_storage(config: StorageConfig):
    """Set custom disk/directory for music downloads and offline storage."""
    if config.path:
        target_dir = os.path.abspath(config.path)
    elif config.drive:
        folder = config.folder_name or "Tono_Music"
        target_dir = os.path.join(config.drive, folder)
    else:
        raise HTTPException(status_code=400, detail="Drive or path must be provided")

    try:
        os.makedirs(target_dir, exist_ok=True)
        # Verify write permission
        test_file = os.path.join(target_dir, ".tono_write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        if os.path.exists(test_file):
            os.remove(test_file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo acceder o crear la carpeta en ese disco: {str(e)}")

    set_setting("storage_dir", target_dir)
    return {
        "success": True,
        "message": f"Almacenamiento configurado en {target_dir}",
        "storage_dir": target_dir
    }

@app.get("/api/stats")
def storage_stats():
    """Disk stats and cache stats for the active storage directory."""
    active_dir = get_storage_dir()
    try:
        total, used, free = shutil.disk_usage(active_dir)
    except Exception:
        total, used, free = shutil.disk_usage(".")

    all_cached_files = set()
    total_bytes = 0
    for d in {active_dir, CACHE_DIR}:
        if os.path.exists(d):
            try:
                for f in os.listdir(d):
                    if f.endswith((".opus", ".mp3", ".m4a")):
                        all_cached_files.add(f)
                        total_bytes += os.path.getsize(os.path.join(d, f))
            except Exception:
                pass

    drive_label = active_dir
    if os.name == "nt" and len(active_dir) >= 2 and active_dir[1] == ":":
        drive_label = f"Disco {active_dir[:2].upper()}"

    return {
        "storage": drive_label,
        "active_dir": active_dir,
        "total_gb": round(total / (1024**3), 1),
        "free_gb": round(free / (1024**3), 1),
        "cached_tracks_count": len(all_cached_files),
        "cache_size_mb": round(total_bytes / (1024**2), 1),
        "cache_dir": active_dir
    }

# Mount Frontend SPA if available locally
if os.path.exists(FRONTEND_DIST):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend_app")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
