import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc)


def new_id():
    return uuid4().hex


engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def sqlite_unicode_lower(connection, _record):
        # SQLite's built-in lower() only handles ASCII by default.
        connection.create_function("lower", 1, lambda value: None if value is None else str(value).lower(),
                                   deterministic=True)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    handle: Mapped[str] = mapped_column(String(32), unique=True)
    password: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="user")


class Login(Base):
    __tablename__ = "logins"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (Index("ix_feed", "state", "visibility", "hidden", "created"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(24), default="Other")
    visibility: Mapped[str] = mapped_column(String(10), default="public")
    state: Mapped[str] = mapped_column(String(16), default="queued")
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(96))
    media: Mapped[str | None] = mapped_column(String(128))
    poster: Mapped[str | None] = mapped_column(String(128))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[str | None] = mapped_column(String(32))


class Grant(Base):
    __tablename__ = "grants"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Like(Base):
    __tablename__ = "likes"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Subscription(Base):
    __tablename__ = "subscriptions"

    channel_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (UniqueConstraint("owner_id", "title"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))


class PlaylistItem(Base):
    __tablename__ = "playlist_items"

    playlist_id: Mapped[str] = mapped_column(ForeignKey("playlists.id"), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), primary_key=True)
    added: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("video_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
