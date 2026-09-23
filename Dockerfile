# ---------- Build frontend ----------
FROM node:20-bookworm-slim AS web
WORKDIR /build/web
COPY web/package.json ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------- Runtime ----------
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-noto-core \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY --from=web /build/web/dist ./bot/web/dist

RUN mkdir -p /tmp/media_converter /app/frames

ENV WORK_DIR=/tmp/media_converter
ENV PORT=8080

EXPOSE 8080

CMD ["python", "-m", "bot.main"]