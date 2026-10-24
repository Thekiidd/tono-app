import os
import shutil
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
    delete_playlist, add_history, get_recent_history
)
from engine import (
    search_music, get_trending_feed, resolve_stream, download_audio_track,
    fetch_synced_lyrics, get_artist_profile, get_track_credits,
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

# Mount local cache for audio files
app.mount("/api/local-audio", StaticFiles(directory=CACHE_DIR), name="local_audio")

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

# --- Endpoints ---

@app.get("/api/health")
def health():
    return {"status": "online", "service": "Tono Audio Core", "version": "1.0.0"}

@app.get("/api/search")
def search(q: str = Query(..., min_length=1), source: str = "all"):
    """Search YouTube Music, SoundCloud and local tracks."""
    results = search_music(q, source=source)
    # Check favorite status
    for item in results:
        item["is_favorite"] = is_favorite(item["video_id"])
    return {"query": q, "count": len(results), "results": results}

@app.get("/api/trending")
def trending():
    """Get home trending tracks."""
    feed = get_trending_feed()
    for item in feed:
        item["is_favorite"] = is_favorite(item["video_id"])
    return {"results": feed}

@app.get("/api/stream/{video_id}")
def stream_info(video_id: str, source: str = "youtube"):
    """Resolve direct audio streaming URL."""
    try:
        info = resolve_stream(video_id, source=source)
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audio-proxy/{video_id}")
async def audio_proxy(video_id: str, request: Request, source: str = "youtube"):
    """Proxy audio stream with HTTP Range support for seamless seeking and no CORS issues."""
    try:
        # Check if local file exists first
        local_opus = os.path.join(CACHE_DIR, f"{video_id}.opus")
        local_mp3 = os.path.join(CACHE_DIR, f"{video_id}.mp3")
        if os.path.exists(local_opus):
            return FileResponse(local_opus, media_type="audio/ogg")
        if os.path.exists(local_mp3):
            return FileResponse(local_mp3, media_type="audio/mpeg")

        # Resolve stream URL
        stream_data = resolve_stream(video_id, source=source)
        stream_url = stream_data["url"]

        # Forward range headers
        headers = {}
        range_header = request.headers.get("Range")
        if range_header:
            headers["Range"] = range_header

        client = httpx.AsyncClient(timeout=15.0)
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

@app.get("/api/stats")
def storage_stats():
    """Disk stats and cache stats (Cross-platform)."""
    check_path = "D:\\" if os.name == "nt" and os.path.exists("D:\\") else "/"
    try:
        total, used, free = shutil.disk_usage(check_path)
    except Exception:
        total, used, free = shutil.disk_usage(".")

    cached_files = [f for f in os.listdir(CACHE_DIR) if f.endswith((".opus", ".mp3", ".m4a"))]
    cache_bytes = sum(os.path.getsize(os.path.join(CACHE_DIR, f)) for f in cached_files)

    return {
        "storage": check_path,
        "total_gb": round(total / (1024**3), 2),
        "free_gb": round(free / (1024**3), 2),
        "cached_tracks_count": len(cached_files),
        "cache_size_mb": round(cache_bytes / (1024**2), 2),
        "cache_dir": CACHE_DIR
    }

# Mount Frontend SPA if available locally
if os.path.exists(FRONTEND_DIST):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend_app")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
