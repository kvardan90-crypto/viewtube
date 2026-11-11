import os
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select

from . import storage
from .db import Comment, Playlist, PlaylistItem, Session, User, Video, now
from .security import password_hash
from .worker import run


CONTACT_SHEET = Path(__file__).resolve().parents[1] / "demo" / "contact-sheet.png"
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


def source_clip(index, output):
    crop = f"crop=trunc(iw/6)*2:trunc(ih/6)*2:trunc(iw*{index % 3}/3):trunc(ih*{index // 3}/3)"
    filters = f"{crop},scale=1280:720,zoompan=z='min(1.10,1+on/4000)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=150:s=640x360:fps=25"
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(CONTACT_SHEET),
         "-vf", filters, "-frames:v", "150", "-c:v", "libx264", "-threads", "2",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)], 40)


def seed():
    demo_password = os.getenv("DEMO_PASSWORD")
    if not demo_password:
        raise RuntimeError("Set DEMO_PASSWORD before seeding")
    moderator_password = os.getenv("MODERATOR_PASSWORD", demo_password)
    with Session.begin() as db:
        users = {}
        for handle in sorted({clip[0] for clip in CLIPS} | {"demo_viewer", "demo_mod"}):
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

    with TemporaryDirectory() as work:
        for index, (handle, category, title, description, views) in enumerate(CLIPS):
            video_id = f"demo{index:028d}"
            with Session() as db:
                if db.get(Video, video_id):
                    continue
            source = Path(work) / "clip.mp4"
            source_clip(index, source)
            key = f"sources/{video_id}"
            storage.put(source, key, "video/mp4")
            with Session.begin() as db:
                db.add(Video(id=video_id, owner_id=users[handle], title=title, description=description,
                             category=category, views=views, source=key, created=now() - timedelta(days=index * 3 + 1)))
                db.flush()
                db.add(Comment(video_id=video_id, user_id=users["demo_viewer"], body="Спасибо за видео!"))
                if handle == "alpine":
                    db.add(PlaylistItem(playlist_id=playlist_id, video_id=video_id))
