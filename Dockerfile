FROM python:3.11-slim

# Install system dependencies: ffmpeg and nodejs (for yt-dlp JS solving)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend requirements and install
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application and frontend dist
COPY backend/ ./backend/
COPY music_storage/ ./music_storage/
COPY frontend/dist/ ./frontend/dist/

WORKDIR /app/backend

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
