import os
import hashlib
import mutagen
from mutagen.id3 import ID3, APIC
from typing import Dict, Any, Optional, List
import urllib.request
import urllib.parse
import json

SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.aac', '.opus', '.ogg', '.wav', '.wma', '.alac', '.aiff'}

def parse_audio_file(filepath: str, covers_dir: str) -> Optional[Dict[str, Any]]:
    """Parse audio metadata and extract embedded cover art using mutagen."""
    try:
        audio = mutagen.File(filepath)
        if audio is None:
            return None
        
        filename = os.path.basename(filepath)
        name_no_ext = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1].lower()
        filesize = os.path.getsize(filepath)
        
        duration_sec = int(getattr(audio.info, "length", 0))
        bitrate = int(getattr(audio.info, "bitrate", 0) / 1000) if getattr(audio.info, "bitrate", 0) else 0
        codec = ext.replace(".", "").upper()
        
        m, s = divmod(duration_sec, 60)
        duration_str = f"{m}:{s:02d}"
        
        def get_tag(keys: list) -> str:
            for k in keys:
                try:
                    if hasattr(audio, "tags") and audio.tags and k in audio.tags:
                        val = audio.tags[k]
                        if isinstance(val, list) and len(val) > 0:
                            return str(val[0]).strip()
                        return str(val).strip()
                    elif hasattr(audio, "__getitem__"):
                        val = audio.get(k) if hasattr(audio, "get") else None
                        if val is not None:
                            if isinstance(val, list) and len(val) > 0:
                                return str(val[0]).strip()
                            return str(val).strip()
                except Exception:
                    pass
            return ""

        title = get_tag(["title", "TIT2", "\xa9nam", "TITLE"])
        artist = get_tag(["artist", "TPE1", "\xa9ART", "ARTIST"])
        album = get_tag(["album", "TALB", "\xa9alb", "ALBUM"])
        album_artist = get_tag(["albumartist", "TPE2", "aART", "ALBUMARTIST"])
        genre = get_tag(["genre", "TCON", "\xa9gen", "GENRE"])
        year = get_tag(["date", "year", "TDRC", "TYER", "\xa9day", "DATE", "YEAR"])
        if len(year) > 4:
            year = year[:4]
            
        track_num_raw = get_tag(["tracknumber", "TRCK", "trkn", "TRACKNUMBER"])
        track_number = 0
        if track_num_raw:
            try:
                track_number = int(str(track_num_raw).split("/")[0])
            except Exception:
                track_number = 0

        # Filename fallback heuristic
        if not title:
            if " - " in name_no_ext:
                parts = name_no_ext.split(" - ", 1)
                artist = artist or parts[0].strip()
                title = parts[1].strip()
            else:
                title = name_no_ext
        if not artist:
            artist = "Artista Desconocido"
        if not album:
            album = "Sencillos"

        # Embedded Cover Art Extraction
        cover_data = None
        cover_mime = "image/jpeg"
        
        # ID3
        if hasattr(audio, "tags") and audio.tags:
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    cover_data = tag.data
                    cover_mime = tag.mime or "image/jpeg"
                    break
        
        # FLAC
        if cover_data is None and hasattr(audio, "pictures") and audio.pictures:
            cover_data = audio.pictures[0].data
            cover_mime = audio.pictures[0].mime or "image/jpeg"
            
        # MP4
        if cover_data is None and hasattr(audio, "tags") and audio.tags:
            if "covr" in audio.tags and audio.tags["covr"]:
                cover_data = bytes(audio.tags["covr"][0])
                
        cover_url = ""
        if cover_data:
            os.makedirs(covers_dir, exist_ok=True)
            cover_hash = hashlib.md5(cover_data).hexdigest()
            ext_img = ".png" if "png" in cover_mime.lower() else ".jpg"
            cover_filename = f"{cover_hash}{ext_img}"
            cover_filepath = os.path.join(covers_dir, cover_filename)
            if not os.path.exists(cover_filepath):
                with open(cover_filepath, "wb") as f_img:
                    f_img.write(cover_data)
            cover_url = f"/api/covers/{cover_filename}"

        return {
            "filepath": filepath,
            "filename": filename,
            "title": title,
            "artist": artist,
            "album": album,
            "album_artist": album_artist or artist,
            "genre": genre,
            "year": year,
            "track_number": track_number,
            "duration": duration_str,
            "duration_seconds": duration_sec,
            "bitrate": bitrate,
            "codec": codec,
            "filesize": filesize,
            "cover_url": cover_url
        }
    except Exception as e:
        print(f"Error parsing audio file {filepath}: {e}")
        return None

def scan_directory(folder_path: str, covers_dir: str) -> List[Dict[str, Any]]:
    """Scan a folder recursively for audio files and extract metadata."""
    scanned_tracks = []
    if not os.path.exists(folder_path):
        return []

    for root, _, files in os.walk(folder_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                fpath = os.path.join(root, f)
                track_info = parse_audio_file(fpath, covers_dir)
                if track_info:
                    scanned_tracks.append(track_info)

    return scanned_tracks

def fetch_local_track_lyrics(filepath: str, title: str, artist: str) -> Dict[str, Any]:
    """Check for local .lrc file next to track, or query LRCLIB free database."""
    base_no_ext = os.path.splitext(filepath)[0]
    lrc_path = f"{base_no_ext}.lrc"
    
    if os.path.exists(lrc_path):
        try:
            with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_lrc = f.read()
            from engine import parse_lrc
            synced = parse_lrc(raw_lrc)
            if synced:
                return {"has_lyrics": True, "is_synced": True, "synced": synced, "plain": raw_lrc}
        except Exception as e:
            print("Local LRC parse note:", e)

    # Online LRCLIB fallback
    try:
        from engine import fetch_synced_lyrics
        return fetch_synced_lyrics(title, artist)
    except Exception:
        return {"has_lyrics": False, "is_synced": False, "synced": [], "plain": ""}
