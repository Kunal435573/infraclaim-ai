FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home infraclaim
COPY app ./app
COPY scripts ./scripts
RUN mkdir -p /data && chown 10001:10001 /data
USER 10001
ENV DATABASE_PATH=/data/infraclaim.sqlite3
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
