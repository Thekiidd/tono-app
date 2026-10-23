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

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
