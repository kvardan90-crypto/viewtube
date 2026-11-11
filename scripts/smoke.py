import argparse
import json
import secrets
import subprocess
import time
from http.cookiejar import CookieJar
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener


class CheckFailed(Exception):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


class Client:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def request(self, path, *, method="GET", status=200, payload=None, headers=None):
        headers = dict(headers or {})
        if isinstance(payload, dict):
            payload = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=payload, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=20)
        except HTTPError as error:
            response = error
        except URLError as error:
            raise CheckFailed(f"{method} {path}: {error.reason}") from error
        with response:
            require(response.code == status, f"{method} {path}: HTTP {response.code}, expected {status}")
            return response.read(), response.headers

    def json(self, path, **kwargs):
        body, _ = self.request(path, **kwargs)
        return json.loads(body)


def fixture():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.mp4"
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "testsrc2=size=160x90:rate=15", "-t", "1", "-c:v", "libx264",
            "-threads", "1", "-pix_fmt", "yuv420p", str(path),
        ], check=True, timeout=30)
        return path.read_bytes()


def wait_until_ready(owner, video, timeout):
    deadline = time.monotonic() + timeout
    state = "queued"
    while time.monotonic() < deadline:
        state = owner.json(video)["state"]
        if state == "ready":
            return
        require(state in {"queued", "processing"}, f"Video reached unexpected state {state!r}")
        time.sleep(1)
    raise CheckFailed(f"Video did not finish within {timeout}s (last state: {state})")


def verify(base_url, wait_seconds):
    owner, viewer = Client(base_url), Client(base_url)
    suffix = secrets.token_hex(6)
    viewer_handle = f"smoke_viewer_{suffix}"
    title = f"ViewTube smoke {suffix}"
    require(owner.json("/health") == {"ok": True}, "Health endpoint failed")
    for client, handle in ((owner, f"smoke_owner_{suffix}"), (viewer, viewer_handle)):
        credentials = {"handle": handle, "password": secrets.token_urlsafe(24)}
        account = client.json("/api/register", method="POST", status=201, payload=credentials)
        require(account["handle"] == handle, "Registration returned the wrong account")

    query = urlencode({"title": title, "visibility": "private"})
    queued = owner.json(f"/api/videos?{query}", method="POST", status=202, payload=fixture(),
                        headers={"Content-Type": "application/octet-stream"})
    video = f"/api/videos/{queued['id']}"
    wait_until_ready(owner, video, wait_seconds)

    viewer.request(video, status=404)
    viewer.request(video + "/poster", status=404)
    viewer.request(video + "/media", status=404, headers={"Range": "bytes=0-15"})
    grant = video + "/grants/" + viewer_handle
    owner.json(grant, method="PUT", payload={"enabled": True})
    require(viewer.json(video)["title"] == title, "Private metadata differs after grant")
    head, head_headers = viewer.request(video + "/media", method="HEAD")
    chunk, range_headers = viewer.request(video + "/media", status=206, headers={"Range": "bytes=0-15"})
    require(not head and int(head_headers["Content-Length"]) > 16, "Invalid media HEAD response")
    require(head_headers.get_content_type() == "video/mp4", "Invalid playback MIME type")
    require(len(chunk) == 16 and chunk[4:8] == b"ftyp", "Range did not return the MP4 header")
    require(range_headers["Content-Range"] == "bytes 0-15/" + head_headers["Content-Length"],
            "Content-Range is inconsistent with HEAD")
    poster, _ = viewer.request(video + "/poster")
    require(poster.startswith(b"\xff\xd8"), "Poster is not JPEG")

    viewer.json(video + "/like", method="PUT", payload={"enabled": True})
    message = "Smoke test comment"
    viewer.json(video + "/comments", method="POST", status=201, payload={"body": message})
    require(viewer.json(video)["liked"], "Like was not recorded")
    require(any(item["body"] == message for item in owner.json(video + "/comments")), "Comment is missing")

    owner.json(grant, method="PUT", payload={"enabled": False})
    viewer.request(video, status=404)
    viewer.request(video + "/media", status=404, headers={"Range": "bytes=0-15"})
    print("PASS: register, upload, transcode, Range playback, poster, grant/revoke, like and comment")


def main():
    parser = argparse.ArgumentParser(description="Exercise ViewTube with disposable accounts and a synthetic upload.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base URL of a disposable ViewTube instance")
    parser.add_argument("--wait", type=int, default=120, help="Seconds to wait for the worker")
    args = parser.parse_args()
    if args.wait <= 0:
        parser.error("--wait must be positive")
    try:
        verify(args.url, args.wait)
    except (CheckFailed, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()
