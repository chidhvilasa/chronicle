import json
import sqlite3

from chronicle.events import new_event
from chronicle.storage import LocalStorage


def test_write_event_persists_to_sqlite(tmp_path):
    db_path = tmp_path / "chronicle.db"
    storage = LocalStorage(db_path=db_path)
    event = new_event("run-1", "error", {"message": "boom"})

    storage.write_event(event)
    storage.close()

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT id, run_id, event_type, payload FROM events WHERE id = ?", (event["id"],)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == event["id"]
    assert row[1] == "run-1"
    assert row[2] == "error"
    assert json.loads(row[3]) == {"message": "boom"}


def test_local_storage_creates_parent_dir(tmp_path):
    db_path = tmp_path / "nested" / "dir" / "chronicle.db"
    storage = LocalStorage(db_path=db_path)
    storage.close()
    assert db_path.exists()
