import logging
import math
import os
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import and_, or_, select, update

from . import storage
from .db import Session, Video, new_id, now


log = logging.getLogger(__name__)
LEASE = timedelta(minutes=45)


def claim():
    with Session.begin() as db:
        item = db.scalar(
            select(Video).where(or_(Video.state == "queued", and_(
                Video.state == "processing", Video.started < now() - LEASE
            ))).order_by(Video.created).limit(1).with_for_update(skip_locked=True)
        )
        if item is None:
            return None
        item.state = "processing"
        item.started = now()
        item.attempt = new_id()
        return item.id, item.source, item.attempt


def run(command, timeout):
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-500:])
    return result.stdout.decode().strip()


def duration(path):
    value = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", str(path)], 15))
    if not math.isfinite(value) or not 0 < value <= 3600:
        raise ValueError("Invalid video duration")
    return value


def convert(source, media, poster):
    length = duration(source)
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-y",
         "-protocol_whitelist", "file", "-format_whitelist", "mov,matroska,webm,avi,mpeg,mpegts,flv",
         "-i", str(source), "-map", "0:V:0", "-map", "0:a:0?", "-sn", "-dn",
         "-vf", "fps=30,scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
         "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ac", "2", "-movflags", "+faststart", "-t", "3600", str(media)], 1500)
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", str(min(length / 3, 3)), "-i", str(media), "-frames:v", "1",
         "-vf", "scale=640:-2", "-q:v", "3", "-update", "1", str(poster)], 30)
    if not poster.is_file():
        raise ValueError("Could not extract a preview")
    return math.ceil(length)


def finish(video_id, attempt, **values):
    with Session.begin() as db:
        return db.execute(update(Video).where(
            Video.id == video_id, Video.state == "processing", Video.attempt == attempt,
        ).values(**values)).rowcount == 1


def process(job):
    video_id, original, attempt = job
    media_key = f"media/{video_id}/{attempt}.mp4"
    poster_key = f"posters/{video_id}/{attempt}.jpg"
    try:
        with TemporaryDirectory() as work:
            source, media, poster = (Path(work) / name for name in ("input", "output.mp4", "poster.jpg"))
            storage.download(original, source)
            seconds = convert(source, media, poster)
            storage.put(media, media_key, "video/mp4")
            storage.put(poster, poster_key, "image/jpeg")
    except Exception:
        log.exception("Video processing failed for %s", video_id)
        finish(video_id, attempt, state="failed")
        return
    if not finish(video_id, attempt, state="ready", duration=seconds, media=media_key, poster=poster_key):
        storage.remove(media_key)
        storage.remove(poster_key)


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    while True:
        try:
            job = claim()
            if job is None:
                time.sleep(2)
            else:
                process(job)
        except Exception:
            log.exception("Worker iteration failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
