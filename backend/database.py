import sqlite3
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spotystream.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Favorites table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS favorites (
        video_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        album TEXT,
        duration TEXT,
        duration_seconds INTEGER,
        thumbnail TEXT,
        source TEXT DEFAULT 'youtube',
        is_downloaded INTEGER DEFAULT 0,
        local_path TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Playlists table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS playlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        cover_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Playlist tracks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS playlist_tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        playlist_id INTEGER,
        video_id TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        album TEXT,
        duration TEXT,
        duration_seconds INTEGER,
        thumbnail TEXT,
        source TEXT DEFAULT 'youtube',
        position INTEGER,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (playlist_id) REFERENCES playlists (id) ON DELETE CASCADE
    );
    """)

    # History
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        album TEXT,
        duration TEXT,
        duration_seconds INTEGER,
        thumbnail TEXT,
        source TEXT DEFAULT 'youtube',
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # App Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # Library Tracks (Local Music Library)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS library_tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filepath TEXT UNIQUE NOT NULL,
        filename TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        album TEXT DEFAULT '',
        album_artist TEXT DEFAULT '',
        genre TEXT DEFAULT '',
        year TEXT DEFAULT '',
        track_number INTEGER DEFAULT 0,
        duration TEXT DEFAULT '0:00',
        duration_seconds INTEGER DEFAULT 0,
        bitrate INTEGER DEFAULT 0,
        codec TEXT DEFAULT '',
        filesize INTEGER DEFAULT 0,
        cover_url TEXT DEFAULT '',
        play_count INTEGER DEFAULT 0,
        is_favorite INTEGER DEFAULT 0,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_played TIMESTAMP
    );
    """)

    # Library Folders (Folders to scan)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS library_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_path TEXT UNIQUE NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

# --- Settings Helpers ---
def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# --- Favorites Helpers ---
def add_favorite(track: Dict[str, Any]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR REPLACE INTO favorites 
        (video_id, title, artist, album, duration, duration_seconds, thumbnail, source, is_downloaded, local_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            track.get("video_id") or track.get("videoId"),
            track.get("title", "Unknown Title"),
            track.get("artist", "Unknown Artist"),
            track.get("album", ""),
            track.get("duration", "0:00"),
            track.get("duration_seconds", 0),
            track.get("thumbnail", ""),
            track.get("source", "youtube"),
            1 if track.get("is_downloaded") else 0,
            track.get("local_path", "")
        ))
        conn.commit()
        return True
    except Exception as e:
        print("Error adding favorite:", e)
        return False
    finally:
        conn.close()

def remove_favorite(video_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorites WHERE video_id = ?", (video_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def is_favorite(video_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM favorites WHERE video_id = ?", (video_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def get_favorites() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM favorites ORDER BY added_at DESC")
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

# --- Playlists Helpers ---
def create_playlist(name: str, description: str = "") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO playlists (name, description) VALUES (?, ?)", (name, description))
    conn.commit()
    playlist_id = cursor.lastrowid
    conn.close()
    return playlist_id

def get_playlists() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.*, COUNT(pt.id) as track_count 
    FROM playlists p 
    LEFT JOIN playlist_tracks pt ON p.id = pt.playlist_id 
    GROUP BY p.id 
    ORDER BY p.created_at DESC
    """)
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

def get_playlist_tracks(playlist_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM playlist_tracks WHERE playlist_id = ? ORDER BY position ASC, id ASC", (playlist_id,))
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

def add_track_to_playlist(playlist_id: int, track: Dict[str, Any]) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
    pos = cursor.fetchone()[0]
    
    cursor.execute("""
    INSERT INTO playlist_tracks 
    (playlist_id, video_id, title, artist, album, duration, duration_seconds, thumbnail, source, position)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        playlist_id,
        track.get("video_id") or track.get("videoId"),
        track.get("title", "Unknown"),
        track.get("artist", "Unknown"),
        track.get("album", ""),
        track.get("duration", "0:00"),
        track.get("duration_seconds", 0),
        track.get("thumbnail", ""),
        track.get("source", "youtube"),
        pos
    ))
    conn.commit()
    conn.close()
    return True

def delete_playlist(playlist_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
    cursor.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    conn.commit()
    conn.close()
    return True

# --- History Helpers ---
def add_history(track: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO history (video_id, title, artist, album, duration, duration_seconds, thumbnail, source)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        track.get("video_id") or track.get("videoId"),
        track.get("title", "Unknown"),
        track.get("artist", "Unknown"),
        track.get("album", ""),
        track.get("duration", "0:00"),
        track.get("duration_seconds", 0),
        track.get("thumbnail", ""),
        track.get("source", "youtube")
    ))
    conn.commit()
    conn.close()

def get_recent_history(limit: int = 30) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT DISTINCT video_id, title, artist, album, duration, thumbnail, source, MAX(played_at) as last_played
    FROM history 
    GROUP BY video_id 
    ORDER BY last_played DESC 
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

