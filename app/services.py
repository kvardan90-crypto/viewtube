from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from .db import Grant, Session, User, Video
from .security import COOKIE, current_user


def session():
    with Session() as db:
        yield db


Db = Annotated[DbSession, Depends(session)]


def viewer(request: Request, db: Db):
    return current_user(db, request.cookies.get(COOKIE))


Viewer = Annotated[User | None, Depends(viewer)]


def actor(user: Viewer):
    if user is None:
        raise HTTPException(401, "Войдите в аккаунт")
    return user


Actor = Annotated[User, Depends(actor)]


def moderator(user: Actor):
    if user.role not in {"moderator", "admin"}:
        raise HTTPException(403, "Недостаточно прав")
    return user


Staff = Annotated[User, Depends(moderator)]


def visible(db, video, user):
    if video is None:
        return False
    if user and user.id == video.owner_id:
        return True
    if video.hidden or video.state != "ready":
        return False
    return video.visibility == "public" or bool(user and db.get(Grant, (video.id, user.id)))


@dataclass
class VideoContext:
    video: Video


def get_video(video_id: str, db: Db, user: Viewer):
    video = db.get(Video, video_id)
    if not visible(db, video, user):
        raise HTTPException(404, "Видео не найдено")
    return VideoContext(video)


def video_dict(video, handle):
    return {
        "id": video.id, "owner": handle, "title": video.title, "description": video.description,
        "category": video.category, "visibility": video.visibility, "state": video.state,
        "hidden": video.hidden, "views": video.views, "duration": video.duration,
        "created": video.created,
    }


def find_user(db, handle):
    user = db.scalar(select(User).where(User.handle == handle.casefold()))
    if user is None:
        raise HTTPException(404, "Канал не найден")
    return user


def commit(db, conflict=None):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if conflict:
            raise HTTPException(409, conflict)


def set_relation(db, model, key, values, enabled):
    existing = db.get(model, key)
    if enabled and existing is None:
        db.add(model(**values))
        commit(db)
    elif not enabled and existing is not None:
        db.delete(existing)
        db.commit()
