<script>
  import { onMount, tick } from 'svelte';
  import { 
    Play, Pause, SkipForward, SkipBack, Shuffle, Repeat, Volume1, Volume2, VolumeX,
    Search, Heart, Music, ListMusic, Download, Disc, Clock, Mic2, Home,
    Library, HardDrive, Sparkles, User, Info, X, Check, Disc3, Settings, Folder,
    Maximize2, Minimize2, SlidersHorizontal, Plus, Radio
  } from 'lucide-svelte';

  // --- Navigation & Views ---
  let activeTab = 'home'; // 'home' | 'search' | 'library' | 'lyrics' | 'artist'
  let searchQuery = '';
  let searchSource = 'all'; // 'all' | 'youtube' | 'soundcloud'
  let searchResults = [];
  let isSearching = false;
  let trendingTracks = [];
  let favorites = [];
  let playlists = [];
  let queue = [];
  let queueIndex = -1;
  
  // Current track state
  let currentTrack = null;
  let isPlaying = false;
  let currentTime = 0;
  let duration = 0;
  let volume = 0.8;
  let isMuted = false;
  let isShuffle = false;
  let repeatMode = 0; // 0: off, 1: all, 2: one
  let isLoadingAudio = false;

  // Lyrics state
  let lyricsData = { has_lyrics: false, is_synced: false, synced: [], plain: '' };
  let currentLyricIndex = -1;
  let lyricsContainer;

  // Artist Profile state
  let currentArtist = null;
  let isLoadingArtist = false;

  // Credits Modal state
  let showCreditsModal = false;
  let creditsData = null;
  let isLoadingCredits = false;

  // Storage Stats & Disks Manager
  let storageStats = { storage: 'Disco D:', free_gb: 0, cached_tracks_count: 0, cache_size_mb: 0 };
  let showStorageModal = false;
  let drivesData = { active_storage_dir: '', drives: [] };
  let selectedDrive = null;
  let customFolderName = 'Tono_Music';
  let isSavingStorage = false;
  let storageMessage = '';

  // Spotify Features State
  let showQueueDrawer = false;
  let showFullscreenMode = false;
  let showAddToPlaylistModal = false;
  let trackToAddToPlaylist = null;
  let newPlaylistInput = '';
  let showAudioSettingsModal = false;
  let crossfadeSeconds = 3;
  let playbackSpeed = 1.0;
  let sleepTimerMinutes = 0;
  let sleepTimerRemaining = 0;
  let sleepTimerInterval = null;
  const searchCache = new Map();
  const artistCache = new Map();
  let forYouData = null;
  let isLoadingForYou = false;
  let matchedArtist = null;
  let toastMessage = '';
  let toastTimeout;
  const prefetchedSet = new Set();

  // Audio DOM element
  let audioElement;

  // Reactive dynamic percentages for progress bar & volume fill
  $: progressPercent = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;
  $: volumePercent = isMuted ? 0 : Math.round(volume * 100);

  // Cloud & Local dynamic API base
  const RAW_API = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
  const API_BASE = RAW_API ? `${RAW_API}/api` : '/api';

  onMount(async () => {
    await Promise.all([
      fetchTrending(),
      fetchFavorites(),
      fetchPlaylists(),
      fetchStorageStats(),
      loadForYouFeed()
    ]);

    // Media Session API for Keyboard Media Keys & Windows Controls
    if ('mediaSession' in navigator) {
      navigator.mediaSession.setActionHandler('play', () => togglePlay());
      navigator.mediaSession.setActionHandler('pause', () => togglePlay());
      navigator.mediaSession.setActionHandler('previoustrack', () => playPrev());
      navigator.mediaSession.setActionHandler('nexttrack', () => playNext());
    }

    // Spotify-style Global Keyboard Shortcuts
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA'].includes(e.target?.tagName)) return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        seekRelative(5);
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        seekRelative(-5);
      } else if (e.code === 'ArrowUp') {
        e.preventDefault();
        setVolume(Math.min(1, volume + 0.05));
      } else if (e.code === 'ArrowDown') {
        e.preventDefault();
        setVolume(Math.max(0, volume - 0.05));
      } else if (e.key.toLowerCase() === 'm') {
        toggleMute();
      } else if (e.key.toLowerCase() === 'l') {
        activeTab = activeTab === 'lyrics' ? 'home' : 'lyrics';
      } else if (e.key.toLowerCase() === 'q') {
        showQueueDrawer = !showQueueDrawer;
      } else if (e.key.toLowerCase() === 'f') {
        showFullscreenMode = !showFullscreenMode;
      } else if (e.key === 'Escape') {
        showFullscreenMode = false;
        showQueueDrawer = false;
        showAddToPlaylistModal = false;
        showAudioSettingsModal = false;
        showStorageModal = false;
        showCreditsModal = false;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  });

  // --- API Fetchers ---
  async function fetchTrending() {
    try {
      const res = await fetch(`${API_BASE}/trending`);
      const data = await res.json();
      trendingTracks = data.results || [];
    } catch (e) {
      console.error('Error fetching trending:', e);
    }
  }

  async function fetchFavorites() {
    try {
      const res = await fetch(`${API_BASE}/favorites`);
      const data = await res.json();
      favorites = data.favorites || [];
    } catch (e) {
      console.error('Error fetching favorites:', e);
    }
  }

  async function fetchPlaylists() {
    try {
      const res = await fetch(`${API_BASE}/playlists`);
      const data = await res.json();
      playlists = data.playlists || [];
    } catch (e) {
      console.error('Error fetching playlists:', e);
    }
  }

  async function fetchStorageStats() {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      const data = await res.json();
      storageStats = data;
    } catch (e) {
      console.error('Error fetching stats:', e);
    }
  }

  async function fetchDrives() {
    try {
      const res = await fetch(`${API_BASE}/drives`);
      if (res.ok) {
        drivesData = await res.json();
        const active = drivesData.drives.find(d => d.is_active);
        if (active) {
          selectedDrive = active;
        } else if (drivesData.drives.length > 0) {
          selectedDrive = drivesData.drives[0];
        }
      }
    } catch (e) {
      console.error('Error fetching drives:', e);
    }
  }

  async function saveStorageConfig() {
    if (!selectedDrive) return;
    isSavingStorage = true;
    storageMessage = '';
    try {
      const res = await fetch(`${API_BASE}/settings/storage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          drive: selectedDrive.path,
          folder_name: customFolderName.trim() || 'Tono_Music'
        })
      });
      if (res.ok) {
        storageMessage = '¡Disco y carpeta configurados exitosamente!';
        await fetchStorageStats();
        await fetchDrives();
        setTimeout(() => {
          showStorageModal = false;
          storageMessage = '';
        }, 1200);
      } else {
        const err = await res.json();
        storageMessage = `Error: ${err.detail || 'No se pudo guardar'}`;
      }
    } catch (e) {
      storageMessage = 'Error al conectar con el servidor';
    } finally {
      isSavingStorage = false;
    }
  }

  function openStorageModal() {
    fetchDrives();
    showStorageModal = true;
  }

  // --- Spotify Features & Automated Prefetch Engine ---
  function showToast(msg) {
    clearTimeout(toastTimeout);
    toastMessage = msg;
    toastTimeout = setTimeout(() => { toastMessage = ''; }, 2600);
  }

  function prefetchTrack(track) {
    if (!track || !track.video_id || prefetchedSet.has(track.video_id)) return;
    prefetchedSet.add(track.video_id);
    fetch(`${API_BASE}/stream/prefetch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_id: track.video_id,
        title: track.title || '',
        artist: track.artist || '',
        source: track.source || 'youtube'
      })
    }).catch(() => {});
  }

  function seekRelative(delta) {
    if (audioElement && duration > 0) {
      const nextTime = Math.max(0, Math.min(duration, currentTime + delta));
      audioElement.currentTime = nextTime;
      currentTime = nextTime;
    }
  }

  function setVolume(v) {
    volume = Math.max(0, Math.min(1, v));
    if (audioElement) audioElement.volume = isMuted ? 0 : volume;
  }

  function removeFromQueue(index, e) {
    if (e) e.stopPropagation();
    queue = queue.filter((_, i) => i !== index);
    if (queueIndex >= index) queueIndex = Math.max(0, queueIndex - 1);
    showToast('Pista eliminada de la cola');
  }

  function clearQueue() {
    if (currentTrack) {
      queue = [currentTrack];
      queueIndex = 0;
    } else {
      queue = [];
      queueIndex = -1;
    }
    showToast('Cola de reproducción vaciada');
  }

  function openAddToPlaylist(track, e) {
    if (e) e.stopPropagation();
    trackToAddToPlaylist = track;
    showAddToPlaylistModal = true;
  }

  async function addTrackToSelectedPlaylist(playlistId, playlistName) {
    if (!trackToAddToPlaylist) return;
    try {
      await fetch(`${API_BASE}/playlists/${playlistId}/tracks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(trackToAddToPlaylist)
      });
      showToast(`Añadida a "${playlistName}"`);
      await fetchPlaylists();
      showAddToPlaylistModal = false;
      trackToAddToPlaylist = null;
    } catch (err) {
      console.error(err);
      showToast('Error al añadir canción');
    }
  }

  async function createAndAddToPlaylist() {
    if (!newPlaylistInput.trim() || !trackToAddToPlaylist) return;
    try {
      const res = await fetch(`${API_BASE}/playlists`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newPlaylistInput.trim() })
      });
      const data = await res.json();
      await addTrackToSelectedPlaylist(data.id, data.name);
      newPlaylistInput = '';
    } catch (err) {
      console.error(err);
      showToast('Error al crear playlist');
    }
  }

  function setPlaybackSpeed(speed) {
    playbackSpeed = speed;
    if (audioElement) {
      audioElement.playbackRate = speed;
    }
    showToast(`Velocidad: ${speed}x`);
  }

  function setSleepTimer(minutes) {
    if (sleepTimerInterval) clearInterval(sleepTimerInterval);
    sleepTimerMinutes = minutes;
    if (minutes === 0) {
      sleepTimerRemaining = 0;
      showToast('Temporizador desactivado');
      return;
    }
    if (minutes === 'end') {
      sleepTimerRemaining = -1;
      showToast('Se apagará al terminar esta canción');
      return;
    }
    sleepTimerRemaining = minutes * 60;
    showToast(`Temporizador: apagado en ${minutes} min`);
    sleepTimerInterval = setInterval(() => {
      if (sleepTimerRemaining > 0) {
        sleepTimerRemaining--;
        if (sleepTimerRemaining <= 0) {
          clearInterval(sleepTimerInterval);
          if (audioElement) audioElement.pause();
          isPlaying = false;
          sleepTimerMinutes = 0;
          showToast('🌙 Temporizador: Reproducción detenida');
        }
      }
    }, 1000);
  }

  function resetAudioOutput() {
    if (audioElement) {
      const curSrc = audioElement.src;
      const curTime = audioElement.currentTime;
      audioElement.pause();
      audioElement.load();
      if (curSrc) {
        audioElement.src = curSrc;
        audioElement.currentTime = curTime;
        audioElement.play().catch(e => console.warn('Play error:', e));
        isPlaying = true;
      }
    }
    showToast('🔊 Salida de audio restablecida');
  }

  // --- Discovery & Smart Radio Engine ---
  async function loadForYouFeed() {
    isLoadingForYou = true;
    try {
      const res = await fetch(`${API_BASE}/recommendations/for-you`);
      if (res.ok) {
        forYouData = await res.json();
      }
    } catch (e) {
      console.warn('For-you feed note:', e);
    } finally {
      isLoadingForYou = false;
    }
  }

  async function startArtistRadio(artistName) {
    showToast(`Iniciando Radio de ${artistName}...`);
    try {
      const res = await fetch(`${API_BASE}/recommendations/radio?artist=${encodeURIComponent(artistName)}`);
      const data = await res.json();
      if (data.tracks && data.tracks.length > 0) {
        playTrack(data.tracks[0], data.tracks, 0);
        showToast(`✨ Radio de ${artistName} activa (${data.tracks.length} canciones)`);
      } else {
        openArtistProfile(artistName);
      }
    } catch (e) {
      console.error('Radio error:', e);
      openArtistProfile(artistName);
    }
  }

  async function startSongRadio(track, e) {
    if (e) e.stopPropagation();
    showToast(`Iniciando Radio de "${track.title}"...`);
    try {
      const res = await fetch(`${API_BASE}/recommendations/radio?video_id=${track.video_id}`);
      const data = await res.json();
      if (data.tracks && data.tracks.length > 0) {
        playTrack(data.tracks[0], data.tracks, 0);
        showToast(`✨ Radio similar activa (${data.tracks.length} canciones)`);
      }
    } catch (e) {
      console.error('Song radio error:', e);
    }
  }

  // --- Search Handler with Instant 0ms Memory Cache ---
  let searchTimeout;
  function handleSearchInput() {
    clearTimeout(searchTimeout);
    const q = searchQuery.trim();
    if (!q) {
      searchResults = [];
      matchedArtist = null;
      return;
    }
    const cacheKey = `${q.toLowerCase()}::${searchSource}`;
    if (searchCache.has(cacheKey)) {
      const cached = searchCache.get(cacheKey);
      searchResults = cached.results || [];
      matchedArtist = cached.matched_artist || null;
      isSearching = false;
      return;
    }
    searchTimeout = setTimeout(performSearch, 280);
  }

  async function performSearch() {
    const q = searchQuery.trim();
    if (!q) return;
    const cacheKey = `${q.toLowerCase()}::${searchSource}`;
    if (searchCache.has(cacheKey)) {
      const cached = searchCache.get(cacheKey);
      searchResults = cached.results || [];
      matchedArtist = cached.matched_artist || null;
      isSearching = false;
      return;
    }
    isSearching = true;
    try {
      const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}&source=${searchSource}`);
      const data = await res.json();
      searchResults = data.results || [];
      matchedArtist = data.matched_artist || null;
      searchCache.set(cacheKey, { results: searchResults, matched_artist: matchedArtist });
    } catch (e) {
      console.error('Search error:', e);
    } finally {
      isSearching = false;
    }
  }

  // --- Artist Profile Fetcher with Instant 0ms Cache ---
  async function openArtistProfile(artistName, e) {
    if (e) e.stopPropagation();
    const aKey = artistName.trim().toLowerCase();
    activeTab = 'artist';
    if (artistCache.has(aKey)) {
      currentArtist = artistCache.get(aKey);
      isLoadingArtist = false;
      return;
    }
    isLoadingArtist = true;
    try {
      const res = await fetch(`${API_BASE}/artist?name=${encodeURIComponent(artistName)}`);
      const data = await res.json();
      currentArtist = data;
      artistCache.set(aKey, data);
    } catch (err) {
      console.error('Error fetching artist:', err);
    } finally {
      isLoadingArtist = false;
    }
  }

  // --- Song Credits Fetcher ---
  async function openSongCredits(track, e) {
    if (e) e.stopPropagation();
    showCreditsModal = true;
    creditsData = null;
    isLoadingCredits = true;
    try {
      const res = await fetch(`${API_BASE}/credits/${track.video_id}`);
      const data = await res.json();
      creditsData = { ...data, trackTitle: track.title, trackArtist: track.artist };
    } catch (err) {
      console.error('Error fetching credits:', err);
    } finally {
      isLoadingCredits = false;
    }
  }

  // --- Playback Engine ---
  async function playTrack(track, newQueue = null, indexInQueue = -1) {
    if (newQueue) {
      queue = [...newQueue];
      queueIndex = indexInQueue >= 0 ? indexInQueue : queue.findIndex(t => t.video_id === track.video_id);
    } else if (!queue.some(t => t.video_id === track.video_id)) {
      queue = [track, ...queue];
      queueIndex = 0;
    }

    currentTrack = track;
    isLoadingAudio = true;
    currentTime = 0;

    // Lookahead automatic background prefetching for next queue items
    if (queue.length > queueIndex + 1) prefetchTrack(queue[queueIndex + 1]);
    if (queue.length > queueIndex + 2) prefetchTrack(queue[queueIndex + 2]);

    // Fetch synchronized lyrics
    fetchLyrics(track.title, track.artist);

    // Record in history
    fetch(`${API_BASE}/history`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(track)
    }).catch(() => {});

    // Update Media Session
    if ('mediaSession' in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title,
        artist: track.artist,
        album: track.album || 'Tono',
        artwork: [{ src: track.thumbnail, sizes: '512x512', type: 'image/jpeg' }]
      });
    }

    await tick();
    if (audioElement) {
      const queryParams = new URLSearchParams({
        source: track.source || 'youtube',
        title: track.title || '',
        artist: track.artist || ''
      }).toString();

      try {
        // Resolve stream URL for direct high-speed cloud CDN playback
        const streamRes = await fetch(`${API_BASE}/stream/${track.video_id}?${queryParams}`);
        if (streamRes.ok) {
          const streamData = await streamRes.json();
          if (streamData.url) {
            audioElement.src = streamData.url.startsWith('http') ? streamData.url : (RAW_API + streamData.url);
          } else {
            audioElement.src = `${API_BASE}/audio-proxy/${track.video_id}?${queryParams}`;
          }
        } else {
          audioElement.src = `${API_BASE}/audio-proxy/${track.video_id}?${queryParams}`;
        }
        audioElement.playbackRate = playbackSpeed;
        await audioElement.play();
        isPlaying = true;
      } catch (err) {
        console.warn('Direct audio stream play error, using high-speed audio proxy:', err);
        try {
          audioElement.src = `${API_BASE}/audio-proxy/${track.video_id}?${queryParams}`;
          await audioElement.play();
          isPlaying = true;
        } catch (e2) {
          console.error('Proxy play error:', e2);
        }
      } finally {
        isLoadingAudio = false;
      }
    }
  }

  function togglePlay() {
    if (!audioElement || !currentTrack) return;
    if (isPlaying) {
      audioElement.pause();
      isPlaying = false;
    } else {
      audioElement.play().catch(console.error);
      isPlaying = true;
    }
  }

  function playNext() {
    if (queue.length === 0) return;
    if (sleepTimerMinutes === 'end') {
      sleepTimerMinutes = 0;
      sleepTimerRemaining = 0;
      if (audioElement) audioElement.pause();
      isPlaying = false;
      showToast('🌙 Temporizador: Reproducción detenida al finalizar canción');
      return;
    }
    if (repeatMode === 2 && audioElement) {
      audioElement.currentTime = 0;
      audioElement.play();
      return;
    }
    if (isShuffle) {
      queueIndex = Math.floor(Math.random() * queue.length);
      playTrack(queue[queueIndex]);
      return;
    }
    if (queueIndex + 1 < queue.length) {
      queueIndex++;
      playTrack(queue[queueIndex]);
    } else if (repeatMode === 1) {
      queueIndex = 0;
      playTrack(queue[0]);
    } else if (currentTrack) {
      // Autoplay: seamlessly load smart radio recommendations
      fetch(`${API_BASE}/recommendations/radio?video_id=${currentTrack.video_id}`)
        .then(res => res.json())
        .then(data => {
          if (data.tracks && data.tracks.length > 1) {
            const nextTracks = data.tracks.filter(t => t.video_id !== currentTrack.video_id);
            if (nextTracks.length > 0) {
              queue = [...queue, ...nextTracks];
              queueIndex++;
              playTrack(queue[queueIndex]);
              showToast('✨ Autoplay: Continuando con pistas recomendadas');
            }
          }
        })
        .catch(console.warn);
    }
  }

  function playPrev() {
    if (!audioElement) return;
    if (audioElement.currentTime > 3) {
      audioElement.currentTime = 0;
      return;
    }
    if (queueIndex > 0) {
      queueIndex--;
      playTrack(queue[queueIndex]);
    }
  }

  function handleTimeUpdate() {
    if (!audioElement) return;
    currentTime = audioElement.currentTime;
    duration = audioElement.duration || 0;

    // Sync lyrics line
    if (lyricsData.is_synced && lyricsData.synced.length > 0) {
      let idx = lyricsData.synced.findIndex((line, i) => {
        const next = lyricsData.synced[i + 1];
        return currentTime >= line.time && (!next || currentTime < next.time);
      });
      if (idx !== -1 && idx !== currentLyricIndex) {
        currentLyricIndex = idx;
        scrollLyricIntoView(idx);
      }
    }
  }

  function handleSeek(e) {
    const val = parseFloat(e.target.value);
    currentTime = val;
    if (audioElement) {
      audioElement.currentTime = val;
    }
  }

  function handleVolumeChange(e) {
    volume = parseFloat(e.target.value);
    if (audioElement) {
      audioElement.volume = volume;
      isMuted = volume === 0;
    }
  }

  function toggleMute() {
    if (!audioElement) return;
    isMuted = !isMuted;
    audioElement.muted = isMuted;
  }

  function cycleRepeat() {
    repeatMode = (repeatMode + 1) % 3;
  }

  // --- Lyrics ---
  async function fetchLyrics(title, artist) {
    lyricsData = { has_lyrics: false, is_synced: false, synced: [], plain: 'Buscando letra...' };
    currentLyricIndex = -1;
    try {
      const res = await fetch(`${API_BASE}/lyrics?title=${encodeURIComponent(title)}&artist=${encodeURIComponent(artist)}`);
      const data = await res.json();
      lyricsData = data;
    } catch (e) {
      lyricsData = { has_lyrics: false, is_synced: false, synced: [], plain: 'No se encontraron letras disponibles.' };
    }
  }

  function scrollLyricIntoView(index) {
    if (!lyricsContainer) return;
    const activeEl = lyricsContainer.children[index];
    if (activeEl) {
      activeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  // --- Favorites & Downloads ---
  async function toggleFavorite(track, e) {
    if (e) e.stopPropagation();
    const isFav = favorites.some(f => f.video_id === track.video_id);
    if (isFav) {
      await fetch(`${API_BASE}/favorites/${track.video_id}`, { method: 'DELETE' });
      favorites = favorites.filter(f => f.video_id !== track.video_id);
    } else {
      await fetch(`${API_BASE}/favorites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(track)
      });
      favorites = [track, ...favorites];
    }
  }

  async function downloadTrack(track, e) {
    if (e) e.stopPropagation();
    try {
      await fetch(`${API_BASE}/download/${track.video_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(track)
      });
      alert(`Guardando "${track.title}" en el almacenamiento local.`);
      setTimeout(fetchStorageStats, 3500);
    } catch (err) {
      console.error(err);
    }
  }

  function formatSeconds(sec) {
    if (!sec || isNaN(sec)) return '0:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  }

  function handleAudioError() {
    if (currentTrack && audioElement && !audioElement.src.includes('/audio-proxy/')) {
      console.warn('Direct stream playback error, switching to high-speed proxy fallback...');
      const queryParams = new URLSearchParams({
        source: currentTrack.source || 'youtube',
        title: currentTrack.title || '',
        artist: currentTrack.artist || ''
      }).toString();
      audioElement.src = `${API_BASE}/audio-proxy/${currentTrack.video_id}?${queryParams}`;
      audioElement.play().catch(e => console.error('Audio proxy playback error:', e));
    }
  }
</script>

<!-- Hidden Audio Element -->
<audio 
  bind:this={audioElement}
  on:timeupdate={handleTimeUpdate}
  on:ended={playNext}
  on:waiting={() => isLoadingAudio = true}
  on:playing={() => isLoadingAudio = false}
  on:error={handleAudioError}
></audio>

<!-- SONG CREDITS MODAL (SPOTIFY STYLE) -->
{#if showCreditsModal}
  <div 
    style="position: fixed; inset: 0; background: rgba(0,0,0,0.75); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 200; padding: 20px;"
    on:click={() => showCreditsModal = false}
    role="dialog"
    tabindex="-1"
  >
    <div 
      style="background: #141722; width: 100%; max-width: 520px; border-radius: 16px; border: 1px solid #252c3f; padding: 28px; box-shadow: 0 24px 60px rgba(0,0,0,0.8); max-height: 85vh; overflow-y: auto;"
      on:click={(e) => e.stopPropagation()}
      role="document"
    >
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
        <div>
          <span style="font-size: 0.75rem; color: #60a5fa; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">Créditos de la Canción</span>
          <h3 style="font-size: 1.45rem; font-weight: 800; margin-top: 4px;">{creditsData?.trackTitle || currentTrack?.title}</h3>
          <p style="color: #94a3b8; font-size: 0.9rem;">{creditsData?.trackArtist || currentTrack?.artist}</p>
        </div>
        <button 
          on:click={() => showCreditsModal = false}
          style="background: #1c2130; border: none; color: #94a3b8; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer;"
        >
          <X size={18} />
        </button>
      </div>

      {#if isLoadingCredits}
        <div style="display: flex; align-items: center; justify-content: center; height: 180px; color: #60a5fa; gap: 10px;">
          <Disc size={24} class="animate-spin" /> Extrayendo créditos oficiales de producción...
        </div>
      {:else if creditsData}
        <div style="display: flex; flex-direction: column; gap: 20px;">
          
          <!-- PERFORMERS -->
          {#if creditsData.performers?.length > 0}
            <div>
              <h4 style="font-size: 0.82rem; color: #64748b; font-weight: 800; text-transform: uppercase; margin-bottom: 8px;">Intérpretes & Músicos</h4>
              <div style="display: flex; flex-direction: column; gap: 6px;">
                {#each creditsData.performers as p}
                  <div style="display: flex; justify-content: space-between; font-size: 0.9rem; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04);">
                    <span style="font-weight: 600; color: #fff;">{p.name}</span>
                    <span style="color: #94a3b8; font-size: 0.8rem;">{p.role}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- WRITERS / COMPOSERS -->
          {#if creditsData.writers?.length > 0}
            <div>
              <h4 style="font-size: 0.82rem; color: #64748b; font-weight: 800; text-transform: uppercase; margin-bottom: 8px;">Composición & Letra</h4>
              <div style="display: flex; flex-direction: column; gap: 6px;">
                {#each creditsData.writers as w}
                  <div style="display: flex; justify-content: space-between; font-size: 0.9rem; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04);">
                    <span style="font-weight: 600; color: #fff;">{w.name}</span>
                    <span style="color: #94a3b8; font-size: 0.8rem;">{w.role}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- PRODUCERS -->
          {#if creditsData.producers?.length > 0}
            <div>
              <h4 style="font-size: 0.82rem; color: #64748b; font-weight: 800; text-transform: uppercase; margin-bottom: 8px;">Producción</h4>
              <div style="display: flex; flex-direction: column; gap: 6px;">
                {#each creditsData.producers as prod}
                  <div style="display: flex; justify-content: space-between; font-size: 0.9rem; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04);">
                    <span style="font-weight: 600; color: #fff;">{prod.name}</span>
                    <span style="color: #94a3b8; font-size: 0.8rem;">{prod.role}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- ENGINEERS -->
          {#if creditsData.engineers?.length > 0}
            <div>
              <h4 style="font-size: 0.82rem; color: #64748b; font-weight: 800; text-transform: uppercase; margin-bottom: 8px;">Ingeniería de Audio (Mezcla & Master)</h4>
              <div style="display: flex; flex-direction: column; gap: 6px;">
                {#each creditsData.engineers as eng}
                  <div style="display: flex; justify-content: space-between; font-size: 0.9rem; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04);">
                    <span style="font-weight: 600; color: #fff;">{eng.name}</span>
                    <span style="color: #94a3b8; font-size: 0.8rem;">{eng.role}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- RECORD LABEL & RELEASE DATE -->
          <div style="margin-top: 10px; padding: 12px; background: #0c0e15; border-radius: 8px; font-size: 0.8rem; color: #94a3b8; display: flex; flex-direction: column; gap: 4px;">
            {#if creditsData.label}
              <div><strong style="color: #fff;">Sello Discográfico:</strong> {creditsData.label}</div>
            {/if}
            {#if creditsData.release_date}
              <div><strong style="color: #fff;">Fecha de Lanzamiento:</strong> {creditsData.release_date}</div>
            {/if}
          </div>
        </div>
      {:else}
        <div style="padding: 20px; text-align: center; color: #64748b;">
          No hay créditos detallados disponibles para esta pista.
        </div>
      {/if}
    </div>
  </div>
{/if}

<!-- STORAGE & DISKS MANAGER MODAL -->
{#if showStorageModal}
  <div 
    style="position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(10px); display: flex; align-items: center; justify-content: center; z-index: 220; padding: 20px;"
    on:click={() => showStorageModal = false}
    on:keydown={(e) => { if (e.key === 'Escape') showStorageModal = false; }}
    role="dialog"
    tabindex="-1"
    aria-label="Gestor de almacenamiento y discos"
  >
    <div 
      style="background: #141722; width: 100%; max-width: 580px; border-radius: 20px; border: 1px solid #252c3f; padding: 28px; box-shadow: 0 24px 70px rgba(0,0,0,0.85); max-height: 90vh; overflow-y: auto;"
      on:click={(e) => e.stopPropagation()}
      on:keydown={() => {}}
      role="document"
      tabindex="-1"
    >
      <!-- HEADER -->
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <div style="width: 44px; height: 44px; border-radius: 12px; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); display: flex; align-items: center; justify-content: center;">
            <HardDrive size={22} color="#3b82f6" />
          </div>
          <div>
            <span style="font-size: 0.72rem; color: #60a5fa; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;">Configuración del Sistema</span>
            <h3 style="font-size: 1.35rem; font-weight: 800; margin-top: 2px;">Gestor de Discos & Almacenamiento</h3>
          </div>
        </div>
        <button 
          type="button"
          on:click={() => showStorageModal = false}
          style="background: #1c2130; border: none; color: #94a3b8; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.15s;"
          class="hover:text-white hover:bg-[#283045]"
        >
          <X size={18} />
        </button>
      </div>

      <p style="color: #94a3b8; font-size: 0.85rem; line-height: 1.5; margin-bottom: 20px;">
        Elige en qué disco duro deseas que Tono guarde tus canciones para reproducción sin conexión y memoria caché de alto rendimiento.
      </p>

      <!-- DETECTED DRIVES LIST -->
      <div style="display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px;">
        <div style="font-size: 0.76rem; color: #64748b; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px;">
          Discos Detectados ({drivesData.drives.length})
        </div>

        {#each drivesData.drives as d}
          <button 
            type="button"
            on:click={() => selectedDrive = d}
            style="display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; border-radius: 12px; border: 2px solid {selectedDrive?.letter === d.letter ? '#3b82f6' : '#22283a'}; background: {selectedDrive?.letter === d.letter ? 'rgba(59, 130, 246, 0.08)' : '#0d1017'}; text-align: left; cursor: pointer; transition: all 0.2s;"
            class="hover:border-blue-400"
          >
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <div style="display: flex; align-items: center; gap: 10px;">
                <HardDrive size={18} color={selectedDrive?.letter === d.letter ? '#3b82f6' : '#64748b'} />
                <div>
                  <div style="font-weight: 700; font-size: 0.95rem; color: #fff;">{d.name}</div>
                  <div style="font-size: 0.74rem; color: #64748b;">Ruta: {d.path}</div>
                </div>
              </div>
              
              <div style="display: flex; align-items: center; gap: 8px;">
                {#if d.is_recommended}
                  <span style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 0.68rem; font-weight: 800; padding: 3px 8px; border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    Recomendado
                  </span>
                {/if}
                {#if d.is_active}
                  <span style="background: rgba(59, 130, 246, 0.2); color: #60a5fa; font-size: 0.68rem; font-weight: 800; padding: 3px 8px; border-radius: 6px; border: 1px solid rgba(59, 130, 246, 0.4);">
                    En Uso
                  </span>
                {/if}
              </div>
            </div>

            <!-- STORAGE USAGE PROGRESS BAR -->
            <div style="margin-top: 4px;">
              <div style="display: flex; justify-content: space-between; font-size: 0.74rem; color: #94a3b8; margin-bottom: 4px;">
                <span style="color: #60a5fa; font-weight: 700;">{d.free_gb} GB libres</span>
                <span>{d.used_gb} GB usados de {d.total_gb} GB ({d.percent_used}%)</span>
              </div>
              <div style="width: 100%; height: 6px; background: #1c2233; border-radius: 3px; overflow: hidden;">
                <div style="height: 100%; width: {d.percent_used}%; background: {d.percent_used > 88 ? '#ef4444' : '#3b82f6'}; border-radius: 3px;"></div>
              </div>
            </div>
          </button>
        {/each}
      </div>

      <!-- FOLDER SETTINGS -->
      <div style="margin-bottom: 24px;">
        <label for="storage-folder-input" style="display: block; font-size: 0.76rem; color: #64748b; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px;">
          Carpeta de Almacenamiento
        </label>
        <div style="display: flex; align-items: center; gap: 8px; background: #0d1017; border: 1px solid #23283a; border-radius: 10px; padding: 8px 14px;">
          <Folder size={18} color="#60a5fa" />
          <span style="color: #64748b; font-family: monospace; font-size: 0.86rem;">{selectedDrive ? selectedDrive.path : 'D:\\'}</span>
          <input 
            id="storage-folder-input"
            type="text" 
            bind:value={customFolderName} 
            placeholder="Tono_Music" 
            style="flex: 1; background: transparent; border: none; color: #fff; font-family: monospace; font-size: 0.86rem; outline: none;"
          />
        </div>
        <p style="font-size: 0.72rem; color: #64748b; margin-top: 6px;">
          Ruta final completa: <span style="color: #94a3b8; font-family: monospace;">{selectedDrive ? `${selectedDrive.path}${customFolderName || 'Tono_Music'}` : '...'}</span>
        </p>
      </div>

      <!-- CURRENT CACHE STATS -->
      <div style="padding: 12px 16px; background: rgba(255, 255, 255, 0.03); border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.06); display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
        <div>
          <div style="font-size: 0.72rem; color: #64748b; font-weight: 700; text-transform: uppercase;">Estado de la Caché</div>
          <div style="font-size: 0.95rem; font-weight: 800; color: #fff; margin-top: 2px;">
            {storageStats.cached_tracks_count || 0} canciones almacenadas ({storageStats.cache_size_mb || 0} MB)
          </div>
        </div>
        <div style="font-size: 0.75rem; color: #34d399; font-weight: 700; display: flex; align-items: center; gap: 6px;">
          <Check size={16} /> Listo para Offline
        </div>
      </div>

      <!-- STATUS MESSAGE -->
      {#if storageMessage}
        <div style="padding: 10px 14px; border-radius: 8px; font-size: 0.82rem; font-weight: 700; margin-bottom: 16px; text-align: center; background: {storageMessage.startsWith('Error') ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)'}; color: {storageMessage.startsWith('Error') ? '#f87171' : '#34d399'}; border: 1px solid {storageMessage.startsWith('Error') ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)'};">
          {storageMessage}
        </div>
      {/if}

      <!-- ACTIONS -->
      <div style="display: flex; justify-content: flex-end; gap: 12px;">
        <button 
          type="button"
          on:click={() => showStorageModal = false}
          style="padding: 10px 18px; border-radius: 8px; background: #1c2130; border: none; color: #94a3b8; font-weight: 700; font-size: 0.85rem; cursor: pointer; transition: all 0.15s;"
          class="hover:bg-[#283045] hover:text-white"
        >
          Cerrar
        </button>
        <button 
          type="button"
          on:click={saveStorageConfig}
          disabled={isSavingStorage}
          style="padding: 10px 22px; border-radius: 8px; background: #3b82f6; border: none; color: #fff; font-weight: 800; font-size: 0.85rem; cursor: pointer; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4); transition: transform 0.15s;"
          class="hover:scale-105"
        >
          {#if isSavingStorage}
            <Disc size={16} class="animate-spin" /> Guardando...
          {:else}
            <Check size={16} /> Aplicar Disco & Carpeta
          {/if}
        </button>
      </div>

    </div>
  </div>
{/if}

<!-- ADD TO PLAYLIST MODAL -->
{#if showAddToPlaylistModal && trackToAddToPlaylist}
  <div 
    style="position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(10px); display: flex; align-items: center; justify-content: center; z-index: 230; padding: 20px;"
    on:click={() => showAddToPlaylistModal = false}
    on:keydown={(e) => { if (e.key === 'Escape') showAddToPlaylistModal = false; }}
    role="dialog"
    tabindex="-1"
    aria-label="Añadir a playlist"
  >
    <div 
      style="background: #141722; width: 100%; max-width: 480px; border-radius: 20px; border: 1px solid #252c3f; padding: 26px; box-shadow: 0 24px 70px rgba(0,0,0,0.85); max-height: 85vh; overflow-y: auto;"
      on:click={(e) => e.stopPropagation()}
      on:keydown={() => {}}
      role="document"
      tabindex="-1"
    >
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px;">
        <div>
          <span style="font-size: 0.72rem; color: #60a5fa; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;">Colecciones</span>
          <h3 style="font-size: 1.3rem; font-weight: 800; margin-top: 2px;">Añadir a Playlist</h3>
        </div>
        <button 
          type="button"
          on:click={() => showAddToPlaylistModal = false}
          style="background: #1c2130; border: none; color: #94a3b8; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer;"
        >
          <X size={16} />
        </button>
      </div>

      <!-- TRACK MINI PREVIEW -->
      <div style="display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: #0c0e15; border-radius: 10px; margin-bottom: 20px; border: 1px solid #1f2538;">
        <img src={trackToAddToPlaylist.thumbnail} alt="" style="width: 42px; height: 42px; border-radius: 6px; object-fit: cover;" />
        <div style="overflow: hidden;">
          <div style="font-weight: 700; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{trackToAddToPlaylist.title}</div>
          <div style="font-size: 0.75rem; color: #94a3b8;">{trackToAddToPlaylist.artist}</div>
        </div>
      </div>

      <!-- CREATE NEW PLAYLIST INLINE -->
      <div style="display: flex; gap: 8px; margin-bottom: 20px;">
        <input 
          type="text" 
          bind:value={newPlaylistInput}
          placeholder="Nombre de nueva playlist..." 
          on:keydown={(e) => { if (e.key === 'Enter') createAndAddToPlaylist(); }}
          style="flex: 1; background: #0c0e15; border: 1px solid #23283a; border-radius: 8px; padding: 8px 14px; color: #fff; font-size: 0.85rem; outline: none;"
        />
        <button 
          type="button"
          on:click={createAndAddToPlaylist}
          disabled={!newPlaylistInput.trim()}
          style="padding: 8px 14px; border-radius: 8px; background: #3b82f6; border: none; color: #fff; font-weight: 700; font-size: 0.82rem; cursor: pointer; display: flex; align-items: center; gap: 6px;"
        >
          <Plus size={16} /> Crear
        </button>
      </div>

      <!-- USER PLAYLISTS LIST -->
      <div style="font-size: 0.74rem; color: #64748b; font-weight: 800; text-transform: uppercase; margin-bottom: 8px;">Tus Playlists ({playlists.length})</div>
      <div style="display: flex; flex-direction: column; gap: 8px; max-height: 250px; overflow-y: auto;">
        {#if playlists.length === 0}
          <div style="padding: 16px; text-align: center; color: #64748b; font-size: 0.85rem;">
            Aún no has creado ninguna playlist. Escribe un nombre arriba para crear tu primera lista.
          </div>
        {:else}
          {#each playlists as pl}
            <button 
              type="button"
              on:click={() => addTrackToSelectedPlaylist(pl.id, pl.name)}
              style="display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; background: #0c0e15; border: 1px solid #1f2538; border-radius: 10px; cursor: pointer; text-align: left; transition: all 0.15s; width: 100%;"
              class="hover:border-blue-500 hover:bg-[#151926]"
            >
              <div style="display: flex; align-items: center; gap: 10px;">
                <ListMusic size={18} color="#60a5fa" />
                <span style="font-weight: 700; font-size: 0.88rem; color: #fff;">{pl.name}</span>
              </div>
              <span style="font-size: 0.75rem; color: #3b82f6; font-weight: 700; display: flex; align-items: center; gap: 4px;">
                <Plus size={14} /> Añadir
              </span>
            </button>
          {/each}
        {/if}
      </div>

    </div>
  </div>
{/if}

<!-- SPOTIFY AUDIO ENHANCER & EQUALIZER MODAL -->
{#if showAudioSettingsModal}
  <div 
    style="position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(10px); display: flex; align-items: center; justify-content: center; z-index: 230; padding: 20px;"
    on:click={() => showAudioSettingsModal = false}
    on:keydown={(e) => { if (e.key === 'Escape') showAudioSettingsModal = false; }}
    role="dialog"
    tabindex="-1"
    aria-label="Ajustes de audio"
  >
    <div 
      style="background: #141722; width: 100%; max-width: 500px; border-radius: 20px; border: 1px solid #252c3f; padding: 28px; box-shadow: 0 24px 70px rgba(0,0,0,0.85);"
      on:click={(e) => e.stopPropagation()}
      on:keydown={() => {}}
      role="document"
      tabindex="-1"
    >
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 22px;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <div style="width: 44px; height: 44px; border-radius: 12px; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); display: flex; align-items: center; justify-content: center;">
            <SlidersHorizontal size={22} color="#3b82f6" />
          </div>
          <div>
            <span style="font-size: 0.72rem; color: #60a5fa; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;">Motor de Sonido</span>
            <h3 style="font-size: 1.35rem; font-weight: 800; margin-top: 2px;">Mejoras de Audio</h3>
          </div>
        </div>
        <button 
          type="button"
          on:click={() => showAudioSettingsModal = false}
          style="background: #1c2130; border: none; color: #94a3b8; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer;"
        >
          <X size={18} />
        </button>
      </div>

      <!-- VELOCIDAD DE REPRODUCCIÓN -->
      <div style="padding: 16px; background: #0c0e15; border-radius: 12px; border: 1px solid #1f2538; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 800; font-size: 0.92rem; color: #fff;">Velocidad de reproducción</span>
          <span style="font-size: 0.8rem; color: #60a5fa; font-weight: 700;">{playbackSpeed}x</span>
        </div>
        <p style="font-size: 0.74rem; color: #94a3b8; margin-bottom: 12px;">Ajusta la velocidad de reproducción sin alterar el tono.</p>
        <div style="display: flex; gap: 8px;">
          {#each [0.75, 1.0, 1.25, 1.5, 2.0] as spd}
            <button 
              type="button"
              on:click={() => setPlaybackSpeed(spd)}
              style="flex: 1; padding: 7px 0; border-radius: 8px; font-size: 0.8rem; font-weight: 800; border: none; cursor: pointer; background: {playbackSpeed === spd ? '#3b82f6' : '#1c2130'}; color: {playbackSpeed === spd ? '#fff' : '#94a3b8'}; transition: all 0.15s;"
            >
              {spd === 1.0 ? '1x' : `${spd}x`}
            </button>
          {/each}
        </div>
      </div>

      <!-- TEMPORIZADOR DE APAGADO (SLEEP TIMER) -->
      <div style="padding: 16px; background: #0c0e15; border-radius: 12px; border: 1px solid #1f2538; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 800; font-size: 0.92rem; color: #fff;">Temporizador de apagado</span>
          {#if sleepTimerRemaining > 0}
            <span style="font-size: 0.8rem; color: #3b82f6; font-weight: 800;">
              {Math.floor(sleepTimerRemaining / 60)}:{sleepTimerRemaining % 60 < 10 ? '0' : ''}{sleepTimerRemaining % 60}
            </span>
          {:else if sleepTimerMinutes === 'end'}
            <span style="font-size: 0.8rem; color: #3b82f6; font-weight: 800;">Fin de canción</span>
          {:else}
            <span style="font-size: 0.8rem; color: #64748b; font-weight: 700;">Desactivado</span>
          {/if}
        </div>
        <p style="font-size: 0.74rem; color: #94a3b8; margin-bottom: 12px;">Detiene automáticamente la reproducción al terminar.</p>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">
          <button 
            type="button"
            on:click={() => setSleepTimer(0)}
            style="padding: 7px 0; border-radius: 8px; font-size: 0.78rem; font-weight: 700; border: none; cursor: pointer; background: {sleepTimerMinutes === 0 ? '#3b82f6' : '#1c2130'}; color: {sleepTimerMinutes === 0 ? '#fff' : '#94a3b8'};"
          >
            Off
          </button>
          <button 
            type="button"
            on:click={() => setSleepTimer(15)}
            style="padding: 7px 0; border-radius: 8px; font-size: 0.78rem; font-weight: 700; border: none; cursor: pointer; background: {sleepTimerMinutes === 15 ? '#3b82f6' : '#1c2130'}; color: {sleepTimerMinutes === 15 ? '#fff' : '#94a3b8'};"
          >
            15m
          </button>
          <button 
            type="button"
            on:click={() => setSleepTimer(30)}
            style="padding: 7px 0; border-radius: 8px; font-size: 0.78rem; font-weight: 700; border: none; cursor: pointer; background: {sleepTimerMinutes === 30 ? '#3b82f6' : '#1c2130'}; color: {sleepTimerMinutes === 30 ? '#fff' : '#94a3b8'};"
          >
            30m
          </button>
          <button 
            type="button"
            on:click={() => setSleepTimer(45)}
            style="padding: 7px 0; border-radius: 8px; font-size: 0.78rem; font-weight: 700; border: none; cursor: pointer; background: {sleepTimerMinutes === 45 ? '#3b82f6' : '#1c2130'}; color: {sleepTimerMinutes === 45 ? '#fff' : '#94a3b8'};"
          >
            45m
          </button>
          <button 
            type="button"
            on:click={() => setSleepTimer(60)}
            style="padding: 7px 0; border-radius: 8px; font-size: 0.78rem; font-weight: 700; border: none; cursor: pointer; background: {sleepTimerMinutes === 60 ? '#3b82f6' : '#1c2130'}; color: {sleepTimerMinutes === 60 ? '#fff' : '#94a3b8'};"
          >
            1h
          </button>
          <button 
            type="button"
            on:click={() => setSleepTimer('end')}
            style="padding: 7px 0; border-radius: 8px; font-size: 0.78rem; font-weight: 700; border: none; cursor: pointer; background: {sleepTimerMinutes === 'end' ? '#3b82f6' : '#1c2130'}; color: {sleepTimerMinutes === 'end' ? '#fff' : '#94a3b8'};"
          >
            Fin pista
          </button>
        </div>
      </div>

      <!-- CROSSFADE SETTING -->
      <div style="padding: 16px; background: #0c0e15; border-radius: 12px; border: 1px solid #1f2538; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-weight: 800; font-size: 0.92rem; color: #fff;">Crossfade entre canciones</span>
          <span style="font-size: 0.8rem; color: #60a5fa; font-weight: 700;">{crossfadeSeconds} segundos</span>
        </div>
        <p style="font-size: 0.74rem; color: #94a3b8; margin-bottom: 12px;">Transición fluida sin silencios entre canciones.</p>
        <input 
          type="range" 
          min="0" 
          max="12" 
          bind:value={crossfadeSeconds} 
          style="width: 100%; accent-color: #3b82f6;"
        />
      </div>

      <!-- RESET AUDIO BUTTON -->
      <div style="padding: 14px 16px; background: #0c0e15; border-radius: 12px; border: 1px solid #1f2538; display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;">
        <div>
          <div style="font-weight: 700; font-size: 0.88rem; color: #fff;">Restablecer Salida de Audio</div>
          <div style="font-size: 0.73rem; color: #94a3b8; margin-top: 2px;">Recarga el hardware de sonido nativo si se corta.</div>
        </div>
        <button 
          type="button"
          on:click={resetAudioOutput}
          style="padding: 8px 14px; border-radius: 8px; background: #1c2130; border: 1px solid #2f3952; color: #fff; font-size: 0.78rem; font-weight: 700; cursor: pointer;"
          class="hover:bg-[#283045]"
        >
          Restablecer
        </button>
      </div>

      <!-- AUDIO QUALITY BADGE -->
      <div style="padding: 12px 16px; background: rgba(59, 130, 246, 0.08); border-radius: 10px; border: 1px solid rgba(59, 130, 246, 0.25); display: flex; align-items: center; justify-content: space-between;">
        <div style="font-size: 0.8rem; color: #94a3b8;">Salida de Audio:</div>
        <div style="font-size: 0.85rem; font-weight: 800; color: #60a5fa; display: flex; align-items: center; gap: 6px;">
          <Sparkles size={16} color="#3b82f6" /> Master Hi-Fi Directo (Opus / MP3)
        </div>
      </div>

      <div style="margin-top: 20px; display: flex; justify-content: flex-end;">
        <button 
          type="button" 
          on:click={() => showAudioSettingsModal = false}
          style="padding: 10px 20px; border-radius: 8px; background: #3b82f6; border: none; color: #fff; font-weight: 800; font-size: 0.85rem; cursor: pointer;"
        >
          Listo
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- SPOTIFY-STYLE QUEUE DRAWER -->
{#if showQueueDrawer}
  <div 
    style="position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 140;"
    on:click={() => showQueueDrawer = false}
    on:keydown={(e) => { if (e.key === 'Escape') showQueueDrawer = false; }}
    role="dialog"
    tabindex="-1"
    aria-label="Cerrar cola"
  ></div>

  <aside 
    style="position: fixed; right: 0; top: 0; bottom: 90px; width: 380px; max-width: 90vw; background: #0c0e15; border-left: 1px solid #1c2233; z-index: 150; box-shadow: -12px 0 40px rgba(0,0,0,0.85); display: flex; flex-direction: column; padding: 22px; overflow-y: auto;"
    role="complementary"
    aria-label="Cola de reproducción"
  >
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <ListMusic size={20} color="#3b82f6" />
        <h3 style="font-size: 1.2rem; font-weight: 800;">Cola de Reproducción</h3>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        {#if queue.length > 1}
          <button 
            type="button"
            on:click={clearQueue}
            style="background: transparent; border: 1px solid #23283a; color: #94a3b8; font-size: 0.74rem; font-weight: 700; padding: 5px 10px; border-radius: 6px; cursor: pointer;"
            class="hover:text-white hover:border-red-400"
          >
            Vaciar
          </button>
        {/if}
        <button 
          type="button"
          on:click={() => showQueueDrawer = false}
          style="background: #161924; border: none; color: #94a3b8; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer;"
        >
          <X size={16} />
        </button>
      </div>
    </div>

    <!-- CURRENT TRACK IN QUEUE -->
    {#if currentTrack}
      <div style="margin-bottom: 24px;">
        <div style="font-size: 0.72rem; color: #64748b; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px;">
          Reproduciendo Ahora
        </div>
        <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 12px;">
          <img src={currentTrack.thumbnail} alt="" style="width: 48px; height: 48px; border-radius: 8px; object-fit: cover;" />
          <div style="flex: 1; overflow: hidden;">
            <div style="font-weight: 800; font-size: 0.9rem; color: #60a5fa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
              {currentTrack.title}
            </div>
            <div style="font-size: 0.76rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
              {currentTrack.artist}
            </div>
          </div>
          <!-- Bouncing equalizer bars -->
          <div class="equalizer-bars {isPlaying ? 'playing' : ''}">
            <span class="bar"></span>
            <span class="bar"></span>
            <span class="bar"></span>
            <span class="bar"></span>
          </div>
        </div>
      </div>
    {/if}

    <!-- UP NEXT IN QUEUE -->
    <div style="flex: 1; display: flex; flex-direction: column;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <span style="font-size: 0.72rem; color: #64748b; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px;">
          A continuación ({Math.max(0, queue.length - (queueIndex + 1))})
        </span>
      </div>

      {#if queue.length <= 1 || queueIndex >= queue.length - 1}
        <div style="padding: 24px 12px; text-align: center; color: #64748b; font-size: 0.82rem; background: #090a0f; border-radius: 10px; border: 1px dashed #1c2233;">
          No hay más canciones en espera.<br>Explora o busca pistas para agregarlas a la cola.
        </div>
      {:else}
        <div style="display: flex; flex-direction: column; gap: 6px; overflow-y: auto;">
          {#each queue.slice(queueIndex + 1) as t, i}
            <div 
              role="button"
              tabindex="0"
              on:click={() => playTrack(t, queue, queueIndex + 1 + i)}
              on:keydown={(e) => { if (e.key === 'Enter') playTrack(t, queue, queueIndex + 1 + i); }}
              style="display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px; cursor: pointer; transition: background 0.15s; background: #0f121a;"
              class="hover:bg-[#1a2030]"
            >
              <span style="font-size: 0.74rem; color: #64748b; min-width: 16px;">{i + 1}</span>
              <img src={t.thumbnail} alt="" style="width: 38px; height: 38px; border-radius: 6px; object-fit: cover;" />
              <div style="flex: 1; overflow: hidden;">
                <div style="font-weight: 700; font-size: 0.84rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #fff;">
                  {t.title}
                </div>
                <div style="font-size: 0.72rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                  {t.artist}
                </div>
              </div>
              <button 
                type="button"
                on:click={(e) => removeFromQueue(queueIndex + 1 + i, e)}
                style="background: transparent; border: none; color: #64748b; padding: 4px; cursor: pointer;"
                class="hover:text-red-400"
                title="Quitar de la cola"
              >
                <X size={14} />
              </button>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </aside>
{/if}

<!-- SPOTIFY-STYLE FULLSCREEN IMMERSIVE CANVAS MODE -->
{#if showFullscreenMode && currentTrack}
  <div 
    style="position: fixed; inset: 0; z-index: 300; background: radial-gradient(circle at 50% 30%, #1e293b 0%, #06070a 100%); display: flex; flex-direction: column; justify-content: space-between; padding: 40px; color: #fff; overflow-y: auto;"
    role="dialog"
    tabindex="-1"
    aria-label="Reproductor en pantalla completa"
  >
    <!-- TOP HEADER -->
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <div style="width: 32px; height: 32px; border-radius: 8px; background: #3b82f6; display: flex; align-items: center; justify-content: center;">
          <Disc3 size={18} color="#fff" />
        </div>
        <span style="font-weight: 800; letter-spacing: -0.5px; font-size: 1.1rem;">Tono Inmersivo</span>
      </div>

      <div style="display: flex; align-items: center; gap: 16px;">
        <button 
          type="button"
          on:click={() => showAudioSettingsModal = true}
          style="padding: 8px 16px; border-radius: 500px; background: rgba(255,255,255,0.1); border: none; color: #fff; font-size: 0.8rem; font-weight: 800; cursor: pointer; display: flex; align-items: center; gap: 6px;"
          class="hover:bg-white hover:text-black"
        >
          <SlidersHorizontal size={16} /> {playbackSpeed !== 1.0 ? `${playbackSpeed}x` : 'Ajustes'}
        </button>
        <button 
          type="button"
          on:click={() => showFullscreenMode = false}
          style="width: 44px; height: 44px; border-radius: 50%; background: rgba(255,255,255,0.1); border: none; color: #fff; display: flex; align-items: center; justify-content: center; cursor: pointer;"
          class="hover:bg-white hover:text-black"
          title="Salir de pantalla completa (Esc)"
        >
          <Minimize2 size={20} />
        </button>
      </div>
    </div>

    <!-- CENTER HERO: ARTWORK + REAL-TIME SYNCHRONIZED LYRICS -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 60px; max-width: 1200px; width: 100%; margin: 20px auto; align-items: center;">
      <!-- ARTWORK WITH GLOW -->
      <div style="display: flex; flex-direction: column; align-items: center; text-align: center;">
        <div style="position: relative; width: 380px; height: 380px; max-width: 75vw; max-height: 75vw;">
          <img 
            src={currentTrack.thumbnail} 
            alt={currentTrack.title} 
            style="width: 100%; height: 100%; border-radius: 20px; object-fit: cover; box-shadow: 0 20px 60px rgba(0,0,0,0.85); {isPlaying ? 'animation: vinylPulse 4s ease-in-out infinite alternate;' : ''}"
          />
        </div>
        <div style="margin-top: 24px;">
          <h2 style="font-size: 2rem; font-weight: 900; letter-spacing: -0.5px; line-height: 1.2;">{currentTrack.title}</h2>
          <p style="font-size: 1.15rem; color: #94a3b8; font-weight: 700; margin-top: 6px;">{currentTrack.artist}</p>
        </div>
      </div>

      <!-- LYRICS STREAM -->
      <div style="height: 420px; overflow-y: auto; padding-right: 16px; mask-image: linear-gradient(180deg, transparent 0%, black 15%, black 85%, transparent 100%); display: flex; flex-direction: column; gap: 14px;">
        {#if lyricsData && lyricsData.is_synced && lyricsData.synced?.length > 0}
          {#each lyricsData.synced as line, i}
            <div 
              style="font-size: {currentLyricIndex === i ? '2.1rem' : '1.4rem'}; font-weight: 800; line-height: 1.35; color: {currentLyricIndex === i ? '#ffffff' : 'rgba(255,255,255,0.25)'}; transition: all 0.25s; text-shadow: {currentLyricIndex === i ? '0 0 30px rgba(59,130,246,0.8)' : 'none'};"
            >
              {line.text}
            </div>
          {/each}
        {:else if lyricsData && lyricsData.plain}
          <div style="font-size: 1.3rem; line-height: 1.8; color: #94a3b8; font-weight: 600; white-space: pre-wrap;">
            {lyricsData.plain}
          </div>
        {:else}
          <div style="height: 100%; display: flex; align-items: center; justify-content: center; color: #64748b; font-size: 1.1rem;">
            Disfrutando de "{currentTrack.title}" de {currentTrack.artist}
          </div>
        {/if}
      </div>
    </div>

    <!-- BOTTOM CONTROLS IN FULLSCREEN -->
    <div style="max-width: 800px; width: 100%; margin: 0 auto;">
      <!-- PROGRESS BAR -->
      <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 16px; font-size: 0.85rem; color: #94a3b8;">
        <span>{formatSeconds(currentTime)}</span>
        <input 
          type="range" 
          min="0" 
          max={duration || 100} 
          value={currentTime} 
          on:input={handleSeek}
          style="width: 100%; accent-color: #3b82f6; height: 6px;"
        />
        <span>{formatSeconds(duration)}</span>
      </div>

      <!-- PLAYBACK BUTTONS -->
      <div style="display: flex; align-items: center; justify-content: center; gap: 28px;">
        <button type="button" on:click={() => isShuffle = !isShuffle} style="background: transparent; border: none; cursor: pointer; color: {isShuffle ? '#3b82f6' : '#64748b'};">
          <Shuffle size={22} />
        </button>
        <button type="button" on:click={playPrev} style="background: transparent; border: none; cursor: pointer; color: #fff;">
          <SkipBack size={26} fill="#fff" />
        </button>
        <button 
          type="button" 
          on:click={togglePlay} 
          style="width: 58px; height: 58px; border-radius: 50%; background: #ffffff; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 0 25px rgba(255,255,255,0.35);"
          class="hover:scale-105"
        >
          {#if isPlaying}
            <Pause size={28} color="#000" fill="#000" />
          {:else}
            <Play size={28} color="#000" fill="#000" style="margin-left: 2px;" />
          {/if}
        </button>
        <button type="button" on:click={playNext} style="background: transparent; border: none; cursor: pointer; color: #fff;">
          <SkipForward size={26} fill="#fff" />
        </button>
        <button type="button" on:click={cycleRepeat} style="background: transparent; border: none; cursor: pointer; color: {repeatMode > 0 ? '#3b82f6' : '#64748b'};">
          <Repeat size={22} />
        </button>
      </div>
    </div>

  </div>
{/if}

<!-- FLOATING TOAST NOTIFICATION -->
{#if toastMessage}
  <div 
    style="position: fixed; bottom: 105px; left: 50%; transform: translateX(-50%); background: rgba(18, 22, 34, 0.95); backdrop-filter: blur(14px); border: 1px solid rgba(59, 130, 246, 0.4); color: #fff; padding: 10px 22px; border-radius: 500px; font-weight: 700; font-size: 0.85rem; box-shadow: 0 10px 30px rgba(0,0,0,0.6); z-index: 250; display: flex; align-items: center; gap: 8px;"
  >
    <Sparkles size={16} color="#60a5fa" />
    <span>{toastMessage}</span>
  </div>
{/if}

<div style="display: flex; height: 100vh; width: 100vw; background: #090a0f; color: #fff;">
  
  <!-- LEFT SIDEBAR -->
  <aside style="width: 270px; min-width: 270px; background: #10121a; display: flex; flex-direction: column; padding: 14px; gap: 10px; border-right: 1px solid #1a1e2b; height: calc(100vh - 90px);">
    
    <!-- TONO BRAND LOGO -->
    <div style="display: flex; align-items: center; gap: 12px; padding: 10px 12px; margin-bottom: 4px;">
      <!-- Custom Tono Acoustic Wave Logo -->
      <div style="width: 38px; height: 38px; border-radius: 10px; background: #3b82f6; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 20px rgba(59, 130, 246, 0.45);">
        <svg width="22" height="22" viewBox="0 0 32 32" fill="none">
          <path d="M16 5v22M11 9v14M21 9v14M6 13v6M26 13v6" stroke="#ffffff" stroke-width="2.8" stroke-linecap="round"/>
        </svg>
      </div>
      <div>
        <h1 style="font-size: 1.35rem; font-weight: 800; letter-spacing: -0.6px; line-height: 1;">Tono</h1>
        <span style="font-size: 0.68rem; color: #60a5fa; font-weight: 600; letter-spacing: 0.5px;">AUDIO VAULT</span>
      </div>
    </div>

    <!-- MAIN NAV -->
    <div style="background: #151822; border-radius: 10px; padding: 8px; border: 1px solid #1e2333;">
      <button 
        on:click={() => activeTab = 'home'}
        style="width: 100%; display: flex; align-items: center; gap: 14px; padding: 11px 14px; border: none; background: {activeTab === 'home' ? '#22283a' : 'transparent'}; color: {activeTab === 'home' ? '#fff' : '#94a3b8'}; font-weight: 700; border-radius: 7px; cursor: pointer; transition: all 0.15s;"
      >
        <Home size={20} color={activeTab === 'home' ? '#3b82f6' : 'currentColor'} />
        <span>Inicio</span>
      </button>

      <button 
        on:click={() => activeTab = 'search'}
        style="width: 100%; display: flex; align-items: center; gap: 14px; padding: 11px 14px; border: none; background: {activeTab === 'search' ? '#22283a' : 'transparent'}; color: {activeTab === 'search' ? '#fff' : '#94a3b8'}; font-weight: 700; border-radius: 7px; cursor: pointer; transition: all 0.15s;"
      >
        <Search size={20} color={activeTab === 'search' ? '#3b82f6' : 'currentColor'} />
        <span>Explorar & Buscar</span>
      </button>

      <button 
        on:click={() => activeTab = 'lyrics'}
        style="width: 100%; display: flex; align-items: center; gap: 14px; padding: 11px 14px; border: none; background: {activeTab === 'lyrics' ? '#22283a' : 'transparent'}; color: {activeTab === 'lyrics' ? '#fff' : '#94a3b8'}; font-weight: 700; border-radius: 7px; cursor: pointer; transition: all 0.15s;"
      >
        <Mic2 size={20} color={activeTab === 'lyrics' ? '#3b82f6' : 'currentColor'} />
        <span>Modo Letras</span>
      </button>
    </div>

    <!-- LIBRARY SECTION -->
    <div style="background: #151822; border-radius: 10px; padding: 12px; flex: 1; display: flex; flex-direction: column; overflow: hidden; border: 1px solid #1e2333;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 2px 6px;">
        <div style="display: flex; align-items: center; gap: 8px; color: #94a3b8; font-weight: 700; font-size: 0.9rem;">
          <Library size={18} />
          <span>Tu Colección</span>
        </div>
        <button 
          on:click={() => activeTab = 'library'}
          style="background: transparent; border: none; color: #94a3b8; cursor: pointer;"
          title="Ver colección completa"
        >
          <ListMusic size={18} />
        </button>
      </div>

      <!-- FAVORITES QUICK CARD -->
      <button 
        type="button"
        on:click={() => activeTab = 'library'}
        style="width: 100%; text-align: left; border: none; display: flex; align-items: center; gap: 12px; padding: 8px; border-radius: 8px; cursor: pointer; background: {activeTab === 'library' ? '#22283a' : 'transparent'}; color: #fff; transition: background 0.15s;"
      >
        <div style="width: 44px; height: 44px; border-radius: 8px; background: linear-gradient(135deg, #2563eb, #38bdf8); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
          <Heart size={20} color="#fff" fill="#fff" />
        </div>
        <div>
          <div style="font-weight: 700; font-size: 0.88rem;">Pistas Guardadas</div>
          <div style="font-size: 0.74rem; color: #94a3b8;">{favorites.length} canciones</div>
        </div>
      </button>

      <!-- PLAYLISTS LIST -->
      <div style="flex: 1; overflow-y: auto; margin-top: 10px; display: flex; flex-direction: column; gap: 3px;">
        {#each playlists as pl}
          <div style="padding: 7px 8px; border-radius: 6px; font-size: 0.83rem; color: #94a3b8; cursor: pointer;">
            {pl.name}
          </div>
        {/each}
      </div>

      <!-- STORAGE HEALTH WIDGET (DRIVE SELECTOR) -->
      <button 
        type="button"
        on:click={openStorageModal}
        style="margin-top: auto; padding: 10px 12px; background: #0c0e14; border-radius: 8px; border: 1px solid #1c2233; font-size: 0.74rem; text-align: left; cursor: pointer; transition: all 0.2s; width: 100%; display: block;"
        class="hover:border-blue-500 hover:bg-[#121622]"
      >
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
          <span style="color: #94a3b8; display: flex; align-items: center; gap: 6px;">
            <HardDrive size={14} color="#3b82f6" /> {storageStats.storage || 'Almacenamiento'}:
          </span>
          <span style="color: #60a5fa; font-weight: 700;">{storageStats.free_gb || 0} GB libres</span>
        </div>
        <div style="color: #64748b; font-size: 0.69rem; display: flex; align-items: center; justify-content: space-between;">
          <span>{storageStats.cached_tracks_count || 0} pistas ({storageStats.cache_size_mb || 0} MB)</span>
          <span style="color: #3b82f6; font-weight: 700;">Cambiar disco ⚙</span>
        </div>
      </button>
    </div>
  </aside>

  <!-- MAIN VIEWPORT -->
  <main style="flex: 1; display: flex; flex-direction: column; height: calc(100vh - 90px); overflow-y: auto; background: linear-gradient(180deg, #131724 0%, #090a0f 260px); position: relative;">
    
    <!-- TOP SEARCH / APP BAR -->
    <header style="padding: 16px 32px; display: flex; align-items: center; justify-content: space-between; gap: 20px; sticky: top; z-index: 20; background: rgba(9, 10, 15, 0.75); backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
      <!-- SEARCH INPUT BAR -->
      <div style="display: flex; align-items: center; gap: 12px; flex: 1; max-width: 520px; background: #151822; border-radius: 10px; padding: 9px 16px; border: 1px solid #23283a;">
        <Search size={18} color="#94a3b8" />
        <input 
          type="text" 
          placeholder="Busca por canción, artista o género..." 
          bind:value={searchQuery}
          on:input={handleSearchInput}
          on:focus={() => { if (activeTab !== 'search') activeTab = 'search'; }}
          style="background: transparent; border: none; color: #fff; width: 100%; font-size: 0.9rem; outline: none;"
        />
        {#if searchQuery}
          <button on:click={() => { searchQuery = ''; searchResults = []; }} style="background: transparent; border: none; color: #64748b; cursor: pointer; font-size: 0.8rem;">✕</button>
        {/if}
      </div>

      <!-- SOURCE TOGGLE (YOUTUBE MUSIC / SOUNDCLOUD) -->
      <div style="display: flex; align-items: center; gap: 8px;">
        <button 
          on:click={() => { searchSource = 'all'; if (searchQuery) performSearch(); }}
          style="padding: 7px 15px; border-radius: 8px; font-size: 0.8rem; font-weight: 700; border: none; cursor: pointer; background: {searchSource === 'all' ? '#3b82f6' : '#151822'}; color: {searchSource === 'all' ? '#fff' : '#94a3b8'}; transition: all 0.15s;"
        >
          Todo
        </button>
        <button 
          on:click={() => { searchSource = 'youtube'; if (searchQuery) performSearch(); }}
          style="padding: 7px 15px; border-radius: 8px; font-size: 0.8rem; font-weight: 700; border: none; cursor: pointer; background: {searchSource === 'youtube' ? '#3b82f6' : '#151822'}; color: {searchSource === 'youtube' ? '#fff' : '#94a3b8'}; transition: all 0.15s;"
        >
          Catálogo Oficial
        </button>
        <button 
          on:click={() => { searchSource = 'soundcloud'; if (searchQuery) performSearch(); }}
          style="padding: 7px 15px; border-radius: 8px; font-size: 0.8rem; font-weight: 700; border: none; cursor: pointer; background: {searchSource === 'soundcloud' ? '#3b82f6' : '#151822'}; color: {searchSource === 'soundcloud' ? '#fff' : '#94a3b8'}; transition: all 0.15s;"
        >
          SoundCloud & Remixes
        </button>
      </div>
    </header>

    <!-- CONTENT BODY -->
    <div style="padding: 24px 32px; flex: 1;">
      
      <!-- HOME TAB -->
      {#if activeTab === 'home'}
        <div>
          <!-- CONTEXTUAL DISCOVERY (FOR YOU) -->
          {#if forYouData && forYouData.tracks?.length > 0}
            <div style="margin-bottom: 40px; background: linear-gradient(180deg, rgba(24, 34, 56, 0.4) 0%, rgba(12, 16, 24, 0.2) 100%); border: 1px solid #1e2638; border-radius: 16px; padding: 24px;">
              <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 18px;">
                <div>
                  <div style="display: flex; align-items: center; gap: 6px; font-size: 0.76rem; font-weight: 800; color: #3b82f6; letter-spacing: 0.8px; text-transform: uppercase;">
                    <Sparkles size={14} /> Recomendado para ti
                  </div>
                  <h2 style="font-size: 1.8rem; font-weight: 900; letter-spacing: -0.8px; margin-top: 4px;">{forYouData.heading}</h2>
                </div>
                <button 
                  type="button"
                  on:click={() => startArtistRadio(forYouData.seed_artist)}
                  style="font-size: 0.82rem; color: #60a5fa; background: #1c2233; border: 1px solid #2e3852; padding: 8px 16px; border-radius: 500px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 8px;"
                  class="hover:border-blue-500"
                >
                  <Radio size={14} /> Iniciar Radio de {forYouData.seed_artist}
                </button>
              </div>

              <!-- FOR YOU TRACKS CARDS -->
              <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; margin-bottom: 22px;">
                {#each forYouData.tracks.slice(0, 6) as track}
                  <div 
                    role="row"
                    tabindex="0"
                    on:mouseenter={() => prefetchTrack(track)}
                    on:click={() => playTrack(track, forYouData.tracks)}
                    on:keydown={(e) => { if (e.key === 'Enter') playTrack(track, forYouData.tracks); }}
                    style="background: #11141e; border: 1px solid #1e2538; border-radius: 10px; display: flex; align-items: center; gap: 12px; cursor: pointer; overflow: hidden; text-align: left; padding: 0; color: #fff; transition: all 0.15s;"
                    class="hover:border-[#3b82f6] hover:bg-[#161b29]"
                  >
                    <img src={track.thumbnail} alt={track.title} style="width: 64px; height: 64px; object-fit: cover; flex-shrink: 0;" />
                    <div style="flex: 1; overflow: hidden; padding-right: 8px;">
                      <div style="font-weight: 700; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{track.title}</div>
                      <span 
                        on:click={(e) => openArtistProfile(track.artist, e)}
                        style="font-size: 0.76rem; color: #94a3b8; cursor: pointer;"
                        class="hover:underline"
                      >
                        {track.artist}
                      </span>
                    </div>
                    <div style="margin-right: 12px; width: 34px; height: 34px; border-radius: 50%; background: #3b82f6; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); flex-shrink: 0;">
                      <Play size={16} color="#fff" fill="#fff" style="margin-left: 2px;" />
                    </div>
                  </div>
                {/each}
              </div>

              <!-- SIMILAR ARTISTS ROW -->
              {#if forYouData.similar_artists?.length > 0}
                <div style="border-top: 1px solid #1e2638; padding-top: 18px;">
                  <div style="font-size: 0.8rem; font-weight: 800; color: #cbd5e1; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                    Artistas similares a {forYouData.seed_artist}:
                  </div>
                  <div style="display: flex; gap: 18px; overflow-x: auto; padding-bottom: 6px;">
                    {#each forYouData.similar_artists as sim}
                      <div 
                        on:click={() => openArtistProfile(sim.name)}
                        style="display: flex; flex-direction: column; align-items: center; gap: 8px; cursor: pointer; flex-shrink: 0; width: 95px; text-align: center;"
                        class="hover:scale-105 transition-transform"
                      >
                        <img src={sim.thumbnail} alt={sim.name} style="width: 72px; height: 72px; border-radius: 50%; object-fit: cover; border: 2px solid #273147;" />
                        <div style="font-weight: 700; font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%;">{sim.name}</div>
                        <div style="font-size: 0.68rem; color: #64748b;">{sim.subscribers || 'Similar'}</div>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
            </div>
          {/if}

          <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 24px;">
            <div>
              <span style="font-size: 0.78rem; font-weight: 700; color: #60a5fa; letter-spacing: 1px; text-transform: uppercase;">Descubre</span>
              <h2 style="font-size: 2.2rem; font-weight: 900; letter-spacing: -1px; margin-top: 4px;">Tendencias Principales</h2>
            </div>
            <span style="color: #94a3b8; font-size: 0.85rem;">Audio sin compresión de datos</span>
          </div>
          
          <!-- QUICK CARDS GRID -->
          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; margin-bottom: 36px;">
            {#each trendingTracks.slice(0, 6) as track}
              <div 
                role="row"
                tabindex="0"
                on:mouseenter={() => prefetchTrack(track)}
                on:click={() => playTrack(track, trendingTracks)}
                on:keydown={(e) => { if (e.key === 'Enter') playTrack(track, trendingTracks); }}
                style="background: #151822; border: 1px solid #1e2434; border-radius: 8px; display: flex; align-items: center; gap: 14px; cursor: pointer; overflow: hidden; text-align: left; padding: 0; color: #fff; transition: transform 0.15s, background 0.15s;"
                class="hover:bg-[#1c2233]"
              >
                <img src={track.thumbnail} alt={track.title} style="width: 68px; height: 68px; object-fit: cover; flex-shrink: 0;" />
                <div style="flex: 1; overflow: hidden; padding-right: 8px;">
                  <div style="font-weight: 700; font-size: 0.92rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{track.title}</div>
                  <span 
                    on:click={(e) => openArtistProfile(track.artist, e)}
                    style="font-size: 0.78rem; color: #94a3b8; cursor: pointer;"
                    class="hover:underline"
                  >
                    {track.artist}
                  </span>
                </div>
                <div style="margin-right: 14px; width: 38px; height: 38px; border-radius: 50%; background: #3b82f6; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); flex-shrink: 0;">
                  <Play size={18} color="#fff" fill="#fff" style="margin-left: 2px;" />
                </div>
              </div>
            {/each}
          </div>

          <!-- TRENDING SECTION -->
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;">
            <h3 style="font-size: 1.35rem; font-weight: 800; letter-spacing: -0.5px;">Más Escuchadas en Tono</h3>
            <span style="font-size: 0.8rem; color: #64748b;">Streaming directo en vivo</span>
          </div>

          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 18px;">
            {#each trendingTracks as track, idx}
              <div 
                role="button"
                tabindex="0"
                on:mouseenter={() => prefetchTrack(track)}
                on:click={() => playTrack(track, trendingTracks, idx)}
                on:keydown={(e) => { if (e.key === 'Enter') playTrack(track, trendingTracks, idx); }}
                style="background: #12151e; padding: 14px; border-radius: 10px; cursor: pointer; border: 1px solid #1c2130; text-align: left; color: #fff; transition: all 0.2s; position: relative;"
                class="hover:border-[#2f3952] hover:bg-[#161a26]"
              >
                <div style="position: relative; margin-bottom: 12px;">
                  <img src={track.thumbnail} alt={track.title} style="width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; box-shadow: 0 8px 20px rgba(0,0,0,0.4);" />
                  <div style="position: absolute; right: 8px; bottom: 8px; width: 42px; height: 42px; border-radius: 50%; background: #3b82f6; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 14px rgba(59, 130, 246, 0.45);">
                    <Play size={20} color="#fff" fill="#fff" style="margin-left: 2px;" />
                  </div>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 3px;">
                  <div style="font-weight: 700; font-size: 0.92rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{track.title}</div>
                  <button 
                    type="button" 
                    on:click={(e) => openAddToPlaylist(track, e)} 
                    style="background: transparent; border: none; color: #64748b; cursor: pointer; padding: 2px;" 
                    class="hover:text-white"
                    title="Añadir a playlist"
                  >
                    <Plus size={15} />
                  </button>
                </div>
                <div 
                  on:click={(e) => openArtistProfile(track.artist, e)}
                  style="font-size: 0.78rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;"
                  class="hover:underline"
                >
                  {track.artist}
                </div>
              </div>
            {/each}
          </div>
        </div>

      <!-- SEARCH TAB -->
      {:else if activeTab === 'search'}
        <div>
          {#if isSearching}
            <div style="display: flex; align-items: center; justify-content: center; height: 320px; color: #60a5fa; gap: 12px; font-weight: 600;">
              <Disc size={26} class="animate-spin" /> Buscando pistas y remixes en tiempo real...
            </div>
          {:else if searchResults.length > 0}
            {#if matchedArtist}
              <!-- SPOTIFY-STYLE TOP RESULT: ARTIST SPOTLIGHT CARD -->
              <div style="background: linear-gradient(135deg, #182238 0%, #0e121a 100%); border: 1px solid #293550; border-radius: 14px; padding: 22px 26px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 12px 36px rgba(0,0,0,0.4);">
                <div style="display: flex; align-items: center; gap: 20px;">
                  <img src={matchedArtist.thumbnail} alt={matchedArtist.name} style="width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 2px solid #3b82f6; box-shadow: 0 6px 20px rgba(0,0,0,0.5);" />
                  <div>
                    <div style="display: flex; align-items: center; gap: 6px; color: #60a5fa; font-size: 0.72rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;">
                      <Check size={14} /> Artista Oficial Coincidente
                    </div>
                    <h3 style="font-size: 1.8rem; font-weight: 900; letter-spacing: -0.5px; margin: 2px 0;">{matchedArtist.name}</h3>
                    <div style="color: #94a3b8; font-size: 0.82rem;">{matchedArtist.subscribers ? `${matchedArtist.subscribers} oyentes` : 'Explorar discografía y canciones similares'}</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                  <button 
                    type="button"
                    on:click={() => startArtistRadio(matchedArtist.name)}
                    style="padding: 10px 20px; border-radius: 500px; background: #3b82f6; border: none; color: #fff; font-weight: 800; font-size: 0.85rem; cursor: pointer; display: flex; align-items: center; gap: 8px;"
                    class="hover:scale-105"
                  >
                    <Radio size={16} /> Radio del Artista
                  </button>
                  <button 
                    type="button"
                    on:click={() => openArtistProfile(matchedArtist.name)}
                    style="padding: 10px 20px; border-radius: 500px; background: #22283a; border: 1px solid #353f5b; color: #fff; font-weight: 700; font-size: 0.85rem; cursor: pointer;"
                    class="hover:bg-[#2b334a]"
                  >
                    Ver Perfil Completo
                  </button>
                </div>
              </div>
            {/if}

            <div style="margin-bottom: 20px;">
              <span style="font-size: 0.75rem; color: #64748b; font-weight: 700; text-transform: uppercase;">Resultados de Búsqueda</span>
              <h3 style="font-size: 1.6rem; font-weight: 800; letter-spacing: -0.5px;">"{searchQuery}"</h3>
            </div>
            
            <!-- TRACK LIST TABLE -->
            <div style="display: flex; flex-direction: column;">
              <!-- TABLE HEADER -->
              <div style="display: grid; grid-template-columns: 44px 4fr 3fr 2fr 130px; padding: 10px 16px; border-bottom: 1px solid #1f2536; color: #64748b; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">
                <span>#</span>
                <span>Canción</span>
                <span>Álbum</span>
                <span>Fuente</span>
                <span style="text-align: right;"><Clock size={14} style="display: inline;" /></span>
              </div>

              <!-- TRACK ROWS -->
              {#each searchResults as track, idx}
                <div 
                  role="row"
                  tabindex="0"
                  on:click={() => playTrack(track, searchResults, idx)}
                  on:keydown={(e) => { if (e.key === 'Enter') playTrack(track, searchResults, idx); }}
                  style="display: grid; grid-template-columns: 44px 4fr 3fr 2fr 130px; padding: 10px 16px; border-radius: 8px; align-items: center; cursor: pointer; border: none; background: transparent; color: #fff; text-align: left; transition: background 0.15s;"
                  class="hover:bg-[#161a26]"
                >
                  <span style="color: #64748b; font-size: 0.85rem; font-weight: 600;">
                    {#if currentTrack && currentTrack.video_id === track.video_id && isPlaying}
                      <span style="color: #3b82f6;">▶</span>
                    {:else}
                      {idx + 1}
                    {/if}
                  </span>

                  <!-- TITLE & ARTIST -->
                  <div style="display: flex; align-items: center; gap: 12px; overflow: hidden; padding-right: 16px;">
                    <img src={track.thumbnail} alt={track.title} style="width: 44px; height: 44px; border-radius: 6px; object-fit: cover; flex-shrink: 0;" />
                    <div style="overflow: hidden;">
                      <div style="font-weight: 700; font-size: 0.92rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: {currentTrack?.video_id === track.video_id ? '#60a5fa' : '#fff'};">
                        {track.title}
                      </div>
                      <div 
                        on:click={(e) => openArtistProfile(track.artist, e)}
                        style="font-size: 0.78rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;"
                        class="hover:underline"
                      >
                        {track.artist}
                      </div>
                    </div>
                  </div>

                  <!-- ALBUM -->
                  <span style="color: #94a3b8; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 12px;">
                    {track.album || 'Single'}
                  </span>

                  <!-- SOURCE BADGE -->
                  <div>
                    <span style="font-size: 0.68rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; background: {track.source === 'soundcloud' ? 'rgba(255, 85, 0, 0.15)' : 'rgba(59, 130, 246, 0.15)'}; color: {track.source === 'soundcloud' ? '#ff7733' : '#60a5fa'}; border: 1px solid {track.source === 'soundcloud' ? 'rgba(255, 85, 0, 0.3)' : 'rgba(59, 130, 246, 0.3)'};">
                      {track.source === 'soundcloud' ? 'SoundCloud' : 'YouTube Music'}
                    </span>
                  </div>

                  <!-- ACTIONS, CREDITS & DURATION -->
                  <div style="display: flex; align-items: center; justify-content: flex-end; gap: 10px; color: #94a3b8;">
                    <button 
                      type="button"
                      on:click={(e) => openSongCredits(track, e)}
                      style="background: transparent; border: none; cursor: pointer; color: #64748b;"
                      title="Ver créditos oficiales"
                      class="hover:text-white"
                    >
                      <Info size={16} />
                    </button>
                    <button 
                      type="button"
                      on:click={(e) => toggleFavorite(track, e)}
                      style="background: transparent; border: none; cursor: pointer; color: {favorites.some(f => f.video_id === track.video_id) ? '#3b82f6' : '#64748b'};"
                      title="Favorito"
                    >
                      <Heart size={16} fill={favorites.some(f => f.video_id === track.video_id) ? '#3b82f6' : 'none'} />
                    </button>
                    <button 
                      type="button"
                      on:click={(e) => downloadTrack(track, e)}
                      style="background: transparent; border: none; cursor: pointer; color: #64748b;"
                      title="Guardar en Disco D"
                    >
                      <Download size={16} />
                    </button>
                    <span style="font-size: 0.82rem; color: #64748b; min-width: 32px; text-align: right;">{track.duration}</span>
                  </div>
                </div>
              {/each}
            </div>
          {:else}
            <!-- EMPTY SEARCH STATE -->
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 350px; color: #64748b;">
              <Search size={52} style="margin-bottom: 14px; opacity: 0.35;" />
              <h3 style="font-size: 1.25rem; font-weight: 800; color: #fff; margin-bottom: 6px;">Encuentra cualquier canción o artista</h3>
              <p style="font-size: 0.88rem; max-width: 420px; text-align: center; color: #94a3b8;">Escribe el nombre de un artista para ver su biografía, álbumes y pistas principales.</p>
            </div>
          {/if}
        </div>

      <!-- ARTIST PROFILE TAB -->
      {:else if activeTab === 'artist'}
        <div>
          {#if isLoadingArtist}
            <div style="display: flex; align-items: center; justify-content: center; height: 380px; color: #60a5fa; gap: 12px; font-weight: 700;">
              <Disc size={28} class="animate-spin" /> Cargando discografía y perfil de artista...
            </div>
          {:else if currentArtist}
            <!-- ARTIST HERO BANNER -->
            <div style="position: relative; border-radius: 16px; overflow: hidden; margin-bottom: 32px; height: 280px; display: flex; align-items: flex-end; padding: 32px; box-shadow: 0 20px 50px rgba(0,0,0,0.6);">
              <img 
                src={currentArtist.banner} 
                alt={currentArtist.name} 
                style="position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; filter: brightness(0.4) saturate(1.2);"
              />
              <div style="position: absolute; inset: 0; background: linear-gradient(180deg, transparent 0%, rgba(9, 10, 15, 0.95) 100%);"></div>
              
              <div style="position: relative; z-index: 10; display: flex; align-items: flex-end; gap: 24px;">
                <img src={currentArtist.banner} alt={currentArtist.name} style="width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 3px solid #3b82f6; box-shadow: 0 8px 30px rgba(0,0,0,0.8);" />
                <div>
                  <div style="display: flex; align-items: center; gap: 6px; color: #60a5fa; font-size: 0.78rem; font-weight: 800; text-transform: uppercase;">
                    <Check size={16} /> Artista Verificado
                  </div>
                  <h2 style="font-size: 3.2rem; font-weight: 900; letter-spacing: -1.5px; line-height: 1.1; margin: 4px 0;">{currentArtist.name}</h2>
                  <div style="color: #cbd5e1; font-size: 0.9rem;">
                    {currentArtist.subscribers || 'Comunidad'} oyentes / suscriptores
                  </div>
                </div>
              </div>
            </div>

            <!-- ACTION BUTTONS -->
            <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 28px;">
              <button 
                type="button"
                on:click={() => { if (currentArtist.top_songs?.length > 0) playTrack(currentArtist.top_songs[0], currentArtist.top_songs, 0); }}
                style="padding: 12px 28px; border-radius: 500px; background: #3b82f6; border: none; color: #fff; font-weight: 800; font-size: 0.95rem; display: flex; align-items: center; gap: 10px; cursor: pointer; box-shadow: 0 8px 24px rgba(59, 130, 246, 0.45);"
                class="hover:scale-105"
              >
                <Play size={18} fill="#fff" /> Reproducir Todo
              </button>
              <button 
                type="button"
                on:click={() => startArtistRadio(currentArtist.name)}
                style="padding: 12px 24px; border-radius: 500px; background: #1c2233; border: 1px solid #2e3852; color: #fff; font-weight: 800; font-size: 0.95rem; display: flex; align-items: center; gap: 10px; cursor: pointer;"
                class="hover:bg-[#28324a]"
              >
                <Radio size={18} color="#60a5fa" /> Iniciar Radio del Artista
              </button>
            </div>

            <!-- TOP SONGS SECTION -->
            <div style="margin-bottom: 40px;">
              <h3 style="font-size: 1.4rem; font-weight: 800; margin-bottom: 16px;">Canciones Populares</h3>
              <div style="display: flex; flex-direction: column;">
                {#each currentArtist.top_songs as song, idx}
                  <div 
                    role="row"
                    tabindex="0"
                    on:click={() => playTrack(song, currentArtist.top_songs, idx)}
                    on:keydown={(e) => { if (e.key === 'Enter') playTrack(song, currentArtist.top_songs, idx); }}
                    style="display: grid; grid-template-columns: 44px 4fr 3fr 100px; padding: 10px 16px; border-radius: 8px; align-items: center; cursor: pointer; border: none; background: transparent; color: #fff; text-align: left; transition: background 0.15s;"
                    class="hover:bg-[#161a26]"
                  >
                    <span style="color: #64748b; font-size: 0.85rem;">{idx + 1}</span>
                    <div style="display: flex; align-items: center; gap: 12px; overflow: hidden; padding-right: 16px;">
                      <img src={song.thumbnail} alt={song.title} style="width: 44px; height: 44px; border-radius: 6px; object-fit: cover;" />
                      <div style="overflow: hidden;">
                        <div style="font-weight: 700; font-size: 0.92rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: {currentTrack?.video_id === song.video_id ? '#60a5fa' : '#fff'};">
                          {song.title}
                        </div>
                        <div style="font-size: 0.78rem; color: #94a3b8;">{song.artist}</div>
                      </div>
                    </div>
                    <span style="color: #94a3b8; font-size: 0.82rem;">{song.album || 'Single'}</span>
                    <div style="display: flex; align-items: center; justify-content: flex-end; gap: 10px;">
                      <button 
                        type="button" 
                        on:click={(e) => openSongCredits(song, e)}
                        style="background: transparent; border: none; color: #64748b; cursor: pointer;"
                        title="Ver créditos"
                      >
                        <Info size={16} />
                      </button>
                      <span style="font-size: 0.82rem; color: #64748b;">{song.duration}</span>
                    </div>
                  </div>
                {/each}
              </div>
            </div>

            <!-- SIMILAR ARTISTS SECTION ("LOS FANS TAMBIÉN ESCUCHAN") -->
            {#if currentArtist.related_artists?.length > 0}
              <div style="margin-bottom: 44px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px;">
                  <h3 style="font-size: 1.4rem; font-weight: 800; letter-spacing: -0.5px;">Fans también escuchan</h3>
                  <span style="font-size: 0.8rem; color: #64748b;">Artistas similares y recomendados</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 18px;">
                  {#each currentArtist.related_artists as sim}
                    <div 
                      on:click={() => openArtistProfile(sim.name)}
                      style="background: #12151e; border: 1px solid #1c2130; border-radius: 14px; padding: 18px 14px; text-align: center; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 10px; transition: all 0.2s;"
                      class="hover:border-[#3b82f6] hover:bg-[#181d2a] hover:scale-105"
                    >
                      <img src={sim.thumbnail} alt={sim.name} style="width: 88px; height: 88px; border-radius: 50%; object-fit: cover; border: 2px solid #273147;" />
                      <div style="font-weight: 700; font-size: 0.88rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%;">{sim.name}</div>
                      <div style="font-size: 0.72rem; color: #94a3b8;">{sim.subscribers || 'Artista Afín'}</div>
                    </div>
                  {/each}
                </div>
              </div>
            {/if}

            <!-- RADIO & SIMILAR SONGS SECTION -->
            {#if currentArtist.radio_tracks?.length > 0}
              <div style="margin-bottom: 44px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px;">
                  <div>
                    <h3 style="font-size: 1.4rem; font-weight: 800; letter-spacing: -0.5px;">Mix de Canciones Similares</h3>
                    <p style="font-size: 0.78rem; color: #94a3b8; margin-top: 2px;">Canciones del mismo género y estilo recomendadas para ti.</p>
                  </div>
                  <button 
                    type="button"
                    on:click={() => playTrack(currentArtist.radio_tracks[0], currentArtist.radio_tracks, 0)}
                    style="padding: 8px 18px; border-radius: 500px; background: #22283a; border: 1px solid #353f5b; color: #fff; font-size: 0.82rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 8px;"
                    class="hover:bg-[#2c344d]"
                  >
                    <Play size={14} fill="#fff" /> Reproducir Mix
                  </button>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px;">
                  {#each currentArtist.radio_tracks.slice(0, 8) as rTrack, idx}
                    <div 
                      role="row"
                      tabindex="0"
                      on:mouseenter={() => prefetchTrack(rTrack)}
                      on:click={() => playTrack(rTrack, currentArtist.radio_tracks, idx)}
                      style="background: #12151e; border: 1px solid #1c2130; border-radius: 10px; display: flex; align-items: center; gap: 12px; padding: 10px; cursor: pointer; transition: all 0.15s;"
                      class="hover:bg-[#181d2a] hover:border-[#2f3952]"
                    >
                      <img src={rTrack.thumbnail} alt={rTrack.title} style="width: 52px; height: 52px; border-radius: 8px; object-fit: cover; flex-shrink: 0;" />
                      <div style="flex: 1; overflow: hidden;">
                        <div style="font-weight: 700; font-size: 0.88rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{rTrack.title}</div>
                        <div style="font-size: 0.76rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{rTrack.artist}</div>
                      </div>
                      <div style="color: #64748b; font-size: 0.78rem; margin-right: 6px;">{rTrack.duration}</div>
                    </div>
                  {/each}
                </div>
              </div>
            {/if}

            <!-- DISCOGRAPHY (ALBUMS & SINGLES) -->
            {#if currentArtist.albums?.length > 0}
              <div style="margin-bottom: 40px;">
                <h3 style="font-size: 1.4rem; font-weight: 800; margin-bottom: 16px;">Discografía (Álbumes & Sencillos)</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 18px;">
                  {#each currentArtist.albums as alb}
                    <div 
                      on:click={() => { searchQuery = `${currentArtist.name} ${alb.title}`; activeTab = 'search'; performSearch(); }}
                      style="background: #12151e; padding: 14px; border-radius: 10px; cursor: pointer; border: 1px solid #1c2130; text-align: left; transition: all 0.2s;"
                      class="hover:border-[#2f3952] hover:bg-[#161a26]"
                    >
                      <img src={alb.thumbnail} alt={alb.title} style="width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; margin-bottom: 10px;" />
                      <div style="font-weight: 700; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{alb.title}</div>
                      <div style="font-size: 0.76rem; color: #94a3b8;">{alb.year || alb.type}</div>
                    </div>
                  {/each}
                </div>
              </div>
            {/if}

            <!-- ARTIST BIOGRAPHY -->
            {#if currentArtist.description}
              <div style="background: #131724; border-radius: 14px; padding: 24px; border: 1px solid #1e2538; margin-bottom: 40px;">
                <h4 style="font-size: 1.1rem; font-weight: 800; margin-bottom: 10px; color: #fff;">Acerca de {currentArtist.name}</h4>
                <p style="color: #cbd5e1; font-size: 0.9rem; line-height: 1.7; white-space: pre-line;">{currentArtist.description}</p>
              </div>
            {/if}
          {/if}
        </div>

      <!-- LIBRARY TAB -->
      {:else if activeTab === 'library'}
        <div>
          <!-- PLAYLIST HEADER BANNER -->
          <div style="display: flex; align-items: flex-end; gap: 24px; margin-bottom: 28px; padding: 20px 0;">
            <div style="width: 180px; height: 180px; border-radius: 14px; background: linear-gradient(135deg, #1d4ed8, #38bdf8); display: flex; align-items: center; justify-content: center; box-shadow: 0 14px 30px rgba(29, 78, 216, 0.45);">
              <Heart size={80} color="#fff" fill="#fff" />
            </div>
            <div>
              <span style="font-size: 0.78rem; font-weight: 800; text-transform: uppercase; color: #60a5fa; letter-spacing: 1px;">Tu Colección Personal</span>
              <h2 style="font-size: 3.2rem; font-weight: 900; letter-spacing: -1.5px; line-height: 1.1; margin: 6px 0;">Pistas Guardadas</h2>
              <div style="color: #94a3b8; font-size: 0.9rem; font-weight: 600;">
                {favorites.length} canciones archivadas en Disco D
              </div>
            </div>
          </div>

          <!-- PLAY BUTTON -->
          <div style="margin-bottom: 20px;">
            <button 
              type="button"
              on:click={() => { if (favorites.length > 0) playTrack(favorites[0], favorites, 0); }}
              style="width: 54px; height: 54px; border-radius: 50%; background: #3b82f6; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 8px 24px rgba(59, 130, 246, 0.45); transition: transform 0.15s;"
              class="hover:scale-105"
            >
              <Play size={24} color="#fff" fill="#fff" style="margin-left: 2px;" />
            </button>
          </div>

          <!-- FAVORITES TABLE -->
          {#if favorites.length === 0}
            <div style="padding: 40px; text-align: center; color: #64748b;">
              <Heart size={44} style="margin: 0 auto 12px auto; opacity: 0.3;" />
              <p>Aún no has guardado canciones. Presiona el corazón en cualquier resultado para archivarlo aquí.</p>
            </div>
          {:else}
            <div style="display: flex; flex-direction: column;">
              {#each favorites as track, idx}
                <div 
                  role="row"
                  tabindex="0"
                  on:click={() => playTrack(track, favorites, idx)}
                  on:keydown={(e) => { if (e.key === 'Enter') playTrack(track, favorites, idx); }}
                  style="display: grid; grid-template-columns: 44px 4fr 3fr 100px; padding: 10px 16px; border-radius: 8px; align-items: center; cursor: pointer; border: none; background: transparent; color: #fff; text-align: left; transition: background 0.15s;"
                  class="hover:bg-[#161a26]"
                >
                  <span style="color: #64748b; font-size: 0.85rem;">{idx + 1}</span>
                  <div style="display: flex; align-items: center; gap: 12px; overflow: hidden; padding-right: 16px;">
                    <img src={track.thumbnail} alt={track.title} style="width: 44px; height: 44px; border-radius: 6px; object-fit: cover;" />
                    <div style="overflow: hidden;">
                      <div style="font-weight: 700; font-size: 0.92rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: {currentTrack?.video_id === track.video_id ? '#60a5fa' : '#fff'};">
                        {track.title}
                      </div>
                      <div 
                        on:click={(e) => openArtistProfile(track.artist, e)}
                        style="font-size: 0.78rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;"
                        class="hover:underline"
                      >
                        {track.artist}
                      </div>
                    </div>
                  </div>
                  <span style="color: #94a3b8; font-size: 0.82rem;">{track.album || 'Single'}</span>
                  <div style="display: flex; align-items: center; justify-content: flex-end; gap: 12px; color: #94a3b8;">
                    <button type="button" on:click={(e) => toggleFavorite(track, e)} style="background: transparent; border: none; cursor: pointer; color: #3b82f6;">
                      <Heart size={16} fill="#3b82f6" />
                    </button>
                    <span style="font-size: 0.82rem;">{track.duration}</span>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>

      <!-- LYRICS TAB -->
      {:else if activeTab === 'lyrics'}
        <div style="max-width: 820px; margin: 0 auto; height: 100%; display: flex; flex-direction: column;">
          {#if !currentTrack}
            <div style="text-align: center; margin: auto; color: #64748b;">
              <Mic2 size={60} style="margin: 0 auto 14px auto; opacity: 0.3;" />
              <h3>Reproduce una canción para activar las letras</h3>
            </div>
          {:else}
            <div style="margin-bottom: 24px;">
              <span style="font-size: 0.78rem; color: #3b82f6; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">Sincronizado en Vivo</span>
              <h2 style="font-size: 2.2rem; font-weight: 900; letter-spacing: -0.5px;">{currentTrack.title}</h2>
              <p 
                on:click={(e) => openArtistProfile(currentTrack.artist, e)}
                style="color: #94a3b8; font-size: 1.1rem; font-weight: 700; cursor: pointer;"
                class="hover:underline"
              >
                {currentTrack.artist}
              </p>
            </div>

            {#if lyricsData.is_synced && lyricsData.synced.length > 0}
              <!-- SYNCHRONIZED KARAOKE LYRICS -->
              <div 
                bind:this={lyricsContainer}
                style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 24px; padding: 40px 36px;"
              >
                {#each lyricsData.synced as line, i}
                  <button 
                    type="button"
                    on:click={() => { if (audioElement) audioElement.currentTime = line.time; }}
                    style="border: none; background: transparent; text-align: left; font-size: {currentLyricIndex === i ? '2.4rem' : '1.7rem'}; font-weight: 800; line-height: 1.35; cursor: pointer; transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); color: {currentLyricIndex === i ? '#ffffff' : 'rgba(255,255,255,0.22)'}; transform-origin: left center; transform: {currentLyricIndex === i ? 'scale(1.02)' : 'scale(1)'}; text-shadow: {currentLyricIndex === i ? '0 0 25px rgba(59, 130, 246, 0.5)' : 'none'}; padding: 4px 0;"
                  >
                    {line.text}
                  </button>
                {/each}
              </div>
            {:else}
              <!-- PLAIN LYRICS -->
              <div style="white-space: pre-line; line-height: 1.8; font-size: 1.25rem; font-weight: 600; color: #cbd5e1; overflow-y: auto; padding: 20px 36px;">
                {lyricsData.plain}
              </div>
            {/if}
          {/if}
        </div>
      {/if}
    </div>
  </main>
</div>

<!-- BOTTOM PERSISTENT PLAYER BAR -->
<footer style="position: fixed; bottom: 0; left: 0; width: 100vw; height: 90px; background: #0c0e15; border-top: 1px solid #1c2233; display: grid; grid-template-columns: 1fr 2fr 1fr; align-items: center; padding: 0 20px; z-index: 100;">
  
  <!-- LEFT: CURRENT TRACK INFO -->
  <div style="display: flex; align-items: center; gap: 14px; overflow: hidden;">
    {#if currentTrack}
      <img src={currentTrack.thumbnail} alt={currentTrack.title} style="width: 54px; height: 54px; border-radius: 8px; object-fit: cover; box-shadow: 0 4px 14px rgba(0,0,0,0.5);" />
      <div style="overflow: hidden;">
        <div style="font-weight: 700; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{currentTrack.title}</div>
        <div 
          on:click={(e) => openArtistProfile(currentTrack.artist, e)}
          style="font-size: 0.74rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;"
          class="hover:underline"
        >
          {currentTrack.artist}
        </div>
      </div>
      <button 
        type="button"
        on:click={(e) => toggleFavorite(currentTrack, e)}
        style="background: transparent; border: none; cursor: pointer; color: {favorites.some(f => f.video_id === currentTrack.video_id) ? '#3b82f6' : '#64748b'}; margin-left: 6px;"
        title="Favorito"
      >
        <Heart size={18} fill={favorites.some(f => f.video_id === currentTrack.video_id) ? '#3b82f6' : 'none'} />
      </button>
      <button 
        type="button"
        on:click={(e) => openAddToPlaylist(currentTrack, e)}
        style="background: transparent; border: none; cursor: pointer; color: #94a3b8; margin-left: 4px;"
        title="Añadir a playlist (+)"
        class="hover:text-white"
      >
        <Plus size={18} />
      </button>
    {:else}
      <div style="width: 54px; height: 54px; border-radius: 8px; background: #161924; display: flex; align-items: center; justify-content: center;">
        <Music size={22} color="#475569" />
      </div>
      <div style="color: #64748b; font-size: 0.82rem;">Selecciona una pista para reproducir</div>
    {/if}
  </div>

  <!-- CENTER: PLAYER CONTROLS & PROGRESS -->
  <div style="display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%; max-width: 650px; margin: 0 auto;">
    <div style="display: flex; align-items: center; gap: 20px;">
      <!-- SHUFFLE -->
      <button 
        type="button"
        on:click={() => isShuffle = !isShuffle}
        style="background: transparent; border: none; cursor: pointer; color: {isShuffle ? '#3b82f6' : '#64748b'};"
        title="Aleatorio"
      >
        <Shuffle size={18} />
      </button>

      <!-- PREV -->
      <button 
        type="button"
        on:click={playPrev}
        style="background: transparent; border: none; cursor: pointer; color: #94a3b8;"
        title="Anterior"
      >
        <SkipBack size={20} fill="#94a3b8" />
      </button>

      <!-- PLAY/PAUSE BIG BUTTON -->
      <button 
        type="button"
        on:click={togglePlay}
        style="width: 40px; height: 40px; border-radius: 50%; background: #ffffff; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: transform 0.15s; box-shadow: 0 0 16px rgba(255,255,255,0.25);"
        class="hover:scale-105"
        title={isPlaying ? 'Pausar' : 'Reproducir'}
      >
        {#if isLoadingAudio}
          <Disc size={18} color="#000" class="animate-spin" />
        {:else if isPlaying}
          <Pause size={20} color="#000" fill="#000" />
        {:else}
          <Play size={20} color="#000" fill="#000" style="margin-left: 2px;" />
        {/if}
      </button>

      <!-- NEXT -->
      <button 
        type="button"
        on:click={playNext}
        style="background: transparent; border: none; cursor: pointer; color: #94a3b8;"
        title="Siguiente"
      >
        <SkipForward size={20} fill="#94a3b8" />
      </button>

      <!-- REPEAT -->
      <button 
        type="button"
        on:click={cycleRepeat}
        style="background: transparent; border: none; cursor: pointer; color: {repeatMode > 0 ? '#3b82f6' : '#64748b'};"
        title={repeatMode === 0 ? 'Sin repetición' : repeatMode === 1 ? 'Repetir lista' : 'Repetir canción'}
      >
        <Repeat size={18} />
      </button>
    </div>

    <!-- PROGRESS SCRUBBER BAR -->
    <div style="display: flex; align-items: center; gap: 10px; width: 100%; font-size: 0.74rem; color: #94a3b8;" class="scrubber-container">
      <span style="min-width: 34px; text-align: right; font-variant-numeric: tabular-nums;">{formatSeconds(currentTime)}</span>
      <input 
        type="range" 
        min="0" 
        max={duration || 100} 
        value={currentTime} 
        on:input={handleSeek}
        style="width: 100%; background: linear-gradient(to right, #3b82f6 {progressPercent}%, #23283a {progressPercent}%);"
      />
      <span style="min-width: 34px; font-variant-numeric: tabular-nums;">{formatSeconds(duration)}</span>
    </div>
  </div>

  <!-- RIGHT: VOLUME, CREDITS & LYRICS -->
  <div style="display: flex; align-items: center; justify-content: flex-end; gap: 16px;">
    <!-- CREDITS BUTTON -->
    {#if currentTrack}
      <button 
        type="button"
        on:click={(e) => openSongCredits(currentTrack, e)}
        style="background: transparent; border: none; cursor: pointer; color: #94a3b8;"
        title="Ver Créditos Oficiales (Compositores, Productores, Sello)"
        class="hover:text-white"
      >
        <Info size={18} />
      </button>
    {/if}

    <!-- LYRICS BUTTON -->
    <button 
      type="button"
      on:click={() => activeTab = activeTab === 'lyrics' ? 'home' : 'lyrics'}
      style="background: transparent; border: none; cursor: pointer; color: {activeTab === 'lyrics' ? '#3b82f6' : '#64748b'};"
      title="Letras en Vivo"
    >
      <Mic2 size={18} />
    </button>

    <!-- AUDIO SETTINGS BUTTON -->
    <button 
      type="button"
      on:click={() => showAudioSettingsModal = true}
      style="background: transparent; border: none; cursor: pointer; color: {sleepTimerRemaining > 0 || playbackSpeed !== 1.0 ? '#3b82f6' : '#94a3b8'}; position: relative;"
      title="Ajustes de Sonido, Velocidad y Temporizador"
      class="hover:text-white"
    >
      <SlidersHorizontal size={18} />
      {#if sleepTimerRemaining > 0 || playbackSpeed !== 1.0}
        <span style="position: absolute; top: -2px; right: -2px; width: 6px; height: 6px; border-radius: 50%; background: #3b82f6;"></span>
      {/if}
    </button>

    <!-- QUEUE DRAWER BUTTON -->
    <button 
      type="button"
      on:click={() => showQueueDrawer = !showQueueDrawer}
      style="background: transparent; border: none; cursor: pointer; color: {showQueueDrawer ? '#3b82f6' : '#94a3b8'};"
      title="Cola de reproducción (Q)"
      class="hover:text-white"
    >
      <ListMusic size={18} />
    </button>

    <!-- FULLSCREEN IMMERSIVE MODE BUTTON -->
    <button 
      type="button"
      on:click={() => showFullscreenMode = !showFullscreenMode}
      style="background: transparent; border: none; cursor: pointer; color: #94a3b8;"
      title="Pantalla Completa Inmersiva (F)"
      class="hover:text-white"
    >
      <Maximize2 size={18} />
    </button>

    <!-- VOLUME CONTROLS -->
    <div style="display: flex; align-items: center; gap: 8px; width: 150px;" class="volume-container">
      <button type="button" on:click={toggleMute} style="background: transparent; border: none; cursor: pointer; color: {isMuted ? '#ef4444' : '#94a3b8'};">
        {#if isMuted || volume === 0}
          <VolumeX size={18} />
        {:else if volume < 0.5}
          <Volume1 size={18} />
        {:else}
          <Volume2 size={18} />
        {/if}
      </button>
      <input 
        type="range" 
        min="0" 
        max="1" 
        step="0.01" 
        value={isMuted ? 0 : volume} 
        on:input={handleVolumeChange}
        style="width: 75px; background: linear-gradient(to right, #3b82f6 {volumePercent}%, #23283a {volumePercent}%);"
      />
      <span style="font-size: 0.72rem; color: #94a3b8; min-width: 28px; text-align: right; font-variant-numeric: tabular-nums;">{volumePercent}%</span>
    </div>
  </div>
</footer>
