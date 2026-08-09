FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 10001 campfyr \
    && useradd --uid 10001 --gid campfyr --no-create-home --shell /usr/sbin/nologin campfyr \
    && mkdir -p /data \
    && chown campfyr:campfyr /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=campfyr:campfyr . .

USER campfyr

EXPOSE 5001
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/healthz', timeout=3)"

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "--threads", "4", "--access-logfile", "-", "campfyr:create_app()"]
