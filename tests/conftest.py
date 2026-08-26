"""
Shared fixtures. Each test gets its own throwaway SQLite file so tests never
interfere with each other or with a real agent.db.
"""
import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["AGENT_DB_PATH"] = path

    # database.py reads DB_PATH at import time, so reset it directly
    import app.database.database as database_module
    monkeypatch.setattr(database_module, "DB_PATH", path)
    database_module.init_db()

    yield path

    os.remove(path)
    for ext in ("-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)
