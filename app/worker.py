import logging
import math
import os
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

from sqlalchemy import and_, or_, select, update

from . import storage
from .db import Session, Video, new_id, now


log = logging.getLogger(__name__)
LEASE = timedelta(minutes=45)
FORMATS = "mov,matroska,webm,avi,mpeg,mpegts,flv"


class Job(NamedTuple):
    video_id: str
    source: str
    attempt: str
    abandoned_attempt: str | None


def claim():
    started = now()
    with Session.begin() as db:
        item = db.scalar(
            select(Video).where(or_(Video.state == "queued", and_(
                Video.state == "processing", or_(Video.started.is_(None), Video.started < started - LEASE)
            ))).order_by(Video.created, Video.id).limit(1).with_for_update(skip_locked=True)
        )
        if item is None:
            return None
        abandoned = item.attempt if item.state == "processing" else None
        item.state = "processing"
        item.started = started
        item.attempt = new_id()
        return Job(item.id, item.source, item.attempt, abandoned)


def run(command, timeout):
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-500:])
    return result.stdout.decode().strip()


def duration(path):
    value = float(run(["ffprobe", "-v", "error", "-protocol_whitelist", "file",
                       "-format_whitelist", FORMATS, "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", str(path)], 15))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid video duration")
    return value


def convert(source, media, poster):
    if duration(source) > 3600:
        raise ValueError("Video duration exceeds one hour")
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-y",
         "-protocol_whitelist", "file", "-format_whitelist", FORMATS,
         "-i", str(source), "-map", "0:V:0", "-map", "0:a:0?", "-sn", "-dn",
         "-vf", "fps=30,scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
         "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-pix_fmt", "yuv420p",
         "-maxrate", "2200k", "-bufsize", "4400k", "-b:a", "128k",
         "-c:a", "aac", "-ac", "2", "-movflags", "+faststart", "-t", "3600", str(media)], 1500)
    length = duration(media)
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(media), "-frames:v", "1",
         "-vf", "thumbnail=24,scale=640:-2", "-q:v", "3", "-update", "1", str(poster)], 30)
    if not poster.is_file():
        raise ValueError("Could not extract a preview")
    return min(math.ceil(length), 3600)


def finish(video_id, attempt, **values):
    with Session.begin() as db:
        return db.execute(update(Video).where(
            Video.id == video_id, Video.state == "processing", Video.attempt == attempt,
        ).values(**values)).rowcount == 1


def output_keys(video_id, attempt):
    return f"media/{video_id}/{attempt}.mp4", f"posters/{video_id}/{attempt}.jpg"


def discard_outputs(keys):
    for key in keys:
        try:
            storage.remove(key)
        except Exception:
            log.warning("Could not remove unpublished object %s", key, exc_info=True)


def process(job):
    video_id, original, attempt, abandoned = job
    keys = output_keys(video_id, attempt)
    media_key, poster_key = keys
    if abandoned:
        discard_outputs(output_keys(video_id, abandoned))
    written = []
    try:
        with TemporaryDirectory() as work:
            source, media, poster = (Path(work) / name for name in ("input", "output.mp4", "poster.jpg"))
            storage.download(original, source)
            seconds = convert(source, media, poster)
            for path, key, content_type in ((media, media_key, "video/mp4"), (poster, poster_key, "image/jpeg")):
                written.append(key)
                storage.put(path, key, content_type)
    except Exception:
        log.exception("Video processing failed for %s", video_id)
        discard_outputs(written)
        finish(video_id, attempt, state="failed")
        return
    if not finish(video_id, attempt, state="ready", duration=seconds, media=media_key, poster=poster_key):
        discard_outputs(keys)


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
