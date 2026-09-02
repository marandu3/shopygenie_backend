# Single stage, deliberately no apt-get: every dependency in requirements.txt
# (asyncpg, bcrypt, greenlet, etc.) ships a prebuilt manylinux wheel for
# linux/amd64 + Python 3.12, so no C compiler is needed to install them —
# keeps the image small and the build fast with no OS package fetches.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

# Installed system-wide while still root — simpler than --user here since
# there's no separate builder stage to copy site-packages out of.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=appuser:appuser . .
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh && mkdir -p uploads && chown -R appuser:appuser uploads

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
