import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import storage
from app.db import Like, Session, User, Video, now
from app.main import app
from app.worker import LEASE, claim, finish, output_keys, process, run


PASSWORD = "correct-horse-staple"


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def source(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.fail("FFmpeg and ffprobe are required")
    file = tmp_path / "clip.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=15",
         "-t", "1", "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(file)], 20)
    return file.read_bytes()


def register(client, handle):
    response = client.post("/api/register", json={"handle": handle, "password": PASSWORD})
    assert response.status_code == 201, response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert response.json()["role"] == "user"


def upload(client, source, visibility="public"):
    response = client.post("/api/videos", params={"title": "Первое видео", "visibility": visibility},
                           content=source, headers={"Content-Type": "application/octet-stream"})
    assert response.status_code == 202, response.text
    return "/api/videos/" + response.json()["id"]


def process_next():
    job = claim()
    assert job is not None
    process(job)
    return job[0]


def assign(handle, role):
    with Session.begin() as db:
        db.scalar(select(User).where(User.handle == handle)).role = role


def test_register_upload_play_like_comment(client, source):
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    assert "/api/videos" in client.get("/openapi.json").json()["paths"]
    register(client, "creator")
    url = upload(client, source)
    assert client.get(url).json()["state"] == "queued"
    assert client.get("/api/videos").json() == []
    process_next()
    detail = client.get(url).json()
    assert detail["state"] == "ready"
    assert client.get("/api/videos", params={"q": "первое"}).json()[0]["id"] == detail["id"]
    assert client.get("/api/videos", params={"q": "Нет совпадения"}).json() == []
    media = client.get(url + "/media")
    assert media.status_code == 200
    assert media.content[4:8] == b"ftyp"
    assert client.head(url + "/media").headers["content-length"] == str(len(media.content))
    ranged = client.get(url + "/media", headers={"Range": "bytes=5-15"})
    assert ranged.status_code == 206
    assert ranged.content == media.content[5:16]
    assert ranged.headers["content-range"] == f"bytes 5-15/{len(media.content)}"
    assert client.get(url + "/media", headers={"Range": "bytes=-7"}).content == media.content[-7:]
    unsatisfiable = client.get(url + "/media", headers={"Range": "bytes=99999999-"})
    assert unsatisfiable.status_code == 416
    assert unsatisfiable.headers["content-range"] == f"bytes */{len(media.content)}"
    outdated = client.get(url + "/media", headers={"Range": "bytes=5-15", "If-Range": '"outdated"'})
    assert outdated.status_code == 200
    assert outdated.content == media.content
    assert client.get(url + "/poster").content.startswith(b"\xff\xd8")
    assert client.post(url + "/view").status_code == 200
    assert client.get(url).json()["views"] == 1
    for _ in range(2):
        assert client.put(url + "/like", json={"enabled": True}).status_code == 200
    assert client.get(url).json()["likes"] == 1
    for _ in range(2):
        response = client.put(url + "/like", json={"enabled": False})
        assert response.status_code == 200
        assert response.json() == {"liked": False}
        assert client.get(url).json()["likes"] == 0
    with Session() as db:
        assert db.scalar(select(Like).where(Like.video_id == detail["id"])) is None
    assert client.post(url + "/comments", json={"body": "<script>test</script>"}).status_code == 201
    assert client.get(url + "/comments").json()[0]["body"] == "<script>test</script>"
    old_token = client.cookies.get("viewtube_session")
    assert client.post("/api/logout").status_code == 200
    client.cookies.set("viewtube_session", old_token)
    assert client.get("/api/me").json() is None
    assert client.post("/api/login", json={"handle": "CREATOR", "password": PASSWORD}).status_code == 200


def test_private_scope_and_revocation(client, source):
    register(client, "owner")
    url = upload(client, source, "private")
    video_id = process_next()
    playlist_id = client.post("/api/playlists", json={"title": "Избранное"}).json()["id"]
    playlist_url = "/api/playlists/" + playlist_id
    assert client.put(playlist_url + "/items/" + video_id, json={"enabled": True}).status_code == 200
    with TestClient(app) as guest, TestClient(app) as stranger:
        register(guest, "viewer")
        register(stranger, "stranger")
        assign("stranger", "admin")
        assert guest.get("/api/videos").json() == []
        for path in ("", "/media", "/poster", "/comments"):
            assert guest.get(url + path).status_code == 404
            assert stranger.get(url + path).status_code == 404
        assert guest.get("/api/channels/owner").json()["videos"] == []
        assert guest.get(playlist_url).json()["videos"] == []
        assert stranger.put(url + "/grants/viewer", json={"enabled": True}).status_code == 404
        assert client.put(url + "/grants/viewer", json={"enabled": True}).status_code == 200
        assert guest.get(url + "/media").status_code == 200
        assert guest.get("/api/channels/owner").json()["videos"][0]["id"] == video_id
        assert guest.get(playlist_url).json()["videos"][0]["id"] == video_id
        assert client.put(url + "/grants/viewer", json={"enabled": False}).status_code == 200
        assert guest.get(url + "/media", headers={"Range": "bytes=0-9"}).status_code == 404


def test_moderation_subscriptions_and_role_changes(client, source):
    register(client, "author")
    url = upload(client, source)
    process_next()
    with TestClient(app) as viewer, TestClient(app) as moderator, TestClient(app) as admin:
        register(viewer, "viewer")
        register(moderator, "mod")
        register(admin, "admin")
        assign("admin", "admin")
        assert viewer.put("/api/admin/users/mod/role", json={"role": "moderator"}).status_code == 403
        assert admin.put("/api/admin/users/mod/role", json={"role": "moderator"}).status_code == 200
        assert viewer.get("/api/videos?subscriptions=true").json() == []
        assert viewer.put("/api/channels/author/subscribe", json={"enabled": True}).status_code == 200
        assert len(viewer.get("/api/videos?subscriptions=true").json()) == 1
        complaint = viewer.post(url + "/reports", json={"reason": "Тест модерации"})
        assert complaint.status_code == 201
        report_url = "/api/moderation/reports/" + complaint.json()["id"]
        assert viewer.put(report_url, json={"action": "hide"}).status_code == 403
        assert moderator.get("/api/moderation/reports").json()[0]["status"] == "open"
        assert moderator.put(report_url, json={"action": "hide"}).json()["hidden"]
        assert viewer.get("/api/videos").json() == []
        assert viewer.get(url + "/poster").status_code == 404
        assert viewer.get(url + "/media").status_code == 404
        assert client.get(url).json()["hidden"]
        assert moderator.put(report_url, json={"action": "restore"}).status_code == 200
        assert viewer.get(url).status_code == 200


def test_invalid_upload_and_cross_origin(client):
    assert client.post("/api/videos?title=test", content=b"test").status_code == 401
    register(client, "creator")
    assert client.post("/api/logout", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/videos?title=test", content=b"").status_code == 422
    assert client.post("/api/videos?title=test", content=b"a", headers={"Content-Length": "invalid"}).status_code == 400
    assert client.post("/api/videos?title=test", content=b"a", headers={"Content-Length": "5"}).status_code == 400
    assert client.post("/api/videos?title=test", content=b"a", headers={"Content-Length": "300000000"}).status_code == 413
    url = upload(client, b"not a video")
    process_next()
    assert client.get(url).json()["state"] == "failed"
    assert client.get(url + "/media").status_code == 404
    with Session() as db:
        assert db.scalar(select(Video)).media is None


def test_failed_upload_owner_retry_keeps_original_and_removes_partial_outputs(client, source, monkeypatch):
    register(client, "owner")
    url = upload(client, source, "private")
    assert client.post(url + "/retry").status_code == 409
    first_job = claim()
    assert first_job is not None
    put = storage.put

    def fail_after_poster(path, key, content_type):
        put(path, key, content_type)
        if content_type == "image/jpeg":
            raise OSError("Simulated storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(storage, "put", fail_after_poster)
        process(first_job)
    assert client.get(url).json()["state"] == "failed"
    assert storage.size(first_job.source) == len(source)
    for key in output_keys(first_job.video_id, first_job.attempt):
        with pytest.raises(FileNotFoundError):
            storage.size(key)

    with TestClient(app) as other:
        assert other.post(url + "/retry").status_code == 401
        register(other, "other")
        assign("other", "admin")
        assert other.post(url + "/retry").status_code == 404
    result = client.post(url + "/retry")
    assert result.status_code == 202
    assert result.json() == {"id": first_job.video_id, "state": "queued"}
    assert client.post(url + "/retry").status_code == 409
    second_job = claim()
    assert second_job is not None
    assert second_job.attempt != first_job.attempt
    process(second_job)
    assert client.get(url).json()["state"] == "ready"
    assert client.get(url + "/media").status_code == 200


def test_expired_worker_attempt_cannot_publish_and_is_cleaned(client, source, tmp_path):
    register(client, "owner")
    url = upload(client, source)
    first_job = claim()
    assert first_job is not None
    assert claim() is None
    old_media, old_poster = output_keys(first_job.video_id, first_job.attempt)
    partial = tmp_path / "partial"
    partial.write_bytes(b"partial output")
    storage.put(partial, old_media, "video/mp4")
    with Session.begin() as db:
        db.get(Video, first_job.video_id).started = now() - 2 * LEASE
    recovered_job = claim()
    assert recovered_job is not None
    assert recovered_job.abandoned_attempt == first_job.attempt
    assert not finish(first_job.video_id, first_job.attempt, state="ready", media=old_media, poster=old_poster)
    process(recovered_job)
    with pytest.raises(FileNotFoundError):
        storage.size(old_media)
    assert client.get(url + "/poster").status_code == 200
    with Session() as db:
        poster = db.get(Video, first_job.video_id).poster
    storage.remove(poster)
    assert client.get(url + "/poster").status_code == 404
