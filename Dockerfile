FROM python:3.12-slim-bookworm
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WEB_DATA_DIR=/data WEB_COOKIE_SECURE=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 songdown && useradd -u 10001 -g songdown -M songdown \
    && mkdir -p /app /data && chown songdown:songdown /data
WORKDIR /app
COPY requirements-web.txt ./
RUN python -m pip install --no-cache-dir -r requirements-web.txt
COPY audio_converter_core.py ncm_decoder.py web_app.py web_worker.py conversion_errors.py site_settings.py run_web.py ./
COPY downloads.json ./
COPY web/ ./web/
USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)"
CMD ["python", "run_web.py", "--host", "0.0.0.0", "--port", "8765"]
