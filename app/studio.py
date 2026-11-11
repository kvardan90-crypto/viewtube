from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select, update

from .db import Grant, Playlist, PlaylistItem, Report, User, Video
from .services import Actor, Db, Staff, commit, find_user, get_video, set_relation, visible


router = APIRouter(prefix="/api")
class Access(BaseModel):
    enabled: bool


class Visibility(BaseModel):
    visibility: Literal["public", "private"]


class PlaylistTitle(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Complaint(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]


class Decision(BaseModel):
    action: Literal["hide", "dismiss", "restore"]


class Role(BaseModel):
    role: Literal["user", "moderator", "admin"]


def owned(db, user, video_id):
    video = db.get(Video, video_id)
    if not video or video.owner_id != user.id:
        raise HTTPException(404, "Видео не найдено")
    return video


@router.patch("/videos/{video_id}/visibility")
def change_visibility(video_id: str, data: Visibility, db: Db, user: Actor):
    video = owned(db, user, video_id)
    video.visibility = data.visibility
    db.commit()
    return {"visibility": video.visibility}


@router.get("/videos/{video_id}/grants")
def grants(video_id: str, db: Db, user: Actor):
    owned(db, user, video_id)
    return list(db.scalars(select(User.handle).join(Grant, Grant.user_id == User.id)
                           .where(Grant.video_id == video_id).order_by(User.handle)))


@router.put("/videos/{video_id}/grants/{handle}")
def grant(video_id: str, handle: str, data: Access, db: Db, user: Actor):
    owned(db, user, video_id)
    recipient = find_user(db, handle)
    if recipient.id == user.id:
        raise HTTPException(422, "У владельца уже есть доступ")
    set_relation(db, Grant, (video_id, recipient.id), {"video_id": video_id, "user_id": recipient.id}, data.enabled)
    return {"enabled": data.enabled}


@router.post("/playlists", status_code=201)
def create_playlist(data: PlaylistTitle, db: Db, user: Actor):
    playlist = Playlist(owner_id=user.id, title=data.title)
    db.add(playlist)
    commit(db, "У вас уже есть плейлист с таким названием")
    return {"id": playlist.id, "title": playlist.title}


@router.put("/playlists/{playlist_id}/items/{video_id}")
def playlist_item(playlist_id: str, video_id: str, data: Access, db: Db, user: Actor):
    item = db.get(Playlist, playlist_id)
    if not item or item.owner_id != user.id:
        raise HTTPException(404, "Плейлист не найден")
    if data.enabled and not visible(db, db.get(Video, video_id), user):
        raise HTTPException(404, "Видео не найдено")
    set_relation(db, PlaylistItem, (playlist_id, video_id), {"playlist_id": playlist_id, "video_id": video_id}, data.enabled)
    return {"enabled": data.enabled}


@router.post("/videos/{video_id}/reports", status_code=201)
def report(data: Complaint, db: Db, user: Actor, ctx=Depends(get_video)):
    video = ctx.video
    if video.visibility != "public" or video.owner_id == user.id or video.hidden:
        raise HTTPException(422, "Жалоба доступна для чужого публичного видео")
    item = Report(video_id=video.id, user_id=user.id, reason=data.reason)
    db.add(item)
    commit(db, "Вы уже отправили жалобу на это видео")
    return {"id": item.id}


@router.get("/moderation/reports")
def reports(db: Db, staff: Staff, offset: int = 0):
    rows = db.execute(select(Report, Video, User.handle).join(Video, Report.video_id == Video.id)
                      .join(User, Report.user_id == User.id)
                      .order_by((Report.status == "open").desc(), Report.created.desc())
                      .offset(max(0, min(offset, 10000))).limit(50))
    return [{
        "id": item.id, "video": video.id,
        "title": video.title if video.visibility == "public" else "Приватное видео",
        "private": video.visibility == "private", "hidden": video.hidden,
        "reporter": handle, "reason": item.reason, "status": item.status,
    } for item, video, handle in rows]


@router.put("/moderation/reports/{report_id}")
def review(report_id: str, data: Decision, db: Db, staff: Staff):
    item = db.get(Report, report_id)
    if not item:
        raise HTTPException(404, "Жалоба не найдена")
    video = db.scalar(select(Video).where(Video.id == item.video_id).with_for_update())
    if data.action == "dismiss":
        item.status = "dismissed"
        item.reviewed_by = staff.id
    else:
        video.hidden = data.action == "hide"
        db.execute(update(Report).where(Report.video_id == video.id).values(
            status="hidden" if video.hidden else "restored", reviewed_by=staff.id
        ))
    db.commit()
    return {"hidden": video.hidden}


@router.put("/admin/users/{handle}/role")
def change_role(handle: str, data: Role, db: Db, user: Actor):
    if user.role != "admin":
        raise HTTPException(403, "Требуется администратор")
    target = find_user(db, handle)
    if target.id == user.id:
        raise HTTPException(422, "Нельзя менять собственную роль")
    target.role = data.role
    db.commit()
    return {"handle": target.handle, "role": target.role}
