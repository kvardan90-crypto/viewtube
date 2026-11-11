import argparse
import os
import time

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from . import storage
from .db import Base, Session, User, engine
from .security import password_hash


def initialize():
    for attempt in range(45):
        try:
            Base.metadata.create_all(engine)
            storage.initialize()
            return
        except (OperationalError, BotoCoreError, ClientError):
            if attempt == 44:
                raise
            time.sleep(2)


def ensure_admin():
    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        return
    with Session.begin() as db:
        if db.scalar(select(User.id).where(User.handle == "admin")) is None:
            db.add(User(handle="admin", password=password_hash(password), role="admin"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    initialize()
    ensure_admin()
    if args.seed:
        from .seed import seed
        seed()


if __name__ == "__main__":
    main()
