import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from . import storage
from .db import Comment, Playlist, PlaylistItem, Session, User, Video, now
from .security import password_hash


DEMO = Path(__file__).resolve().parents[1] / "demo"
PUBLIC_DOMAIN_CLIPS = (
    ("orbit.mp4", "desk_lab", "Technology", "Ночная Земля с МКС",
     "Рассвет над краем ночной Земли в кадре с Международной космической станции. Источник: NASA Johnson Space Center.", 18000),
    ("gulf.mp4", "alpine", "Nature", "Рыба Мексиканского залива",
     "Подводная съёмка экспедиции в Мексиканском заливе. Источник: NOAA Okeanos Explorer.", 9800),
    ("geyser.mp4", "city_frame", "Travel", "Извержение гейзера Олд-Фейтфул",
     "Извержение в Йеллоустонском национальном парке. Источник: National Park Service, Jacob W. Frank.", 23400),
)
CLIPS = (
    ("alpine", "Nature", "Альпийская тропа к озеру", "Прогулка по горной долине у подножия Альп.", 24000),
    ("desk_lab", "Technology", "Как собрать удобный рабочий стол", "Демо рабочего места с механической клавиатурой.", 15200),
    ("citrus", "Cooking", "Лимонная паста за 15 минут", "Короткое превью рецепта с лимоном и пармезаном.", 37800),
    ("city_frame", "Travel", "Ночной Токио под дождём", "Неоновые улицы после дождя.", 92000),
    ("vinyl_room", "Music", "Джаз на виниле в воскресенье", "Винтажный проигрыватель и спокойный вечер.", 13100),
    ("city_frame", "Travel", "Дорога через красный каньон", "Вид на дорогу с вершины каньона.", 8600),
    ("alpine", "Nature", "Папоротники после дождя", "Капли на листьях крупным планом.", 6900),
    ("clay_studio", "Art", "Гончарный круг для начинающих", "Первые минуты работы с глиной.", 19100),
    ("alpine", "Nature", "Золотой час на берегу океана", "Свет над прибойной полосой.", 12300),
)


def demo_clips():
    for index, (filename, *metadata) in enumerate(PUBLIC_DOMAIN_CLIPS):
        yield len(CLIPS) + index, metadata, DEMO / "videos" / filename, timedelta(hours=index)
    for index, metadata in enumerate(CLIPS):
        yield index, metadata, DEMO / "animated" / f"{index}.mp4", timedelta(days=index * 3 + 1)


def seed():
    demo_password = os.getenv("DEMO_PASSWORD")
    if not demo_password:
        raise RuntimeError("Set DEMO_PASSWORD before seeding")
    moderator_password = os.getenv("MODERATOR_PASSWORD", demo_password)
    channels = {metadata[0] for _, metadata, _, _ in demo_clips()}
    with Session.begin() as db:
        users = {}
        for handle in sorted(channels | {"demo_viewer", "demo_mod"}):
            user = db.scalar(select(User).where(User.handle == handle))
            if not user:
                role = "moderator" if handle == "demo_mod" else "user"
                user = User(handle=handle, role=role, password=password_hash(
                    moderator_password if role == "moderator" else demo_password))
                db.add(user)
                db.flush()
            users[handle] = user.id
        playlist = db.scalar(select(Playlist).where(Playlist.owner_id == users["alpine"],
                                                    Playlist.title == "Природа крупным планом"))
        if not playlist:
            playlist = Playlist(owner_id=users["alpine"], title="Природа крупным планом")
            db.add(playlist)
            db.flush()
        playlist_id = playlist.id

    for index, (handle, category, title, description, views), source, age in demo_clips():
        video_id = f"demo{index:028d}"
        with Session() as db:
            if db.get(Video, video_id):
                continue
        key = f"sources/{video_id}"
        storage.put(source, key, "video/mp4")
        with Session.begin() as db:
            db.add(Video(id=video_id, owner_id=users[handle], title=title, description=description,
                         category=category, views=views, source=key, created=now() - age))
            db.flush()
            db.add(Comment(video_id=video_id, user_id=users["demo_viewer"], body="Спасибо за видео!"))
            if handle == "alpine":
                db.add(PlaylistItem(playlist_id=playlist_id, video_id=video_id))
