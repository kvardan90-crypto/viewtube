import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from sqlalchemy import delete, select

from .db import Login, User, now


COOKIE = "viewtube_session"
SESSION_AGE = timedelta(days=7)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"{salt}:{digest.hex()}"


DUMMY_HASH = password_hash("invalid")


def verify_password(password, encoded):
    return hmac.compare_digest(password_hash(password, encoded.split(":")[0]), encoded)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(db, token):
    if not token or len(token) > 100:
        return None
    return db.scalar(
        select(User).join(Login, Login.user_id == User.id)
        .where(Login.token_hash == token_hash(token), Login.expires > now())
    )


def login(db, user, request, response):
    revoke(db, request.cookies.get(COOKIE))
    db.execute(delete(Login).where(Login.expires <= now()))
    token = secrets.token_urlsafe(32)
    db.add(Login(token_hash=token_hash(token), user_id=user.id, expires=now() + SESSION_AGE))
    db.commit()
    response.set_cookie(
        COOKIE, token, max_age=int(SESSION_AGE.total_seconds()),
        httponly=True, samesite="strict", secure=os.getenv("SECURE_COOKIES", "0") == "1",
    )


def revoke(db, token):
    if token and len(token) <= 100:
        db.execute(delete(Login).where(Login.token_hash == token_hash(token)))