# --- Library Management Helpers ---

def add_library_folder(folder_path: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO library_folders (folder_path) VALUES (?)", (folder_path,))
        conn.commit()
        return True
    finally:
        conn.close()

def get_library_folders() -> List[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT folder_path FROM library_folders ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def remove_library_folder(folder_path: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM library_folders WHERE folder_path = ?", (folder_path,))
    conn.commit()
    conn.close()
    return True

def upsert_library_track(data: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO library_tracks (
        filepath, filename, title, artist, album, album_artist, genre, year,
        track_number, duration, duration_seconds, bitrate, codec, filesize, cover_url
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(filepath) DO UPDATE SET
        title = excluded.title,
        artist = excluded.artist,
        album = excluded.album,
        album_artist = excluded.album_artist,
        genre = excluded.genre,
        year = excluded.year,
        duration = excluded.duration,
        duration_seconds = excluded.duration_seconds,
        bitrate = excluded.bitrate,
        codec = excluded.codec,
        filesize = excluded.filesize,
        cover_url = CASE WHEN excluded.cover_url != '' THEN excluded.cover_url ELSE library_tracks.cover_url END
    """, (
        data["filepath"], data["filename"], data["title"], data["artist"],
        data.get("album", ""), data.get("album_artist", ""), data.get("genre", ""),
        data.get("year", ""), data.get("track_number", 0), data.get("duration", "0:00"),
        data.get("duration_seconds", 0), data.get("bitrate", 0), data.get("codec", ""),
        data.get("filesize", 0), data.get("cover_url", "")
    ))
    track_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return track_id

def get_library_tracks(genre: str = "", artist: str = "", album: str = "", query: str = "", sort_by: str = "title") -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM library_tracks WHERE 1=1"
    params = []
    if genre:
        sql += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    if artist:
        sql += " AND (artist LIKE ? OR album_artist LIKE ?)"
        params.extend([f"%{artist}%", f"%{artist}%"])
    if album:
        sql += " AND album = ?"
        params.append(album)
    if query:
        sql += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

    if sort_by == "recent":
        sql += " ORDER BY added_at DESC"
    elif sort_by == "play_count":
        sql += " ORDER BY play_count DESC"
    elif sort_by == "artist":
        sql += " ORDER BY artist COLLATE NOCASE ASC, album COLLATE NOCASE ASC, track_number ASC"
    else:
        sql += " ORDER BY title COLLATE NOCASE ASC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

def get_library_albums() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT album, artist, album_artist, year, cover_url, COUNT(*) as track_count, SUM(duration_seconds) as total_duration
    FROM library_tracks
    WHERE album != ''
    GROUP BY album, artist
    ORDER BY album COLLATE NOCASE ASC
    """)
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

def get_library_artists() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT artist, COUNT(DISTINCT album) as album_count, COUNT(*) as track_count, cover_url
    FROM library_tracks
    WHERE artist != ''
    GROUP BY artist
    ORDER BY artist COLLATE NOCASE ASC
    """)
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

def get_library_genres() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT genre, COUNT(*) as track_count
    FROM library_tracks
    WHERE genre != ''
    GROUP BY genre
    ORDER BY track_count DESC
    """)
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return results

def get_library_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        COUNT(*) as total_tracks,
        COUNT(DISTINCT album) as total_albums,
        COUNT(DISTINCT artist) as total_artists,
        COALESCE(SUM(filesize), 0) as total_bytes,
        COALESCE(SUM(duration_seconds), 0) as total_duration_seconds
    FROM library_tracks
    """)
    row = cursor.fetchone()
    conn.close()
    if row:
        bytes_val = row["total_bytes"]
        gb_val = round(bytes_val / (1024 * 1024 * 1024), 2)
        hours_val = round(row["total_duration_seconds"] / 3600, 1)
        return {
            "total_tracks": row["total_tracks"],
            "total_albums": row["total_albums"],
            "total_artists": row["total_artists"],
            "total_bytes": bytes_val,
            "total_gb": gb_val,
            "total_hours": hours_val
        }
    return {"total_tracks": 0, "total_albums": 0, "total_artists": 0, "total_gb": 0, "total_hours": 0}

def toggle_library_favorite(track_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE library_tracks SET is_favorite = 1 - is_favorite WHERE id = ?", (track_id,))
    cursor.execute("SELECT is_favorite FROM library_tracks WHERE id = ?", (track_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    return bool(row[0]) if row else False

def increment_library_play(track_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE library_tracks SET play_count = play_count + 1, last_played = CURRENT_TIMESTAMP WHERE id = ?", (track_id,))
    conn.commit()
    conn.close()

def delete_library_track(track_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM library_tracks WHERE id = ?", (track_id,))
    conn.commit()
    conn.close()
    return True

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
