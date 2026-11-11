from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, or_, select, text, update

from .db import Comment, Grant, Like, Playlist, PlaylistItem, Report, Subscription, User, Video
from .media import CATEGORIES, router as media_router
from .security import COOKIE, DUMMY_HASH, login, password_hash, revoke, verify_password
from .services import Actor, Db, Staff, Viewer, commit, find_user, get_video, set_relation, video_dict, visible
from .studio import router as studio_router


app = FastAPI(title="ViewTube", version="1.0.0")
app.include_router(media_router, tags=["Media"])
app.include_router(studio_router, tags=["Studio"])
STATIC = Path(__file__).resolve().parents[1] / "web"


@app.middleware("http")
async def response_policy(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
        response = JSONResponse({"detail": "Недопустимый источник запроса"}, status_code=403)
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    elif request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; font-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
    return response


class Credentials(BaseModel):
    handle: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-zA-Z0-9_]{3,32}$")]
    password: Annotated[str, StringConstraints(min_length=10, max_length=128)]


class Toggle(BaseModel):
    enabled: bool


class Message(BaseModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


def account(user):
    return {"handle": user.handle, "role": user.role} if user else None


@app.get("/health", include_in_schema=False)
def health(db: Db):
    db.execute(text("SELECT 1"))
    return {"ok": True}


@app.get("/api/me", tags=["Account"])
def me(user: Viewer):
    return account(user)


@app.post("/api/register", status_code=201, tags=["Account"])
def register(data: Credentials, request: Request, response: Response, db: Db):
    user = User(handle=data.handle, password=password_hash(data.password))
    db.add(user)
    commit(db, "Имя уже занято")
    login(db, user, request, response)
    return account(user)


@app.post("/api/login", tags=["Account"])
def authenticate(data: Credentials, request: Request, response: Response, db: Db):
    user = db.scalar(select(User).where(User.handle == data.handle))
    if not verify_password(data.password, user.password if user else DUMMY_HASH) or not user:
        raise HTTPException(401, "Неверное имя или пароль")
    login(db, user, request, response)
    return account(user)


@app.post("/api/logout", tags=["Account"])
def logout(request: Request, response: Response, db: Db):
    revoke(db, request.cookies.get(COOKIE))
    db.commit()
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/videos", tags=["Videos"])
def feed(db: Db, user: Viewer, q: Annotated[str, Query(max_length=140)] = "",
         category: str = "", subscriptions: bool = False, offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    query = select(Video, User.handle).join(User, User.id == Video.owner_id).where(
        Video.state == "ready", Video.visibility == "public", Video.hidden.is_(False)
    )
    if q.strip():
        query = query.where(Video.title.icontains(q.strip(), autoescape=True))
    if category:
        if category not in CATEGORIES:
            raise HTTPException(422, "Неизвестная категория")
        query = query.where(Video.category == category)
    if subscriptions:
        if not user:
            raise HTTPException(401, "Войдите в аккаунт")
        query = query.join(Subscription, Subscription.channel_id == Video.owner_id).where(Subscription.user_id == user.id)
    return [video_dict(video, handle) for video, handle in db.execute(
        query.order_by(Video.created.desc(), Video.id).offset(offset).limit(24)
    )]


@app.get("/api/videos/{video_id}", tags=["Videos"])
def detail(db: Db, user: Viewer, ctx=Depends(get_video)):
    video = ctx.video
    owner = db.get(User, video.owner_id)
    likes = db.scalar(select(func.count()).select_from(Like).where(Like.video_id == video.id))
    return {
        **video_dict(video, owner.handle), "likes": likes,
        "liked": bool(user and db.get(Like, (video.id, user.id))),
        "subscribed": bool(user and db.get(Subscription, (owner.id, user.id))),
    }


@app.post("/api/videos/{video_id}/view", tags=["Videos"])
def add_view(db: Db, ctx=Depends(get_video)):
    if ctx.video.state == "ready":
        db.execute(update(Video).where(Video.id == ctx.video.id).values(views=Video.views + 1))
        db.commit()
    return {"ok": True}


@app.put("/api/videos/{video_id}/like", tags=["Videos"])
def like(data: Toggle, db: Db, user: Actor, ctx=Depends(get_video)):
    if ctx.video.state != "ready":
        raise HTTPException(409, "Видео обрабатывается")
    key = (ctx.video.id, user.id)
    set_relation(db, Like, key, {"video_id": key[0], "user_id": key[1]}, data.enabled)
    return {"liked": data.enabled}


@app.get("/api/videos/{video_id}/comments", tags=["Videos"])
def comments(db: Db, offset: Annotated[int, Query(ge=0, le=10000)] = 0, ctx=Depends(get_video)):
    query = select(Comment, User.handle).join(User, Comment.user_id == User.id).where(
        Comment.video_id == ctx.video.id
    ).order_by(Comment.created.desc(), Comment.id).offset(offset).limit(50)
    return [{"author": handle, "body": item.body, "created": item.created} for item, handle in db.execute(query)]


@app.post("/api/videos/{video_id}/comments", status_code=201, tags=["Videos"])
def comment(data: Message, db: Db, user: Actor, ctx=Depends(get_video)):
    if ctx.video.state != "ready":
        raise HTTPException(409, "Видео обрабатывается")
    item = Comment(video_id=ctx.video.id, user_id=user.id, body=data.body)
    db.add(item)
    db.commit()
    return {"author": user.handle, "body": item.body, "created": item.created}


@app.get("/api/channels/{handle}", tags=["Channels"])
def channel(handle: str, db: Db, user: Viewer, offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    owner = find_user(db, handle)
    is_owner = bool(user and user.id == owner.id)
    query = select(Video).where(Video.owner_id == owner.id)
    if not is_owner:
        audience = Video.visibility == "public"
        if user:
            audience = or_(audience, Video.id.in_(select(Grant.video_id).where(Grant.user_id == user.id)))
        query = query.where(Video.state == "ready", Video.hidden.is_(False), audience)
    playlists = db.scalars(select(Playlist).where(Playlist.owner_id == owner.id).order_by(Playlist.title).limit(100))
    return {
        "handle": owner.handle,
        "subscribers": db.scalar(select(func.count()).select_from(Subscription).where(Subscription.channel_id == owner.id)),
        "subscribed": bool(user and db.get(Subscription, (owner.id, user.id))),
        "videos": [video_dict(video, owner.handle) for video in db.scalars(
            query.order_by(Video.created.desc(), Video.id).offset(offset).limit(24)
        )],
        "playlists": [{"id": item.id, "title": item.title} for item in playlists],
    }


@app.put("/api/channels/{handle}/subscribe", tags=["Channels"])
def subscribe(handle: str, data: Toggle, db: Db, user: Actor):
    owner = find_user(db, handle)
    if owner.id == user.id:
        raise HTTPException(422, "Это ваш канал")
    set_relation(db, Subscription, (owner.id, user.id), {"channel_id": owner.id, "user_id": user.id}, data.enabled)
    return {"subscribed": data.enabled}


@app.get("/api/playlists/{playlist_id}", tags=["Channels"])
def playlist(playlist_id: str, db: Db, user: Viewer):
    item = db.get(Playlist, playlist_id)
    if not item:
        raise HTTPException(404, "Плейлист не найден")
    owner = db.get(User, item.owner_id)
    query = select(Video, User.handle).join(PlaylistItem, PlaylistItem.video_id == Video.id).join(
        User, User.id == Video.owner_id
    ).where(PlaylistItem.playlist_id == playlist_id).order_by(PlaylistItem.added, Video.id)
    return {"title": item.title, "owner": owner.handle, "videos": [
        video_dict(video, handle) for video, handle in db.execute(query) if visible(db, video, user)
    ]}


app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")
