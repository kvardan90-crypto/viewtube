import logging
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from . import storage
from .db import Session, Video, new_id
from .services import Actor, get_video


router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)
MAX_UPLOAD = 256 * 1024 * 1024
CATEGORIES = ("Technology", "Nature", "Travel", "Cooking", "Music", "Art", "Other")
STORAGE_FAILURES = (BotoCoreError, ClientError, OSError, S3UploadFailedError)


@router.post("/videos", status_code=202, openapi_extra={
    "requestBody": {"required": True, "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}
})
async def upload(
    request: Request,
    actor: Actor,
    title: Annotated[str, Query(min_length=1, max_length=140)],
    description: Annotated[str, Query(max_length=4000)] = "",
    visibility: Literal["public", "private"] = "public",
    category: str = "Other",
):
    title = title.strip()
    if not title or "\0" in title or "\0" in description or category not in CATEGORIES:
        raise HTTPException(422, "Проверьте название, описание и категорию")
    length_header = request.headers.get("content-length")
    declared = None
    if length_header is not None:
        if not length_header.isascii() or not length_header.isdecimal():
            raise HTTPException(400, "Некорректный размер файла")
        if len(length_header) > 12 or int(length_header) > MAX_UPLOAD:
            raise HTTPException(413, "Максимум 256 МБ")
        declared = int(length_header)
    video_id = new_id()
    key = f"sources/{video_id}"
    with TemporaryDirectory() as work:
        path = Path(work) / "source"
        received = 0
        with path.open("wb") as file:
            async for chunk in request.stream():
                received += len(chunk)
                if received > MAX_UPLOAD:
                    raise HTTPException(413, "Максимум 256 МБ")
                if chunk:
                    await run_in_threadpool(file.write, chunk)
        if not received:
            raise HTTPException(422, "Пустой файл")
        if declared is not None and declared != received:
            raise HTTPException(400, "Получен неполный файл")
        await run_in_threadpool(save_upload, path, key, video_id, actor.id, title, description, visibility, category)
    return {"id": video_id, "state": "queued"}


def save_upload(path, key, video_id, owner_id, title, description, visibility, category):
    try:
        storage.put(path, key, "application/octet-stream")
    except STORAGE_FAILURES:
        log.exception("Could not store upload %s", video_id)
        raise HTTPException(503, "Хранилище временно недоступно")
    # If the commit outcome is uncertain, leave the object available for reconciliation.
    with Session.begin() as db:
        db.add(Video(id=video_id, source=key, owner_id=owner_id, title=title,
                     description=description, visibility=visibility, category=category))


def bounds(header, size):
    if header is None:
        return 0, size - 1
    if size == 0:
        raise ValueError
    match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", header)
    if not match:
        raise ValueError
    left, right = match.groups()
    if not left:
        if not right or int(right) == 0:
            raise ValueError
        return max(0, size - int(right)), size - 1
    start = int(left)
    end = min(int(right), size - 1) if right else size - 1
    if start > end:
        raise ValueError
    return start, end


@router.head("/videos/{video_id}/media", include_in_schema=False)
@router.head("/videos/{video_id}/poster", include_in_schema=False)
@router.get("/videos/{video_id}/media", response_class=Response)
@router.get("/videos/{video_id}/poster", response_class=Response)
def serve_media(video_id: str, request: Request, ctx=Depends(get_video)):
    video = ctx.video
    poster = request.url.path.endswith("/poster")
    key = video.poster if poster else video.media
    if video.state != "ready" or not key:
        raise HTTPException(404, "Файл ещё недоступен")
    try:
        length = storage.size(key)
    except FileNotFoundError:
        raise HTTPException(404, "Файл ещё недоступен")
    except STORAGE_FAILURES:
        log.exception("Could not check media for %s", video_id)
        raise HTTPException(503, "Хранилище временно недоступно")
    # Media responses do not supply a validator for If-Range.
    header = request.headers.get("range") if "if-range" not in request.headers else None
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    try:
        start, end = bounds(header, length)
    except ValueError:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{length}"})
    headers["Content-Length"] = str(end - start + 1)
    if header is not None:
        headers["Content-Range"] = f"bytes {start}-{end}/{length}"
    status = 206 if header is not None else 200
    content_type = "image/jpeg" if poster else "video/mp4"
    if request.method == "HEAD" or not length:
        return Response(status_code=status, headers=headers, media_type=content_type)
    return StreamingResponse(storage.stream(key, start, end), status_code=status, headers=headers, media_type=content_type)
