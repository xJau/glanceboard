FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY glanceboard/ ./glanceboard/
COPY assets/ ./assets/

# The rendered board and its state live on a volume, not in the image.
RUN useradd --uid 10001 --create-home glance \
    && mkdir -p /data \
    && chown glance:glance /data
USER glance

# Inside the container 0.0.0.0 is correct: the port is never published to the
# host, so the only thing that can reach it is Caddy on the shared network.
ENV GB_OUTPUT_DIR=/data \
    GB_BIND_HOST=0.0.0.0 \
    GB_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "glanceboard", "serve"]
