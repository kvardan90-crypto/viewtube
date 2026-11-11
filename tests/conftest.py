import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


temporary = TemporaryDirectory()
work = Path(temporary.name)
os.environ["DATABASE_URL"] = "sqlite:///" + str(work / "test.sqlite3")
os.environ["LOCAL_STORAGE"] = str(work / "media")

from app import storage
from app.db import Base, engine


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    storage.initialize()
    yield
    engine.dispose()
