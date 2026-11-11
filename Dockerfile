FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/viewtube
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 viewtube && useradd --uid 10001 --gid 10001 viewtube
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY web web
COPY demo demo
COPY scripts/smoke.py scripts/smoke.py
USER 10001:10001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "100"]
