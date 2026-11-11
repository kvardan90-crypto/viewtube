import os
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


BUCKET = os.getenv("S3_BUCKET", "viewtube")
LOCAL = Path(os.environ["LOCAL_STORAGE"]) if os.getenv("LOCAL_STORAGE") else None


@lru_cache
def client():
    return boto3.client(
        "s3", endpoint_url=os.getenv("S3_ENDPOINT"),
        region_name="us-east-1", config=Config(
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def initialize():
    if LOCAL:
        LOCAL.mkdir(parents=True, exist_ok=True)
        return
    try:
        client().head_bucket(Bucket=BUCKET)
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
            raise
        client().create_bucket(Bucket=BUCKET)


def put(path, key, content_type):
    if LOCAL:
        import shutil
        destination = LOCAL / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        return
    client().upload_file(str(path), BUCKET, key, ExtraArgs={"ContentType": content_type})


def download(key, path):
    if LOCAL:
        import shutil
        shutil.copyfile(LOCAL / key, path)
        return
    client().download_file(BUCKET, key, str(path))


def remove(key):
    if LOCAL:
        (LOCAL / key).unlink(missing_ok=True)
        return
    client().delete_object(Bucket=BUCKET, Key=key)


def size(key):
    if LOCAL:
        return (LOCAL / key).stat().st_size
    return client().head_object(Bucket=BUCKET, Key=key)["ContentLength"]


def stream(key, start, end):
    if LOCAL:
        with (LOCAL / key).open("rb") as file:
            file.seek(start)
            left = end - start + 1
            while left and (chunk := file.read(min(left, 256 * 1024))):
                left -= len(chunk)
                yield chunk
        return
    body = client().get_object(Bucket=BUCKET, Key=key, Range=f"bytes={start}-{end}")["Body"]
    try:
        yield from body.iter_chunks(256 * 1024)
    finally:
        body.close()
